from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import replace
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import AppConfig, is_loopback_host, load_config, write_runtime_env
from .crisis import CrisisPack, CrisisValidationError, VolumePack
from .doctor import doctor
from .host import ChronicleHost
from .product_api import build_product_router
from .subject_continuity import SubjectContinuityError
from .volume_runtime import VolumeRuntimeError

logger = logging.getLogger(__name__)


class SetupRequest(BaseModel):
    base_url: str = Field(max_length=2048)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(max_length=256)
    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning_effort: str = Field(default="", max_length=128)


def _provider_url_error(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return "Provider URL is malformed."
    if parsed.scheme not in {"http", "https"}:
        return "Provider URL must use http or https."
    if parsed.username or parsed.password:
        return "Provider URL must not contain embedded credentials."
    host = parsed.hostname
    if not host:
        return "Provider URL must include a hostname."
    literal_host = None
    try:
        literal_host = ipaddress.ip_address(host)
    except ValueError:
        pass
    if literal_host is not None:
        addresses = [literal_host]
        explicit_loopback = literal_host.is_loopback
    elif host.lower() == "localhost":
        addresses = [ipaddress.ip_address("127.0.0.1")]
        explicit_loopback = True
    else:
        try:
            infos = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError:
            return "Provider hostname could not be resolved."
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        explicit_loopback = False
    if not addresses:
        return "Provider hostname could not be resolved."
    for address in addresses:
        unsafe = (
            address.is_private
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
            or (address.is_loopback and not explicit_loopback)
        )
        if unsafe:
            return "Provider URL resolves to a private or reserved network address."
    return None


def _provider_model_ids(response: Any) -> set[str]:
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        return set()
    entries = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return set()
    return {str(item.get("id")) for item in entries if isinstance(item, dict) and item.get("id")}


def create_app(
    config: AppConfig | None = None,
) -> FastAPI:
    base_config = config or load_config()
    if not is_loopback_host(base_config.host):
        raise ValueError("Chronicle only supports loopback host binding")
    app = FastAPI(title="Chronicle: 甲申", docs_url="/dev/docs", redoc_url=None)
    web_root = base_config.root / "web"
    if web_root.exists():
        app.mount("/assets", StaticFiles(directory=web_root), name="assets")

    def current_config() -> AppConfig:
        values: dict[str, str] = {}
        if base_config.runtime_env_path.exists():
            for line in base_config.runtime_env_path.read_text(encoding="utf-8").splitlines():
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
        return replace(
            base_config,
            llm_base_url=values.get("CHRONICLE_LLM_BASE_URL", base_config.llm_base_url).rstrip("/"),
            llm_api_key=values.get("CHRONICLE_LLM_API_KEY", base_config.llm_api_key),
            llm_model=values.get("CHRONICLE_LLM_MODEL", base_config.llm_model),
            llm_api_mode=values.get("CHRONICLE_LLM_API_MODE", base_config.llm_api_mode),
            llm_reasoning_effort=values.get(
                "CHRONICLE_LLM_REASONING_EFFORT", base_config.llm_reasoning_effort
            ),
        )

    def host() -> ChronicleHost:
        active = current_config()
        return ChronicleHost(active)

    def assert_archivist_open(active: ChronicleHost) -> None:
        current = active.db.active_volume_worldline()
        if current is not None and current.get("human_lifetime_id"):
            raise HTTPException(status_code=423, detail="Archivist view is locked while a human Seat is active")

    def volume_pack() -> VolumePack:
        return VolumePack.load(current_config().volume_path)

    def crisis_payload(pack: CrisisPack) -> dict[str, Any]:
        return {
            "summary": pack.summary(),
            "title": pack.crisis.title,
            "subtitle": pack.crisis.subtitle,
            "checkpoint": pack.crisis.checkpoint.model_dump(mode="json"),
            "boundary": pack.crisis.simulation_boundary.model_dump(mode="json"),
            "surface": pack.surface_projection(
                {"positions": {}, "messages": []}, visible_actor_ids=set()
            ),
            "actors": [
                {
                    "id": actor.id,
                    "display_name": actor.display_name,
                    "role_charter": actor.role_charter.model_dump(mode="json"),
                    "playable": actor.id in pack.crisis.playable_actor_ids,
                }
                for actor in pack.crisis.actors
            ],
            "corridor": [
                location.model_dump(mode="json")
                for location in sorted(pack.crisis.corridor, key=lambda item: item.order)
            ],
        }

    async def reconcile_volume_runtime_on_startup() -> None:
        """Fail closed on restart until the live V6 Volume is reconciled."""

        try:
            active = current_config()
            volume_host = ChronicleHost(active)
            candidates = []
            current = volume_host.db.active_volume_worldline()
            if current is not None and current.get("runtime_mode") == "live":
                candidates.append(current)
            candidates.extend(
                row
                for row in volume_host.db.worldlines(status="SEALED")
                if row.get("kind") == "VOLUME"
                and row.get("runtime_mode") == "live"
                and row.get("runtime_phase") == "CLEANUP_PENDING"
            )
            for row in candidates:
                await asyncio.to_thread(
                    volume_host.volume_runtime.reconcile_live_runtime,
                    str(row["id"]),
                )
        except Exception:
            logger.exception("Chronicle V6 Volume startup reconcile failed closed")

    app.router.add_event_handler("startup", reconcile_volume_runtime_on_startup)

    app.include_router(build_product_router(host))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "chronicle-host"}

    @app.get("/api/config")
    async def runtime_config() -> dict[str, Any]:
        active = current_config()
        readiness = await asyncio.to_thread(doctor, active)
        hermes_ready = readiness["status"] == "READY"
        return {
            "setup_required": not active.llm_configured,
            "base_url": active.llm_base_url,
            "model": active.llm_model,
            "api_mode": active.llm_api_mode,
            "reasoning_effort": active.llm_reasoning_effort,
            "api_key": active.masked_api_key(),
            "hermes_base_url": active.hermes_base_url,
            "runtime_mode": "live",
            "hermes_ready": hermes_ready,
            "hermes_status": readiness["status"],
            "dev": active.dev,
        }

    @app.get("/api/volume")
    async def volume() -> dict[str, Any]:
        return volume_pack().summary()

    @app.get("/api/crises")
    async def crises() -> dict[str, Any]:
        pack = volume_pack()
        return {"crises": [crisis.summary() for crisis in pack.packs.values()]}

    @app.get("/api/crises/{crisis_id}")
    async def crisis_detail(crisis_id: str) -> dict[str, Any]:
        try:
            return crisis_payload(volume_pack().pack(crisis_id))
        except CrisisValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/dev/worldlines/{worldline_id}/why/{event_id}")
    async def dev_worldline_causal_trace(worldline_id: str, event_id: str) -> dict[str, Any]:
        active = current_config()
        if not active.dev:
            raise HTTPException(status_code=404, detail="Developer diagnostics are disabled")
        try:
            return await asyncio.to_thread(
                ChronicleHost(active).volume_runtime.causal_trace,
                worldline_id,
                event_id,
            )
        except (SubjectContinuityError, VolumeRuntimeError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/doctor")
    async def run_doctor() -> dict[str, Any]:
        return await asyncio.to_thread(doctor, current_config())

    @app.post("/api/setup/test")
    async def setup_test(request: SetupRequest) -> dict[str, Any]:
        if not request.base_url or not request.model:
            return {"ok": False, "message": "Base URL and model are required."}
        if not request.api_key:
            return {"ok": False, "message": "An API key is required for the connection test."}
        base_url = request.base_url.rstrip("/")
        url_error = _provider_url_error(base_url)
        if url_error:
            return {"ok": False, "message": url_error}
        try:
            endpoints = [f"{base_url}/models"]
            if not base_url.endswith("/v1"):
                endpoints.append(f"{base_url}/v1/models")
            response = None
            model_ids: set[str] = set()
            for endpoint in endpoints:
                candidate = await asyncio.to_thread(
                    httpx.get,
                    endpoint,
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    timeout=12,
                )
                response = candidate
                if candidate.status_code < 400:
                    model_ids = _provider_model_ids(candidate)
                    if request.model in model_ids:
                        break
            assert response is not None
            if response.status_code >= 400:
                return {"ok": False, "message": f"Provider returned HTTP {response.status_code}."}
            if request.model not in model_ids:
                return {"ok": False, "message": f"Model {request.model} was not returned by the provider."}
            return {"ok": True, "message": "Connection established.", "model": request.model}
        except httpx.HTTPError as exc:
            return {"ok": False, "message": f"Connection failed: {type(exc).__name__}."}

    @app.post("/api/setup/configure")
    async def setup_configure(request: SetupRequest) -> dict[str, Any]:
        active = current_config()
        assert_archivist_open(host())
        if not request.base_url or not request.model:
            raise HTTPException(status_code=400, detail="Base URL and model are required")
        url_error = _provider_url_error(request.base_url)
        if url_error:
            raise HTTPException(status_code=400, detail=url_error)
        existing = active.llm_api_key
        api_key = request.api_key or existing
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        values = {
            "CHRONICLE_LLM_BASE_URL": request.base_url.rstrip("/"),
            "CHRONICLE_LLM_API_KEY": api_key,
            "CHRONICLE_LLM_MODEL": request.model,
            "CHRONICLE_LLM_API_MODE": request.api_mode,
            "CHRONICLE_LLM_REASONING_EFFORT": request.reasoning_effort,
        }
        try:
            write_runtime_env(active, values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        configured = current_config()
        return {
            "configured": True,
            "model": configured.llm_model,
            "api_mode": configured.llm_api_mode,
            "reasoning_effort": configured.llm_reasoning_effort,
            "api_key": configured.masked_api_key(),
            "runtime_file_mode": oct(active.runtime_env_path.stat().st_mode & 0o777),
            "message": "Runtime saved server-side. Live Volume Lifetimes can now be materialized.",
        }

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/{path:path}")
    async def spa_fallback(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        candidate = web_root / path
        if candidate.is_file():
            return FileResponse(candidate)
        raise HTTPException(status_code=404, detail="Page not found")

    @app.api_route(
        "/{path:path}",
        methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def api_method_fallback(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        raise HTTPException(status_code=405, detail="Method not allowed")

    return app


app = create_app()

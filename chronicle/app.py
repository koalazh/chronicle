from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import AppConfig, load_config, write_runtime_env
from .doctor import doctor
from .hermes import HermesRuntimeError
from .hermes import bootstrap as bootstrap_hermes
from .host import BranchEngine, ChronicleHost
from .models import BranchAction, WakeType


class AdvanceRequest(BaseModel):
    tick: int = Field(ge=0, le=78)


class WakeRequest(BaseModel):
    tick: int | None = Field(default=None, ge=0, le=78)
    wake_type: WakeType = WakeType.OBSERVATION
    live: bool = False
    outcome: str = ""


class SetupRequest(BaseModel):
    base_url: str
    api_key: str = ""
    model: str
    api_mode: str = "chat_completions"
    reasoning_effort: str = ""


def create_app(config: AppConfig | None = None) -> FastAPI:
    base_config = config or load_config()
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "chronicle-host"}

    @app.get("/api/config")
    async def runtime_config() -> dict[str, Any]:
        active = current_config()
        return {
            "setup_required": not active.llm_configured,
            "base_url": active.llm_base_url,
            "model": active.llm_model,
            "api_mode": active.llm_api_mode,
            "reasoning_effort": active.llm_reasoning_effort,
            "api_key": active.masked_api_key(),
            "hermes_base_url": active.hermes_base_url,
        }

    @app.get("/api/scenario")
    async def scenario() -> dict[str, Any]:
        active = host()
        return {
            "summary": active.pack.summary(),
            "current_tick": active.current_tick,
            "world": active.world_state(),
            "actors": [actor.model_dump(mode="json") for actor in active.pack.actors],
            "locations": [location.model_dump(mode="json") for location in active.pack.locations],
            "routes": [route.model_dump(mode="json") for route in active.pack.routes],
            "fork": active.pack.fork.model_dump(mode="json"),
        }

    @app.get("/api/timeline")
    async def timeline(tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        return {"current_tick": active.current_tick if tick is None else tick, "items": active.timeline(tick)}

    @app.post("/api/canon/advance")
    async def advance(request: AdvanceRequest) -> dict[str, Any]:
        active = host()
        try:
            tick = active.set_tick(request.tick)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"current_tick": tick, "world": active.world_state(tick), "who_knows": active.who_knows(tick)}

    @app.get("/api/events/{event_id}")
    async def event_detail(event_id: str, tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        if event_id not in active.pack.event_by_id:
            raise HTTPException(status_code=404, detail="event not found")
        return active.event_detail(event_id, tick)

    @app.get("/api/sources/{assertion_id}")
    async def source_detail(assertion_id: str) -> dict[str, Any]:
        active = host()
        if assertion_id not in active.pack.assertion_by_id:
            raise HTTPException(status_code=404, detail="assertion not found")
        return active.source_detail(assertion_id)

    @app.get("/api/who-knows")
    async def who_knows(tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        return {"tick": active.current_tick if tick is None else tick, "seats": active.who_knows(tick)}

    @app.get("/api/lifetimes/{seat}")
    async def lifetime(seat: str) -> dict[str, Any]:
        active = host()
        if seat not in active.pack.actor_by_seat:
            raise HTTPException(status_code=404, detail="Seat not found")
        return active.lifetime(seat)

    @app.post("/api/lifetimes/{seat}/wake")
    async def wake(seat: str, request: WakeRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                active.wake,
                seat,
                request.tick,
                request.wake_type,
                live=request.live,
                outcome=request.outcome,
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HermesRuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/lifetimes/{seat}/reflect")
    async def reflect(seat: str, request: WakeRequest) -> dict[str, Any]:
        request.wake_type = WakeType.REFLECTION
        active = host()
        try:
            return await asyncio.to_thread(
                active.wake,
                seat,
                request.tick,
                WakeType.REFLECTION,
                live=request.live,
                outcome=request.outcome or "A later event contradicted an earlier assessment.",
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HermesRuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/branch/definition")
    async def branch_definition() -> dict[str, Any]:
        active = host()
        return {
            "fork": active.pack.fork.model_dump(mode="json"),
            "event": active.pack.event_by_id[active.pack.fork.event_id].model_dump(mode="json"),
        }

    @app.post("/api/branch")
    async def create_branch() -> dict[str, Any]:
        active = host()
        return BranchEngine(active).create()

    @app.get("/api/branch/{branch_id}")
    async def branch(branch_id: str) -> dict[str, Any]:
        active = host()
        value = active.db.branch(branch_id)
        if value is None:
            raise HTTPException(status_code=404, detail="branch not found")
        return {"branch": value, "records": active.db.branch_records(branch_id)}

    @app.post("/api/branch/{branch_id}/step")
    async def branch_step(branch_id: str, seat: str, action: BranchAction) -> dict[str, Any]:
        active = host()
        try:
            return BranchEngine(active).step(branch_id, seat, action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/doctor")
    async def run_doctor() -> dict[str, Any]:
        return doctor(current_config())

    @app.post("/api/setup/test")
    async def setup_test(request: SetupRequest) -> dict[str, Any]:
        if not request.base_url or not request.model:
            return {"ok": False, "message": "Base URL and model are required."}
        if not request.api_key:
            return {"ok": False, "message": "An API key is required for the connection test."}
        base_url = request.base_url.rstrip("/")
        try:
            endpoints = [f"{base_url}/models"]
            if not base_url.endswith("/v1"):
                endpoints.append(f"{base_url}/v1/models")
            response = None
            for endpoint in endpoints:
                candidate = await asyncio.to_thread(
                    httpx.get,
                    endpoint,
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    timeout=12,
                )
                response = candidate
                if candidate.status_code < 400:
                    break
            assert response is not None
            if response.status_code >= 400:
                return {"ok": False, "message": f"Provider returned HTTP {response.status_code}."}
            return {"ok": True, "message": "Connection established.", "model": request.model}
        except httpx.HTTPError as exc:
            return {"ok": False, "message": f"Connection failed: {type(exc).__name__}."}

    @app.post("/api/setup/configure")
    async def setup_configure(request: SetupRequest) -> dict[str, Any]:
        active = current_config()
        if not request.base_url or not request.model:
            raise HTTPException(status_code=400, detail="Base URL and model are required")
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
        write_runtime_env(active, values)
        configured = current_config()
        return {
            "configured": True,
            "model": configured.llm_model,
            "api_mode": configured.llm_api_mode,
            "reasoning_effort": configured.llm_reasoning_effort,
            "api_key": configured.masked_api_key(),
            "runtime_file_mode": oct(active.runtime_env_path.stat().st_mode & 0o777),
            "message": "Runtime saved server-side. Bootstrap can now create the three Seats.",
        }

    @app.post("/api/bootstrap")
    async def bootstrap() -> dict[str, Any]:
        active = current_config()
        try:
            return await asyncio.to_thread(bootstrap_hermes, active)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(web_root / "index.html")

    @app.get("/{path:path}")
    async def spa_fallback(path: str) -> FileResponse:
        candidate = web_root / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(web_root / "index.html")

    return app


app = create_app()

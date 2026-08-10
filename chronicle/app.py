from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import replace
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import AppConfig, is_loopback_host, load_config, write_runtime_env
from .crisis import CrisisPack, CrisisValidationError, VolumeRegistry
from .crisis_runtime import (
    CrisisRunConflict,
    CrisisRunEngine,
    CrisisRunError,
    RunMode,
)
from .db import ChronicleDB
from .doctor import doctor
from .hermes import HermesRuntimeError
from .hermes import bootstrap as bootstrap_hermes
from .host import BranchEngine, ChronicleHost
from .live_runtime import LiveRuntimeManager
from .models import BranchAction, WakeType
from .runtime import WorldlineConflict, WorldlineError, WorldlineRuntime


class AdvanceRequest(BaseModel):
    tick: int = Field(ge=0, le=78)


class WakeRequest(BaseModel):
    tick: int | None = Field(default=None, ge=0, le=78)
    wake_type: WakeType = WakeType.OBSERVATION
    live: bool = False
    outcome: str = ""


class SetupRequest(BaseModel):
    base_url: str = Field(max_length=2048)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(max_length=256)
    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning_effort: str = Field(default="", max_length=128)


class CreateWorldlineRequest(BaseModel):
    entry_id: str = Field(max_length=128)
    seat: str = Field(default="A", max_length=16)
    live: bool = False


class WorldlineInputRequest(BaseModel):
    text: str = Field(max_length=4000)


class WorldlineConfirmRequest(BaseModel):
    confirmation_id: str = Field(max_length=128)


class WorldlineAdvanceRequest(BaseModel):
    live: bool = False


class WorldlineSealRequest(BaseModel):
    reason: str = Field(default="user_exit", max_length=256)


class CreateRunRequest(BaseModel):
    crisis_id: str | None = Field(default=None, min_length=1, max_length=128)
    mode: Literal["WATCH", "TAKEOVER"]
    human_actor_id: str | None = Field(default=None, min_length=1, max_length=128)
    live: bool = True


class HumanDecisionRequest(BaseModel):
    text: str = Field(default="", max_length=4000)


class SealRunRequest(BaseModel):
    reason: str = Field(default="user_exit", max_length=256)


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
    *,
    live_runtime: LiveRuntimeManager | None = None,
    manage_live_runtime_on_startup: bool = False,
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
        if active.db.active_human_worldline() is not None:
            raise HTTPException(status_code=423, detail="Archivist view is locked while a human Seat is active")

    def worldline_runtime(active: ChronicleHost) -> WorldlineRuntime:
        return active.worldline_runtime

    def worldline_http_error(exc: WorldlineError) -> HTTPException:
        status = 423 if "Archivist view is locked" in str(exc) else 409 if isinstance(exc, WorldlineConflict) else 400
        return HTTPException(status_code=status, detail=str(exc))

    def crisis_engine() -> CrisisRunEngine:
        return CrisisRunEngine(current_config())

    def volume_registry() -> VolumeRegistry:
        return VolumeRegistry.load(current_config().volume_path)

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

    managed_runtime = live_runtime

    def crisis_runtime(active: AppConfig) -> LiveRuntimeManager:
        nonlocal managed_runtime
        if managed_runtime is None or managed_runtime.config != active:
            managed_runtime = LiveRuntimeManager(active)
        return managed_runtime

    def runtime_message(run: dict[str, Any]) -> str:
        phase = str(run.get("runtime_phase") or "READY")
        code = str(run.get("runtime_error_code") or "")
        if phase == "READY":
            return ""
        if phase in {"BOOTSTRAPPING", "RECONCILING"}:
            return "这一局正在建立或恢复，暂不能推进。"
        if phase == "SEALING":
            return "这一局正在封存，暂不能继续操作。"
        if phase == "CLEANUP_PENDING":
            return "卷册已经封存，正在收束本地主体。"
        if code in {"runtime_owner_unknown", "runtime_port_occupied"}:
            return "发现一个无法安全接管的本地服务；为避免影响其他项目，这一局尚未启动。"
        return "这一局尚未准备好；请在页面中重新准备。"

    if manage_live_runtime_on_startup:

        @app.on_event("startup")
        async def reconcile_live_runtime() -> None:
            await asyncio.to_thread(crisis_runtime(current_config()).reconcile_active)

    def crisis_http_error(exc: CrisisRunError) -> HTTPException:
        if isinstance(exc, CrisisRunConflict):
            detail: str | dict[str, Any] = {
                "code": exc.code,
                "message": str(exc),
                "state": exc.state,
                "tick": exc.tick,
            }
        else:
            detail = str(exc)
        return HTTPException(
            status_code=409 if isinstance(exc, CrisisRunConflict) else 400,
            detail=detail,
        )

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
        }

    @app.get("/api/crisis")
    async def crisis() -> dict[str, Any]:
        return crisis_payload(volume_registry().default_pack)

    @app.get("/api/volume")
    async def volume() -> dict[str, Any]:
        return volume_registry().summary()

    @app.get("/api/crises")
    async def crises() -> dict[str, Any]:
        registry = volume_registry()
        return {"crises": [pack.summary() for pack in registry.packs.values()]}

    @app.get("/api/crises/{crisis_id}")
    async def crisis_detail(crisis_id: str) -> dict[str, Any]:
        try:
            return crisis_payload(volume_registry().pack(crisis_id))
        except CrisisValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/runs")
    async def create_run(request: CreateRunRequest) -> dict[str, Any]:
        active = current_config()
        try:
            pack = volume_registry().pack(request.crisis_id) if request.crisis_id else volume_registry().default_pack
        except CrisisValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not request.live and not active.dev:
            raise HTTPException(
                status_code=409,
                detail="正式体验只使用真实主体运行；测试替身仅在开发模式开放。",
            )
        if request.live and not active.llm_configured:
            raise HTTPException(
                status_code=409,
                detail="请先在设置页连接主体所需的模型服务。",
            )
        engine = CrisisRunEngine(active, pack=pack)
        try:
            if request.live:
                summary = await asyncio.to_thread(
                    crisis_runtime(active).create,
                    RunMode(request.mode),
                    human_actor_id=request.human_actor_id,
                    crisis_id=pack.crisis.id,
                )
                return {
                    "run": summary,
                    "started": summary["runtime_phase"] == "READY",
                    "start_error": runtime_message(summary),
                }
            created = await asyncio.to_thread(
                engine.create,
                RunMode(request.mode),
                runtime_mode="fixture",
                human_actor_id=request.human_actor_id,
            )
            if not request.live:
                await asyncio.to_thread(engine.advance_one, created["run"]["id"])
            return {
                "run": engine.run_summary(created["run"]["id"]),
                "started": True,
                "start_error": "",
            }
        except CrisisRunConflict as exc:
            raise HTTPException(
                status_code=409,
                detail="已有一局尚未封存，请先继续或封存当前这一局。",
            ) from exc
        except CrisisRunError as exc:
            raise HTTPException(
                status_code=400,
                detail="这一局未能建立，请确认设置页中的模型连接后重试。",
            ) from exc

    @app.get("/api/runs/active")
    async def active_run() -> dict[str, Any]:
        engine = crisis_engine()
        run = engine.db.active_run()
        if run is None:
            return {"run": None}
        return {"run": engine.run_summary(run["id"])}

    @app.post("/api/runs/{run_id}/continue")
    async def continue_run(run_id: str) -> dict[str, Any]:
        active = current_config()
        engine = CrisisRunEngine(active)
        try:
            summary = engine.run_summary(run_id)
            advanced = await asyncio.to_thread(
                crisis_runtime(active).advance_one if summary["runtime_mode"] == "live" else engine.advance_one,
                run_id,
            )
            return {
                "advanced": advanced,
                "run": crisis_engine().run_summary(run_id),
            }
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.get("/api/runs/{run_id}/world")
    async def run_world(run_id: str) -> dict[str, Any]:
        engine = crisis_engine()
        try:
            summary = engine.run_summary(run_id)
            if summary["mode"] == "TAKEOVER" and summary["status"] == "ACTIVE":
                raise HTTPException(
                    status_code=403,
                    detail="Human Takeover is locked to the Human perspective",
                )
            return engine.world_view(run_id)
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.get("/api/runs/{run_id}/perspective/{actor_id}")
    async def run_perspective(run_id: str, actor_id: str) -> dict[str, Any]:
        engine = crisis_engine()
        try:
            summary = engine.run_summary(run_id)
            if (
                summary["mode"] == "TAKEOVER"
                and summary["status"] == "ACTIVE"
                and actor_id != summary["human_actor"]
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Human Takeover is locked to the Human perspective",
                )
            return engine.product_perspective(run_id, actor_id)
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.post("/api/runs/{run_id}/decision")
    async def decide(run_id: str, request: HumanDecisionRequest) -> dict[str, Any]:
        try:
            engine = crisis_engine()
            summary = engine.run_summary(run_id)
            return await asyncio.to_thread(
                crisis_runtime(current_config()).submit_human_decision
                if summary["runtime_mode"] == "live"
                else engine.submit_human_decision,
                run_id,
                request.text,
            )
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.post("/api/runs/{run_id}/seal")
    async def seal_run(run_id: str, request: SealRunRequest) -> dict[str, Any]:
        engine = crisis_engine()
        try:
            summary = engine.run_summary(run_id)
            sealed = await asyncio.to_thread(
                crisis_runtime(current_config()).seal
                if summary["runtime_mode"] == "live"
                else engine.seal,
                run_id,
                request.reason,
            )
            return {"run": sealed}
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.post("/api/runs/{run_id}/runtime/retry")
    async def retry_runtime(run_id: str) -> dict[str, Any]:
        active = current_config()
        try:
            return {"run": await asyncio.to_thread(crisis_runtime(active).retry, run_id)}
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.get("/api/runs/{run_id}/replay")
    async def replay_run(run_id: str) -> dict[str, Any]:
        engine = crisis_engine()
        try:
            return engine.replay(run_id)
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.get("/api/archive")
    async def archive() -> dict[str, Any]:
        active = current_config()
        db = ChronicleDB(active.database_path)
        runs = []
        for row in db.worldlines(status="SEALED"):
            if row["kind"] == "CRISIS":
                runs.append(CrisisRunEngine(active, db=db).run_summary(row["id"]))
            else:
                runs.append(
                    {
                        "id": row["id"],
                        "mode": "LEGACY_V2",
                        "status": row["status"],
                        "current_tick": row["current_tick"],
                        "created_at": row["created_at"],
                        "seal_reason": row["seal_reason"],
                    }
                )
        return {"runs": runs}

    @app.get("/api/history")
    async def historical_background() -> dict[str, Any]:
        pack = volume_registry().default_pack
        return historical_payload(pack)

    @app.get("/api/crises/{crisis_id}/history")
    async def crisis_history(crisis_id: str) -> dict[str, Any]:
        try:
            return historical_payload(volume_registry().pack(crisis_id))
        except CrisisValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def historical_payload(pack: CrisisPack) -> dict[str, Any]:
        return {
            "sources": [source.model_dump(mode="json") for source in pack.sources],
            "assertions": [assertion.model_dump(mode="json") for assertion in pack.assertions],
            "anchors": [anchor.model_dump(mode="json") for anchor in pack.crisis.anchors],
            "boundary": pack.crisis.simulation_boundary.model_dump(mode="json"),
        }

    @app.get("/api/dev/runs/{run_id}")
    async def dev_run(run_id: str) -> dict[str, Any]:
        active = current_config()
        if not active.dev:
            raise HTTPException(status_code=404, detail="Developer diagnostics are disabled")
        engine = CrisisRunEngine(active)
        try:
            summary = engine.run_summary(run_id)
            events = engine.db.worldline_events(run_id)
            wakes = engine.db.crisis_wakes(run_id)
            lifetimes = engine.db.worldline_lifetimes(run_id)
            if summary["mode"] == "TAKEOVER" and summary["status"] == "ACTIVE":
                human_actor = str(summary["human_actor"])
                lifetimes = [item for item in lifetimes if item["seat"] == human_actor]
                wakes = [item for item in wakes if item["actor_id"] == human_actor]
                events = [
                    item
                    for item in events
                    if not item["seat_id"]
                    or item["seat_id"] == human_actor
                    or human_actor in item["payload"].get("visibility", [])
                ]
            return {
                "run": summary,
                "wakes": wakes,
                "events": events,
                "lifetimes": lifetimes,
            }
        except CrisisRunError as exc:
            raise crisis_http_error(exc) from exc

    @app.get("/api/scenario")
    async def scenario() -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        return {
            "summary": active.pack.summary(),
            "current_tick": active.current_tick,
            "world": active.world_state(),
            "actors": [actor.model_dump(mode="json") for actor in active.pack.actors],
            "locations": [location.model_dump(mode="json") for location in active.pack.locations],
            "routes": [route.model_dump(mode="json") for route in active.pack.routes],
            "fork": active.pack.fork.model_dump(mode="json"),
            "entry": active.pack.fork.model_dump(mode="json"),
        }

    @app.get("/api/timeline")
    async def timeline(tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        return {"current_tick": active.current_tick if tick is None else tick, "items": active.timeline(tick)}

    @app.post("/api/canon/advance")
    async def advance(request: AdvanceRequest) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        try:
            tick = active.set_tick(request.tick)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"current_tick": tick, "world": active.world_state(tick), "who_knows": active.who_knows(tick)}

    @app.post("/api/canon/advance-next")
    async def advance_next() -> dict[str, Any]:
        active = host()
        try:
            return worldline_runtime(active).advance_canon_next()
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.get("/api/events/{event_id}")
    async def event_detail(event_id: str, tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        if event_id not in active.pack.event_by_id:
            raise HTTPException(status_code=404, detail="event not found")
        return active.event_detail(event_id, tick)

    @app.get("/api/sources/{assertion_id}")
    async def source_detail(assertion_id: str) -> dict[str, Any]:
        active = host()
        active_worldline = active.db.active_human_worldline()
        if active_worldline is not None:
            context = active.worldline_runtime.seat_context(active_worldline["id"])
            if assertion_id not in context.visible_assertion_ids:
                raise HTTPException(status_code=404, detail="source not found")
        else:
            assert_archivist_open(active)
        if assertion_id not in active.pack.assertion_by_id:
            raise HTTPException(status_code=404, detail="assertion not found")
        return active.source_detail(assertion_id)

    @app.get("/api/who-knows")
    async def who_knows(tick: int | None = Query(default=None, ge=0, le=78)) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        return {"tick": active.current_tick if tick is None else tick, "seats": active.who_knows(tick)}

    @app.get("/api/lifetimes/{seat}")
    async def lifetime(seat: str) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        if seat not in active.pack.actor_by_seat:
            raise HTTPException(status_code=404, detail="Seat not found")
        return active.lifetime(seat)

    @app.post("/api/lifetimes/{seat}/wake")
    async def wake(seat: str, request: WakeRequest) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
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
        assert_archivist_open(active)
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
        assert_archivist_open(active)
        return {
            "fork": active.pack.fork.model_dump(mode="json"),
            "event": active.pack.event_by_id[active.pack.fork.event_id].model_dump(mode="json"),
        }

    @app.post("/api/branch")
    async def create_branch() -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        try:
            return BranchEngine(active).create()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/branch/{branch_id}")
    async def branch(branch_id: str) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        value = active.db.branch(branch_id)
        if value is None:
            raise HTTPException(status_code=404, detail="branch not found")
        return {"branch": value, "records": active.db.branch_records(branch_id)}

    @app.post("/api/branch/{branch_id}/step")
    async def branch_step(branch_id: str, seat: str, action: BranchAction) -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        try:
            return BranchEngine(active).step(branch_id, seat, action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/entries")
    async def entries() -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        return {"entries": [active.pack.fork.model_dump(mode="json")]}

    @app.post("/api/worldlines")
    async def create_worldline(request: CreateWorldlineRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                worldline_runtime(active).create,
                request.entry_id,
                request.seat,
                live=request.live,
            )
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc
        except HermesRuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/worldlines/active")
    async def active_worldline() -> dict[str, Any]:
        active = host()
        return {"active": await asyncio.to_thread(worldline_runtime(active).active)}

    @app.get("/api/worldlines")
    async def sealed_worldlines() -> dict[str, Any]:
        active = host()
        assert_archivist_open(active)
        return {"worldlines": await asyncio.to_thread(worldline_runtime(active).sealed)}

    @app.get("/api/worldlines/{worldline_id}/context")
    async def worldline_context(worldline_id: str) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).context, worldline_id)
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.get("/api/worldlines/{worldline_id}/lifetimes")
    async def worldline_lifetimes(worldline_id: str) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).lifetimes, worldline_id)
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.get("/api/worldlines/{worldline_id}/lifetimes/{seat}")
    async def worldline_lifetime(worldline_id: str, seat: str) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).lifetime, worldline_id, seat)
        except WorldlineError as exc:
            if str(exc) == "Seat not found":
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            raise worldline_http_error(exc) from exc

    @app.get("/api/worldlines/{worldline_id}/ledger")
    async def worldline_ledger(worldline_id: str) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).ledger, worldline_id)
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.post("/api/worldlines/{worldline_id}/input")
    async def worldline_input(worldline_id: str, request: WorldlineInputRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).input, worldline_id, request.text)
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.post("/api/worldlines/{worldline_id}/confirm")
    async def worldline_confirm(worldline_id: str, request: WorldlineConfirmRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                worldline_runtime(active).confirm, worldline_id, request.confirmation_id
            )
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.post("/api/worldlines/{worldline_id}/cancel")
    async def worldline_cancel(worldline_id: str, request: WorldlineConfirmRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                worldline_runtime(active).cancel, worldline_id, request.confirmation_id
            )
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.post("/api/worldlines/{worldline_id}/advance")
    async def worldline_advance(worldline_id: str, request: WorldlineAdvanceRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                worldline_runtime(active).advance, worldline_id, live=request.live
            )
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc
        except HermesRuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/worldlines/{worldline_id}/seal")
    async def worldline_seal(worldline_id: str, request: WorldlineSealRequest) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(
                worldline_runtime(active).seal, worldline_id, request.reason
            )
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

    @app.get("/api/worldlines/{worldline_id}/debrief")
    async def worldline_debrief(worldline_id: str) -> dict[str, Any]:
        active = host()
        try:
            return await asyncio.to_thread(worldline_runtime(active).debrief, worldline_id)
        except WorldlineError as exc:
            raise worldline_http_error(exc) from exc

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
            "message": "Runtime saved server-side. Bootstrap can now create the three Seats.",
        }

    @app.post("/api/bootstrap")
    async def bootstrap() -> dict[str, Any]:
        active = current_config()
        assert_archivist_open(host())
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

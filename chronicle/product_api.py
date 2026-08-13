from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .editorial import volume_attention
from .hermes import HermesRuntimeError
from .host import ChronicleHost
from .models import WorldlineKind
from .product_assist import draft_judgment
from .product_projection import ProductProjection
from .volume_live import HermesVolumeActorDriver
from .volume_runtime import VolumeRuntimeConflict, VolumeRuntimeError

V6_CONTINUE_MAX_TICKS = 12
V6_CONTINUE_MAX_AGENT_DELIBERATIONS = 24
V6_CONTINUE_MAX_WALL_SECONDS = 30.0
V6_MEANINGFUL_BOUNDARY_EVENTS = frozenset(
    {"CRISIS_ACTIVATED", "CRISIS_CHECKPOINT_ENTERED", "CRISIS_SETTLED"}
)
PRODUCT_CONTENT_MISMATCH = "这份卷册由不同版本的内容创建，当前版本无法可靠回放。"


class ProductWorldlineRequest(BaseModel):
    """Create the current V6 Volume Worldline."""

    model_config = ConfigDict(extra="forbid")

    live: bool = False


class ProductInhabitRequest(BaseModel):
    lifetime_id: str = Field(min_length=1, max_length=128)


class ProductDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["KEEP", "CHANGE", "WAIT"]
    text: str = Field(default="", max_length=4000)


class ProductSealRequest(BaseModel):
    reason: str = Field(default="user_exit", max_length=256)


def build_product_router(host_factory: Callable[[], ChronicleHost]) -> APIRouter:
    """Expose the current V6 Volume product contract."""

    router = APIRouter(prefix="/api", tags=["v6-product"])

    def active_host() -> ChronicleHost:
        return host_factory()

    def volume_row(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] != WorldlineKind.VOLUME.value:
            raise HTTPException(status_code=404, detail="Volume Worldline not found")
        if row.get("runtime_mode") == "live" and row.get("runtime_phase") == "FAILED":
            raise HTTPException(
                status_code=503,
                detail="Live Volume runtime is unavailable; reconcile it before continuing",
            )
        try:
            active.volume_runtime.assert_content_compatible(row)
        except VolumeRuntimeConflict as exc:
            raise HTTPException(status_code=409, detail=PRODUCT_CONTENT_MISMATCH) from exc
        return row

    def projection(active: ChronicleHost) -> ProductProjection:
        return ProductProjection(active, volume_row)

    def classify_error(exc: Exception) -> HTTPException:
        if isinstance(exc, HTTPException):
            return exc
        if isinstance(exc, VolumeRuntimeConflict):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, VolumeRuntimeError):
            status = 404 if "not found" in str(exc).lower() else 400
            return HTTPException(status_code=status, detail=str(exc))
        if isinstance(exc, HermesRuntimeError):
            return HTTPException(status_code=503, detail=str(exc))
        return HTTPException(status_code=500, detail=str(exc))

    def due_wakes(active: ChronicleHost, worldline_id: str) -> list[dict[str, Any]]:
        row = volume_row(active, worldline_id)
        return [
            wake
            for wake in active.db.subject_wakes(worldline_id, tick=int(row["current_tick"]))
            if wake["status"] in {"QUEUED", "WAITING_HUMAN"}
        ]

    def resolve_agent_wakes(active: ChronicleHost, worldline_id: str) -> list[dict[str, Any]]:
        """Resolve one frozen moment, using live Hermes only for live Volumes."""

        state = active.volume_runtime.worldline(worldline_id)
        pending = state["projection"].get("pending_moment")
        if not pending:
            return []
        events: list[dict[str, Any]] = []
        live_driver = None
        if state["worldline"].get("runtime_mode") == "live":
            active.volume_runtime.ensure_live_runtime(worldline_id)
            live_driver = HermesVolumeActorDriver(active.config, active.db)
        for wake_id in pending["wake_ids"]:
            wake = active.db.crisis_wake(wake_id)
            if wake is None or wake["status"] == "STAGED":
                continue
            lifetime = active.db.worldline_lifetime_by_id(worldline_id, str(wake["actor_id"]))
            lifetime = lifetime or active.db.worldline_lifetime(
                worldline_id, str(wake["actor_id"])
            )
            if lifetime is None:
                continue
            if lifetime["controller"] != "AGENT":
                continue
            if live_driver is not None:
                result = live_driver.run_wake(wake, wake["frozen_perspective"])
                events.append({"wake_id": wake_id, **result})
                continue
            staged = active.volume_runtime.stage_intent(
                worldline_id,
                lifetime["id"],
                {"type": "wait"},
                source="human" if lifetime["controller"] == "HUMAN" else "agent",
            )
            events.append(staged)
        staged_wakes = [
            active.db.crisis_wake(wake_id)
            for wake_id in pending["wake_ids"]
        ]
        if staged_wakes and all(wake and wake["status"] == "STAGED" for wake in staged_wakes):
            committed = active.volume_runtime.commit_pending_moment(worldline_id)
            events.extend(committed.get("events", []))
        return events

    def pending_for_human(active: ChronicleHost, worldline_id: str) -> dict[str, Any] | None:
        row = volume_row(active, worldline_id)
        human_id = projection(active).lifetime_seat(
            worldline_id, str(row.get("human_lifetime_id") or "")
        )
        if not human_id:
            return None
        state = active.volume_runtime.worldline(worldline_id)
        pending = state["projection"].get("pending_moment")
        if not pending:
            return None
        wake_ids = set(pending.get("wake_ids", []))
        if any(
            str(wake["actor_id"]) == human_id
            for wake in active.db.subject_wakes(worldline_id)
            if str(wake["id"]) in wake_ids
        ):
            return pending
        return None

    def pending_human_wake(active: ChronicleHost, worldline_id: str) -> dict[str, Any] | None:
        row = volume_row(active, worldline_id)
        human_id = projection(active).lifetime_seat(
            worldline_id, str(row.get("human_lifetime_id") or "")
        )
        pending = pending_for_human(active, worldline_id)
        if pending is None:
            return None
        return next(
            (
                active.db.crisis_wake(wake_id)
                for wake_id in pending.get("wake_ids", [])
                if (
                    wake := active.db.crisis_wake(str(wake_id))
                ) is not None
                and str(wake.get("actor_id", "")) == human_id
            ),
            None,
        )

    async def continue_until_boundary(
        active: ChronicleHost, worldline_id: str
    ) -> dict[str, Any]:
        """Advance Host-owned ticks until Human judgment or a bounded stop condition."""

        started = time.monotonic()
        events: list[dict[str, Any]] = []
        advanced_ticks = 0
        agent_deliberations = 0
        stopped_at = "no_future_trigger"

        while True:
            row = volume_row(active, worldline_id)
            state = active.volume_runtime.worldline(worldline_id)
            pending = state["projection"].get("pending_moment")
            if pending:
                if pending_for_human(active, worldline_id) is not None:
                    stopped_at = "human_judgment"
                    break
                pending_wakes = [
                    active.db.crisis_wake(wake_id)
                    for wake_id in pending.get("wake_ids", [])
                ]
                agent_wakes = [
                    wake
                    for wake in pending_wakes
                    if wake is not None
                    and str(wake.get("actor_id", ""))
                    != str(row.get("human_lifetime_id", ""))
                ]
                if agent_deliberations + len(agent_wakes) > V6_CONTINUE_MAX_AGENT_DELIBERATIONS:
                    stopped_at = "safety_cap"
                    break
                events.extend(
                    await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
                )
                agent_deliberations += len(agent_wakes)
                continue

            boundary = await asyncio.to_thread(active.volume_runtime.boundary, worldline_id)
            if boundary["boundary"].get("ready"):
                stopped_at = "volume_boundary"
                break
            if advanced_ticks >= V6_CONTINUE_MAX_TICKS:
                stopped_at = "safety_cap"
                break
            if time.monotonic() - started >= V6_CONTINUE_MAX_WALL_SECONDS:
                stopped_at = "safety_cap"
                break

            iteration_start = len(events)
            result = await asyncio.to_thread(active.volume_runtime.advance_one, worldline_id)
            events.extend(result.get("events", []))
            if not result.get("advanced"):
                stopped_at = "no_future_trigger"
                break
            advanced_ticks += 1

            wakes = due_wakes(active, worldline_id)
            if wakes:
                frozen = await asyncio.to_thread(
                    active.volume_runtime.freeze_pending_moment, worldline_id
                )
                frozen_event = next(
                    (
                        event
                        for event in reversed(active.db.worldline_events(worldline_id))
                        if event["event_type"] == "MOMENT_FROZEN"
                        and event.get("payload", {}).get("moment_id") == frozen["moment_id"]
                    ),
                    None,
                )
                if frozen_event is not None:
                    events.append(frozen_event)
                if pending_for_human(active, worldline_id) is not None:
                    stopped_at = "human_judgment"
                    break
                pending_wakes = [
                    active.db.crisis_wake(wake_id)
                    for wake_id in frozen["pending_moment"].get("wake_ids", [])
                ]
                agent_wakes = [wake for wake in pending_wakes if wake is not None]
                if agent_deliberations + len(agent_wakes) > V6_CONTINUE_MAX_AGENT_DELIBERATIONS:
                    stopped_at = "safety_cap"
                    break
                events.extend(
                    await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
                )
                agent_deliberations += len(agent_wakes)
                if pending_for_human(active, worldline_id) is not None:
                    stopped_at = "human_judgment"
                    break

            if any(
                str(event.get("event_type", "")) in V6_MEANINGFUL_BOUNDARY_EVENTS
                for event in events[iteration_start:]
            ):
                stopped_at = "knot_boundary"
                break

        state = active.volume_runtime.worldline(worldline_id)
        view = projection(active)
        return {
            "worldline": view.public_worldline(state["worldline"]),
            "world": view.public_world(worldline_id),
            "pending_moment": state["projection"].get("pending_moment"),
            "advanced": advanced_ticks > 0,
            "advanced_ticks": advanced_ticks,
            "continue_status": stopped_at,
            "attention": volume_attention(events),
        }

    @router.post("/worldlines")
    async def create_worldline(request: ProductWorldlineRequest) -> dict[str, Any]:
        active = active_host()
        if not request.live and not active.config.dev:
            raise HTTPException(
                status_code=409,
                detail="正式卷册需要真实运行模式；fixture 只在开发模式开放。",
            )
        try:
            existing = active.db.active_volume_worldline()
            if existing is not None:
                resumable = request.live and existing.get("runtime_mode") == "live" and existing.get(
                    "runtime_phase"
                ) in {"BOOTSTRAPPING", "RECONCILING", "FAILED"}
                if not resumable:
                    raise VolumeRuntimeConflict("an active Volume Worldline already exists")
                await asyncio.to_thread(
                    active.volume_runtime.ensure_live_runtime,
                    str(existing["id"]),
                )
                worldline_id = str(existing["id"])
            else:
                created = await asyncio.to_thread(
                    active.volume_runtime.create,
                    runtime_mode="live" if request.live else "fixture",
                )
                worldline_id = str(created["worldline"]["id"])
                await asyncio.to_thread(
                    active.volume_runtime.reconcile_crisis_envelopes,
                    worldline_id,
                )
                if request.live:
                    await asyncio.to_thread(
                        active.volume_runtime.ensure_live_runtime,
                        worldline_id,
                    )
            view = projection(active)
            return {
                "worldline": view.public_worldline(active.db.worldline(worldline_id) or {}),
                "world": view.public_world(worldline_id),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/active")
    async def active_worldline() -> dict[str, Any]:
        active = active_host()
        row = active.db.active_volume_worldline()
        if row is None:
            return {"active": None}
        row = volume_row(active, str(row["id"]))
        view = projection(active)
        return {
            "active": view.public_worldline(row),
            "world": view.public_world(str(row["id"])),
        }

    @router.get("/worldlines")
    async def worldlines() -> dict[str, Any]:
        active = active_host()
        view = projection(active)
        sealed: list[dict[str, Any]] = []
        for row in active.db.worldlines(status="SEALED"):
            if row["kind"] != WorldlineKind.VOLUME.value:
                continue
            sealed.append(view.public_worldline(volume_row(active, str(row["id"]))))
        return {"worldlines": sealed}

    @router.get("/worldlines/{worldline_id}/world")
    async def world(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        volume_row(active, worldline_id)
        try:
            return projection(active).public_world(worldline_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/follow/{lifetime_id}")
    async def follow(worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        active = active_host()
        volume_row(active, worldline_id)
        try:
            return projection(active).public_follow(worldline_id, lifetime_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/desk")
    async def desk(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        try:
            return projection(active).public_desk(
                worldline_id, pending_for_human(active, worldline_id)
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/inhabit")
    async def inhabit(worldline_id: str, request: ProductInhabitRequest) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            result = await asyncio.to_thread(
                active.volume_runtime.inhabit, worldline_id, request.lifetime_id
            )
            if active.db.worldline_snapshot(worldline_id, int(row["current_tick"])) is None:
                return result
            state = active.volume_runtime.worldline(worldline_id)
            current_tick = int(state["worldline"]["current_tick"])
            human_seat = projection(active).lifetime_seat(worldline_id, request.lifetime_id)
            has_current_human_wake = any(
                str(wake["actor_id"]) == human_seat
                and int(wake["tick"]) == current_tick
                and wake["status"] in {"QUEUED", "WAITING_HUMAN"}
                for wake in active.db.subject_wakes(worldline_id)
            )
            if not state["projection"].get("pending_moment") and has_current_human_wake:
                await asyncio.to_thread(
                    active.volume_runtime.freeze_pending_moment, worldline_id
                )
            view = projection(active)
            return {
                "worldline": view.public_worldline(active.db.worldline(worldline_id) or {}),
                "world": view.public_world(worldline_id),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/leave")
    async def leave(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            result = await asyncio.to_thread(active.volume_runtime.leave, worldline_id)
            if active.db.worldline_snapshot(worldline_id, int(row["current_tick"])) is None:
                return result
            view = projection(active)
            return {
                "worldline": view.public_worldline(active.db.worldline(worldline_id) or {}),
                "world": view.public_world(worldline_id),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/continue")
    async def continue_worldline(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        try:
            volume_row(active, worldline_id)
            return await continue_until_boundary(active, worldline_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/assist/draft")
    async def assist_draft(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        volume_row(active, worldline_id)
        try:
            wake = pending_human_wake(active, worldline_id)
            perspective = (wake or {}).get("frozen_perspective", {})
            context = perspective.get("context")
            if not isinstance(context, dict):
                return {"available": False}
            stage = "REOPEN" if context.get("current_course") else "FIRST"
            suggestion = await asyncio.to_thread(
                draft_judgment,
                active.config,
                context,
                stage,
            )
            if suggestion is None:
                return {"available": False}
            return {"available": True, "suggestion": suggestion}
        except HTTPException:
            raise
        except Exception:
            return {"available": False}

    @router.post("/worldlines/{worldline_id}/reconsider")
    async def reconsider(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            view = projection(active)
            human_id = view.lifetime_seat(
                worldline_id, str(row.get("human_lifetime_id") or "")
            )
            if not human_id:
                raise VolumeRuntimeConflict("请先进入一段人生")
            await asyncio.to_thread(
                active.volume_runtime.open_voluntary_reconsideration,
                worldline_id,
                human_id,
            )
            state = active.volume_runtime.worldline(worldline_id)
            return {
                "worldline": view.public_worldline(state["worldline"]),
                "world": view.public_world(worldline_id),
                "desk": view.public_desk(
                    worldline_id, pending_for_human(active, worldline_id)
                ),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/decision")
    async def decision(worldline_id: str, request: ProductDecisionRequest) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            view = projection(active)
            human_id = view.lifetime_seat(
                worldline_id, str(row.get("human_lifetime_id") or "")
            )
            if not human_id:
                raise VolumeRuntimeConflict("请先进入一段人生")
            state = active.volume_runtime.worldline(worldline_id)
            human_wake = pending_human_wake(active, worldline_id)
            if human_wake is None:
                raise VolumeRuntimeConflict("当前时刻没有需要你处理的下一步")
            context = active.volume_runtime.lifetime_context(
                worldline_id, human_id, wake_id=human_wake["id"]
            )
            current_course = context.get("current_course")
            if request.action == "KEEP":
                if not current_course:
                    raise VolumeRuntimeConflict("已有判断才能维持原来的打算")
                proposal = {"outcome": "HOLD", "world_actions": []}
                await asyncio.to_thread(
                    active.volume_runtime.stage_deliberation,
                    worldline_id,
                    human_id,
                    proposal,
                    source="human",
                    wake_id=human_wake["id"],
                )
            elif request.action == "CHANGE":
                text = request.text.strip()
                if not text:
                    raise VolumeRuntimeConflict("改主意需要写下新的判断")
                proposal = {
                    "outcome": "REVISE",
                    "course": {
                        "summary": text,
                        "steps": [text],
                    },
                    "world_actions": [],
                }
                await asyncio.to_thread(
                    active.volume_runtime.stage_deliberation,
                    worldline_id,
                    human_id,
                    proposal,
                    source="human",
                    wake_id=human_wake["id"],
                )
            else:
                if current_course:
                    raise VolumeRuntimeConflict("已有判断不能用暂时不定")
                await asyncio.to_thread(
                    active.volume_runtime.stage_intent,
                    worldline_id,
                    human_id,
                    {"type": "wait"},
                    source="human",
                    wake_id=human_wake["id"],
                )
            await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
            state = active.volume_runtime.worldline(worldline_id)
            if state["projection"].get("pending_moment"):
                await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
                state = active.volume_runtime.worldline(worldline_id)
            return {
                "worldline": view.public_worldline(state["worldline"]),
                "world": view.public_world(worldline_id),
                "desk": view.public_desk(
                    worldline_id, pending_for_human(active, worldline_id)
                ),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/archive")
    async def archive(
        worldline_id: str,
        lifetime_id: str | None = Query(default=None, max_length=128),
    ) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        if row["status"] != "SEALED":
            raise HTTPException(status_code=409, detail="卷册尚未到达封存边界")
        try:
            view = projection(active)
            result = view.volume_archive(worldline_id)
            if lifetime_id is not None:
                state = view.volume_state(worldline_id)
                lifetime = next(
                    (
                        item
                        for item in state["lifetimes"]
                        if item["seat"] == lifetime_id or item["id"] == lifetime_id
                    ),
                    None,
                )
                if lifetime is None:
                    raise HTTPException(status_code=404, detail="Lifetime not found")
                result["selected_life"] = view.lifetime_replay(
                    state,
                    lifetime,
                    active.db.worldline_events(worldline_id),
                )
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/seal")
    async def seal(worldline_id: str, request: ProductSealRequest) -> dict[str, Any]:
        active = active_host()
        try:
            volume_row(active, worldline_id)
            return await asyncio.to_thread(
                active.volume_runtime.seal, worldline_id, request.reason
            )
        except Exception as exc:
            raise classify_error(exc) from exc

    return router

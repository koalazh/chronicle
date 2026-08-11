from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .editorial import volume_attention
from .hermes import HermesRuntimeError
from .host import ChronicleHost
from .models import WorldlineKind
from .runtime import WorldlineConflict, WorldlineError
from .volume_runtime import VolumeRuntimeConflict, VolumeRuntimeError


class ProductWorldlineRequest(BaseModel):
    """V5 creates a Volume unless the legacy entry_id compatibility field is used."""

    entry_id: str | None = Field(default=None, max_length=128)
    seat: str = Field(default="A", max_length=16)
    live: bool = False


class ProductInhabitRequest(BaseModel):
    lifetime_id: str = Field(min_length=1, max_length=128)


class ProductDecisionRequest(BaseModel):
    intent: dict[str, Any] = Field(default_factory=dict)
    text: str = Field(default="", max_length=4000)


class ProductSealRequest(BaseModel):
    reason: str = Field(default="user_exit", max_length=256)


def build_product_router(host_factory: Callable[[], ChronicleHost]) -> APIRouter:
    """Expose the V5 product contract while keeping the V4 router readable."""

    router = APIRouter(prefix="/api", tags=["v5-product"])

    def active_host() -> ChronicleHost:
        return host_factory()

    def volume_row(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] != WorldlineKind.VOLUME.value:
            raise HTTPException(status_code=404, detail="Volume Worldline not found")
        return row

    def public_worldline(row: dict[str, Any]) -> dict[str, Any]:
        inhabited = str(row.get("human_lifetime_id") or "")
        if ":lifetime:" in inhabited:
            inhabited = inhabited.rsplit(":lifetime:", 1)[-1]
        return {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "current_tick": int(row["current_tick"]),
            "volume_id": row.get("volume_id", ""),
            "worldline_phase": row.get("worldline_phase", "READY"),
            "inhabited_lifetime_id": inhabited,
        }

    def lifetime_seat(active: ChronicleHost, worldline_id: str, lifetime_id: str) -> str:
        for lifetime in active.db.worldline_lifetimes(worldline_id):
            if lifetime["id"] == lifetime_id or lifetime["seat"] == lifetime_id:
                return str(lifetime["seat"])
        return lifetime_id

    def location_name(active: ChronicleHost, location_id: str) -> str:
        for location in active.volume_runtime.pack.world.locations:
            if location.id == location_id:
                return location.display_name
        return location_id

    def public_lifetime(
        active: ChronicleHost,
        row: dict[str, Any],
        projection: dict[str, Any],
        lifetime: dict[str, Any],
    ) -> dict[str, Any]:
        lifetime_id = str(lifetime["seat"])
        definition = active.volume_runtime.pack.lifetimes.get(lifetime_id)
        current_location = str(projection.get("positions", {}).get(lifetime_id, ""))
        active_ids = set(projection.get("active_crisis_ids", []))
        participant_ids = {
            participant_id
            for crisis_id in active_ids
            for participant_id in projection.get("crisis_instances", {})
            .get(crisis_id, {})
            .get("participants", [])
        }
        reasons: list[str] = []
        if definition and (definition.initial_knowledge or definition.genesis_context):
            reasons.append("有过去")
        if lifetime_id in participant_ids:
            reasons.append("有杠杆")
        if active_ids:
            reasons.append("有未决")
        return {
            "id": lifetime_id,
            "display_name": (definition.display_name if definition else lifetime_id),
            "location": {
                "id": current_location,
                "display_name": location_name(active, current_location),
            },
            "available": bool(active_ids and lifetime_id in participant_ids),
            "availability_reasons": reasons,
            "inhabited": lifetime_id
            == lifetime_seat(active, str(row["id"]), str(row.get("human_lifetime_id") or "")),
        }

    def public_surface(
        active: ChronicleHost,
        pack: Any,
        instance: dict[str, Any],
        projection: dict[str, Any],
    ) -> dict[str, Any]:
        local_projection = {
            "positions": projection.get("positions", {}),
            "messages": [],
            "entities": instance.get("entities", {}),
        }
        visible_entity_ids = {
            *pack.crisis.surface.subject_ids,
            *pack.crisis.surface.context_entity_ids,
        }
        surface = pack.surface_projection(
            local_projection,
            visible_actor_ids=set(pack.participant_ids),
            visible_entity_ids=visible_entity_ids,
            include_messages=False,
        )
        if surface.get("kind") == "POLITICAL":
            for group in ("subjects", "context"):
                for entity in surface.get(group, []):
                    entity.pop("knowledge", None)
                    entity["state_label"] = entity.get("state_label", "")
        surface.pop("messages", None)
        if surface.get("kind") == "SPATIAL":
            for actor in surface.get("actors", []):
                actor["location"] = location_name(active, str(actor.get("location", "")))
        return surface

    def public_world(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        state = active.volume_runtime.worldline(worldline_id)
        row = state["worldline"]
        projection = state["projection"]
        pack = active.volume_runtime.pack
        people = []
        for lifetime in state["lifetimes"]:
            item = public_lifetime(active, row, projection, lifetime)
            people.append(item)

        knots = []
        for crisis_id in projection.get("active_crisis_ids", []):
            instance = projection.get("crisis_instances", {}).get(crisis_id, {})
            crisis_pack = pack.pack(crisis_id)
            knots.append(
                {
                    "id": crisis_id,
                    "title": crisis_pack.crisis.title,
                    "subtitle": crisis_pack.crisis.subtitle,
                    "phase": instance.get("phase", "OPEN"),
                    "activation_tick": int(instance.get("activation_tick", 0)),
                    "participants": [
                        next(
                            (
                                {
                                    "id": person["id"],
                                    "display_name": person["display_name"],
                                    "location": person["location"],
                                }
                                for person in people
                                if person["id"] == participant_id
                            ),
                            {"id": participant_id, "display_name": participant_id},
                        )
                        for participant_id in instance.get("participants", [])
                    ],
                    "surface": public_surface(active, crisis_pack, instance, projection),
                }
            )

        facts = []
        for field_event in projection.get("field_events", []):
            if field_event.get("status") != "APPLIED":
                continue
            facts.append(
                {
                    "id": field_event.get("id", ""),
                    "tick": int(field_event.get("applied_tick", field_event.get("tick", 0))),
                    "title": str(field_event.get("title") or field_event.get("id") or "历史现场"),
                    "content": str(
                        field_event.get("description")
                        or field_event.get("content")
                        or field_event.get("summary")
                        or ""
                    ),
                }
            )
        return {
            "worldline": public_worldline(row),
            "volume": {
                "id": pack.volume.id,
                "title": pack.volume.title,
                "subtitle": pack.volume.subtitle,
                "native_period": pack.volume.native_period,
            },
            "tick": int(projection.get("tick", row["current_tick"])),
            "locations": [
                {
                    "id": location.id,
                    "display_name": location.display_name,
                }
                for location in pack.world.locations
            ],
            "people": people,
            "public_facts": facts,
            "active_knots": knots,
        }

    def public_lifetimes(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        state = active.volume_runtime.worldline(worldline_id)
        return {
            "worldline": public_worldline(state["worldline"]),
            "lifetimes": [
                public_lifetime(active, state["worldline"], state["projection"], lifetime)
                for lifetime in state["lifetimes"]
            ],
        }

    def public_follow(active: ChronicleHost, worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        state = active.volume_runtime.worldline(worldline_id)
        lifetime = next(
            (item for item in state["lifetimes"] if item["seat"] == lifetime_id), None
        )
        if lifetime is None:
            raise HTTPException(status_code=404, detail="Lifetime not found")
        public = public_lifetime(active, state["worldline"], state["projection"], lifetime)
        labels = {
            "CRISIS_ACTIVATED": "一处局势开始收紧",
            "CRISIS_CHECKPOINT_ENTERED": "进入一个未决节点",
            "FIELD_EVENT_APPLIED": "公共历史向前推进",
            "MESSAGE_DISPATCHED": "发出一项公开声明",
            "MESSAGE_DELIVERED": "收到一项外部消息",
            "LIFETIME_INHABITED": "有人接过这段人生",
            "LIFETIME_LEFT": "这段人生暂时交还世界",
            "CRISIS_SETTLED": "一处局势留下结果",
            "MOMENT_COMMITTED": "一个时刻完成落笔",
        }
        trace = []
        for event in active.db.worldline_events(worldline_id):
            event_type = str(event["event_type"])
            if event_type not in labels:
                continue
            payload = event.get("payload", {})
            if event_type not in {
                "CRISIS_ACTIVATED",
                "CRISIS_CHECKPOINT_ENTERED",
                "FIELD_EVENT_APPLIED",
                "CRISIS_SETTLED",
            } and event.get("seat_id") not in {None, lifetime_id}:
                continue
            item = {
                "id": event["id"],
                "tick": int(event["tick"]),
                "kind": labels[event_type],
            }
            if event_type == "MESSAGE_DISPATCHED" and payload.get("sender") == lifetime_id:
                item["declaration"] = str(payload.get("content", ""))
            trace.append(item)
        return {"worldline": public_worldline(state["worldline"]), "lifetime": public, "trace": trace}

    def public_desk(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        row = volume_row(active, worldline_id)
        lifetime_id = lifetime_seat(active, worldline_id, str(row.get("human_lifetime_id") or ""))
        if not lifetime_id:
            raise HTTPException(status_code=409, detail="请先进入一段人生")
        state = active.volume_runtime.worldline(worldline_id)
        lifetime = next(item for item in state["lifetimes"] if item["seat"] == lifetime_id)
        context = active.volume_runtime.lifetime_context(worldline_id, lifetime_id)
        return {
            "worldline": public_worldline(row),
            "lifetime": public_lifetime(active, row, state["projection"], lifetime),
            "desk": {
                "position": context.get("position", {}),
                "arrivals": context.get("recent_knowledge", []),
                "known": context.get("relevant_evidence", []),
                "uncertainty": context.get("known_uncertainty", []),
                "current_plan": context.get("current_plan", []),
                "active_obligations": context.get("active_obligations", []),
                "role": context.get("role", {}),
            },
        }

    def classify_error(exc: Exception) -> HTTPException:
        if isinstance(exc, (WorldlineConflict, VolumeRuntimeConflict)):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, (WorldlineError, VolumeRuntimeError)):
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
        """Keep fixture progression deterministic without inventing private cognition."""

        state = active.volume_runtime.worldline(worldline_id)
        pending = state["projection"].get("pending_moment")
        if not pending:
            return []
        events: list[dict[str, Any]] = []
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
        human_id = lifetime_seat(active, worldline_id, str(row.get("human_lifetime_id") or ""))
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

    @router.post("/worldlines")
    async def create_worldline(request: ProductWorldlineRequest) -> dict[str, Any]:
        active = active_host()
        if request.entry_id:
            try:
                return await asyncio.to_thread(
                    active.worldline_runtime.create,
                    request.entry_id,
                    request.seat,
                    live=request.live,
                )
            except Exception as exc:
                raise classify_error(exc) from exc
        if not request.live and not active.config.dev:
            raise HTTPException(
                status_code=409,
                detail="正式卷册需要真实运行模式；fixture 只在开发模式开放。",
            )
        try:
            created = await asyncio.to_thread(
                active.volume_runtime.create,
                runtime_mode="live" if request.live else "fixture",
            )
            for reference in active.volume_runtime.pack.volume.crises:
                await asyncio.to_thread(
                    active.volume_runtime.activate_crisis,
                    created["worldline"]["id"],
                    reference.id,
                )
            return {
                "worldline": public_worldline(active.db.worldline(created["worldline"]["id"]) or {}),
                "world": public_world(active, created["worldline"]["id"]),
                "lifetimes": public_lifetimes(active, created["worldline"]["id"]),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/active")
    async def active_worldline() -> dict[str, Any]:
        active = active_host()
        row = active.db.active_volume_worldline()
        if row is None:
            return {"active": await asyncio.to_thread(active.worldline_runtime.active)}
        return {
            "active": public_worldline(row),
            "world": public_world(active, row["id"]),
        }

    @router.get("/worldlines")
    async def worldlines() -> dict[str, Any]:
        active = active_host()
        if active.db.active_volume_worldline() is None:
            return {"worldlines": await asyncio.to_thread(active.worldline_runtime.sealed)}
        return {
            "worldlines": [
                public_worldline(row)
                for row in active.db.worldlines(status="SEALED")
                if row["kind"] == WorldlineKind.VOLUME.value
            ]
        }

    @router.get("/worldlines/{worldline_id}/world")
    async def world(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        volume_row(active, worldline_id)
        try:
            return public_world(active, worldline_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/lifetimes")
    async def lifetimes(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] != WorldlineKind.VOLUME.value:
            return await asyncio.to_thread(active.worldline_runtime.lifetimes, worldline_id)
        try:
            return public_lifetimes(active, worldline_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/follow/{lifetime_id}")
    async def follow(worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        active = active_host()
        volume_row(active, worldline_id)
        try:
            return public_follow(active, worldline_id, lifetime_id)
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/desk")
    async def desk(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        try:
            return public_desk(active, worldline_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/inhabit")
    async def inhabit(worldline_id: str, request: ProductInhabitRequest) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        try:
            result = await asyncio.to_thread(
                active.worldline_runtime.inhabit, worldline_id, request.lifetime_id
            )
            if row["kind"] != WorldlineKind.VOLUME.value:
                return result
            if active.db.worldline_snapshot(worldline_id, int(row["current_tick"])) is None:
                return result
            return {
                "worldline": public_worldline(active.db.worldline(worldline_id) or {}),
                "world": public_world(active, worldline_id),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/leave")
    async def leave(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        try:
            result = await asyncio.to_thread(active.worldline_runtime.leave, worldline_id)
            if row["kind"] != WorldlineKind.VOLUME.value:
                return result
            if active.db.worldline_snapshot(worldline_id, int(row["current_tick"])) is None:
                return result
            return {
                "worldline": public_worldline(active.db.worldline(worldline_id) or {}),
                "world": public_world(active, worldline_id),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/continue")
    async def continue_worldline(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            events: list[dict[str, Any]] = []
            if pending_for_human(active, worldline_id):
                return {
                    "worldline": public_worldline(row),
                    "world": public_world(active, worldline_id),
                    "pending_moment": active.volume_runtime.worldline(worldline_id)[
                        "projection"
                    ].get("pending_moment"),
                    "attention": volume_attention([]),
                }
            result = await asyncio.to_thread(active.volume_runtime.advance_one, worldline_id)
            events.extend(result.get("events", []))
            wakes = due_wakes(active, worldline_id)
            if wakes:
                frozen = await asyncio.to_thread(
                    active.volume_runtime.freeze_pending_moment, worldline_id
                )
                events.append(frozen)
                if pending_for_human(active, worldline_id) is None:
                    events.extend(await asyncio.to_thread(resolve_agent_wakes, active, worldline_id))
            state = active.volume_runtime.worldline(worldline_id)
            return {
                "worldline": public_worldline(state["worldline"]),
                "world": public_world(active, worldline_id),
                "pending_moment": state["projection"].get("pending_moment"),
                "advanced": bool(result.get("advanced")),
                "attention": volume_attention(events),
            }
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.post("/worldlines/{worldline_id}/decision")
    async def decision(worldline_id: str, request: ProductDecisionRequest) -> dict[str, Any]:
        active = active_host()
        row = volume_row(active, worldline_id)
        try:
            human_id = lifetime_seat(active, worldline_id, str(row.get("human_lifetime_id") or ""))
            if not human_id:
                raise VolumeRuntimeConflict("请先进入一段人生")
            state = active.volume_runtime.worldline(worldline_id)
            if not state["projection"].get("pending_moment"):
                await asyncio.to_thread(active.volume_runtime.freeze_pending_moment, worldline_id)
                state = active.volume_runtime.worldline(worldline_id)
            if pending_for_human(active, worldline_id) is None:
                raise VolumeRuntimeConflict("当前时刻没有需要你处理的下一步")
            intent = dict(request.intent)
            if not intent:
                if request.text.strip():
                    intent = {
                        "type": "update_plan",
                        "objective": request.text.strip(),
                        "steps": [request.text.strip()],
                    }
                else:
                    intent = {"type": "wait"}
            await asyncio.to_thread(
                active.volume_runtime.stage_intent,
                worldline_id,
                human_id,
                intent,
                source="human",
            )
            await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
            state = active.volume_runtime.worldline(worldline_id)
            if state["projection"].get("pending_moment"):
                await asyncio.to_thread(resolve_agent_wakes, active, worldline_id)
                state = active.volume_runtime.worldline(worldline_id)
            return {
                "worldline": public_worldline(state["worldline"]),
                "world": public_world(active, worldline_id),
                "desk": public_desk(active, worldline_id),
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise classify_error(exc) from exc

    @router.get("/worldlines/{worldline_id}/archive")
    async def archive(worldline_id: str) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] != WorldlineKind.VOLUME.value:
            return await asyncio.to_thread(active.worldline_runtime.debrief, worldline_id)
        return {
            "worldline": public_worldline(row),
            "events": [
                {
                    "id": event["id"],
                    "tick": int(event["tick"]),
                    "kind": str(event["event_type"]),
                }
                for event in active.db.worldline_events(worldline_id)
            ],
        }

    @router.post("/worldlines/{worldline_id}/seal")
    async def seal(worldline_id: str, request: ProductSealRequest) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] == WorldlineKind.VOLUME.value:
            raise HTTPException(status_code=409, detail="卷册尚未到达封存边界")
        try:
            return await asyncio.to_thread(
                active.worldline_runtime.seal, worldline_id, request.reason
            )
        except Exception as exc:
            raise classify_error(exc) from exc

    return router

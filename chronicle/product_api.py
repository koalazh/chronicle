from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .editorial import volume_attention
from .hermes import HermesRuntimeError
from .host import ChronicleHost
from .models import WorldlineKind
from .runtime import WorldlineConflict, WorldlineError
from .volume_live import HermesVolumeActorDriver
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

    def volume_state(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        row = volume_row(active, worldline_id)
        snapshot = active.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        return {
            "worldline": row,
            "lifetimes": active.db.worldline_lifetimes(worldline_id),
            "crisis_instances": active.db.crisis_instances(worldline_id),
            "projection": snapshot["projection"],
        }

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
        state = volume_state(active, worldline_id)
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
        state = volume_state(active, worldline_id)
        return {
            "worldline": public_worldline(state["worldline"]),
            "lifetimes": [
                public_lifetime(active, state["worldline"], state["projection"], lifetime)
                for lifetime in state["lifetimes"]
            ],
        }

    def public_follow(active: ChronicleHost, worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        state = volume_state(active, worldline_id)
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

    replay_labels = {
        "WORLDLINE_CREATED": "卷册展开",
        "WORLD_INITIALIZED": "共同世界成形",
        "LIFETIME_GENESIS_ESTABLISHED": "一段人生进入卷册",
        "CRISIS_ACTIVATED": "一处局势开始收紧",
        "CRISIS_CHECKPOINT_ENTERED": "一个未决节点进入视野",
        "CRISIS_PRESSURE_APPLIED": "外部压力改变了局面",
        "FIELD_EVENT_APPLIED": "公共历史向前推进",
        "MESSAGE_DISPATCHED": "一项声明发出",
        "MESSAGE_DELIVERED": "一项消息抵达",
        "LIFETIME_INHABITED": "有人接过这段人生",
        "LIFETIME_LEFT": "这段人生暂时交还世界",
        "PLAN_UPDATED": "计划发生变化",
        "BELIEF_UPDATED": "一个判断留下证据",
        "HUMAN_INTENT_STAGED": "一个决定被提出",
        "AGENT_INTENT_STAGED": "一个决定被提出",
        "CRISIS_SETTLED": "一处局势留下结果",
        "MOMENT_COMMITTED": "一个时刻完成落笔",
        "VOLUME_SEALED": "卷册到达结构边界",
    }

    def replay_event_text(active: ChronicleHost, event: dict[str, Any]) -> str:
        event_type = str(event["event_type"])
        payload = event.get("payload", {})
        if event_type == "CRISIS_ACTIVATED":
            crisis = active.volume_runtime.pack.packs.get(str(payload.get("crisis_id", "")))
            return crisis.crisis.title if crisis else "一处局势开始收紧"
        if event_type == "CRISIS_CHECKPOINT_ENTERED":
            crisis = active.volume_runtime.pack.packs.get(str(payload.get("crisis_id", "")))
            return crisis.crisis.subtitle if crisis else "一个未决节点进入视野"
        if event_type == "FIELD_EVENT_APPLIED":
            field = payload.get("field_event", {})
            if field.get("id") == "north-south-recognition-bridge":
                return "北方军情公开记录进入南京可接触的公开范围"
            return str(field.get("title") or field.get("id") or "公共历史向前推进")
        if event_type == "CRISIS_PRESSURE_APPLIED":
            pressure = payload.get("pressure", {})
            return str(pressure.get("title") or "外部压力改变了局面")
        if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            source = str(payload.get("source", ""))
            if source == "historical_field":
                return str(payload.get("content", "一项公开军情抵达"))
            return "一项消息抵达" if event_type == "MESSAGE_DELIVERED" else "一项声明发出"
        if event_type == "CRISIS_SETTLED":
            outcome = payload.get("outcome", {})
            return str(outcome.get("summary") or "事情已经成为这样。")
        if event_type in {"PLAN_UPDATED", "HUMAN_INTENT_STAGED", "AGENT_INTENT_STAGED"}:
            plan = payload.get("plan") or payload.get("intent") or {}
            return str(plan.get("objective") or replay_labels[event_type])
        if event_type == "BELIEF_UPDATED":
            return str(payload.get("assessment") or replay_labels[event_type])
        return replay_labels.get(event_type, "一项世界事实发生了变化")

    def public_replay_event(active: ChronicleHost, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(event["event_type"])
        payload = event.get("payload", {})
        if event_type == "CRISIS_PRESSURE_APPLIED":
            visibility = str(payload.get("pressure", {}).get("visibility", ""))
            if visibility not in {"PUBLIC", "SHARED"}:
                return None
        if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            if str(payload.get("source", "")) != "historical_field":
                return None
        if event_type not in {
            "WORLDLINE_CREATED",
            "WORLD_INITIALIZED",
            "LIFETIME_GENESIS_ESTABLISHED",
            "CRISIS_ACTIVATED",
            "CRISIS_CHECKPOINT_ENTERED",
            "CRISIS_PRESSURE_APPLIED",
            "FIELD_EVENT_APPLIED",
            "MESSAGE_DISPATCHED",
            "MESSAGE_DELIVERED",
            "LIFETIME_INHABITED",
            "LIFETIME_LEFT",
            "CRISIS_SETTLED",
            "MOMENT_COMMITTED",
            "VOLUME_SEALED",
        }:
            return None
        item = {
            "id": str(event["id"]),
            "tick": int(event["tick"]),
            "kind": replay_labels.get(event_type, "世界事实"),
            "text": replay_event_text(active, event),
        }
        if event_type == "CRISIS_SETTLED":
            item["meaning"] = True
        return item

    def lifetime_replay_event(
        active: ChronicleHost, event: dict[str, Any], lifetime_id: str
    ) -> dict[str, Any] | None:
        public = public_replay_event(active, event)
        if public is not None:
            return public
        payload = event.get("payload", {})
        event_type = str(event["event_type"])
        visible = event.get("seat_id") == lifetime_id
        visible = visible or payload.get("sender") == lifetime_id
        visible = visible or payload.get("recipient") == lifetime_id
        explicit_visibility = payload.get("visibility")
        visible = visible or isinstance(explicit_visibility, list) and lifetime_id in explicit_visibility
        if not visible or event_type not in replay_labels:
            return None
        return {
            "id": str(event["id"]),
            "tick": int(event["tick"]),
            "kind": replay_labels[event_type],
            "text": replay_event_text(active, event),
            "private_to_lifetime": True,
        }

    def lifetime_replay(
        active: ChronicleHost,
        state: dict[str, Any],
        lifetime: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lifetime_id = str(lifetime["seat"])
        items = [
            item
            for event in events
            if (item := lifetime_replay_event(active, event, lifetime_id)) is not None
        ]
        dispatches = {
            str(event.get("payload", {}).get("id", "")): event
            for event in events
            if event.get("event_type") == "MESSAGE_DISPATCHED"
            and event.get("payload", {}).get("recipient") == lifetime_id
        }
        deliveries = {
            str(event.get("payload", {}).get("message_id", "")): event
            for event in events
            if event.get("event_type") == "MESSAGE_DELIVERED"
            and event.get("payload", {}).get("recipient") == lifetime_id
        }
        later_known = []
        unknown_at_time = []
        known_at_time = []
        for message_id, dispatch in dispatches.items():
            delivery = deliveries.get(message_id)
            if delivery is None:
                unknown_at_time.append(
                    {
                        "event_id": str(dispatch["id"]),
                        "happened_tick": int(dispatch["tick"]),
                        "known_tick": None,
                        "text": "一封消息在卷册结束时仍未抵达。",
                    }
                )
                continue
            delivery_item = lifetime_replay_event(active, delivery, lifetime_id)
            if delivery_item is None:
                continue
            delivery_item = {**delivery_item, "known_at_tick": int(delivery["tick"])}
            known_at_time.append(delivery_item)
            if int(dispatch["tick"]) < int(delivery["tick"]):
                later_known.append(
                    {
                        "event_id": str(dispatch["id"]),
                        "known_event_id": str(delivery["id"]),
                        "happened_tick": int(dispatch["tick"]),
                        "known_tick": int(delivery["tick"]),
                        "text": delivery_item["text"],
                    }
                )
                unknown_at_time.append(
                    {
                        "event_id": str(dispatch["id"]),
                        "happened_tick": int(dispatch["tick"]),
                        "known_tick": int(delivery["tick"]),
                        "text": "一封消息在抵达之前仍处于在途状态。",
                    }
                )
        return {
            "id": lifetime_id,
            "display_name": public_lifetime(
                active, state["worldline"], state["projection"], lifetime
            )["display_name"],
            "items": items,
            "known_at_time": known_at_time,
            "later_known": later_known,
            "unknown_at_time": unknown_at_time,
        }

    def volume_archive(active: ChronicleHost, worldline_id: str) -> dict[str, Any]:
        state = volume_state(active, worldline_id)
        events = active.db.worldline_events(worldline_id)
        public_items = [
            item
            for event in events
            if (item := public_replay_event(active, event)) is not None
        ]
        ledger = []
        for event in events:
            public_item = public_replay_event(active, event)
            ledger.append(
                {
                    **(
                        public_item
                        or {
                            "id": str(event["id"]),
                            "tick": int(event["tick"]),
                            "kind": "主体内部记录",
                            "text": "一项未向公共世界公开的主体记录。",
                        }
                    ),
                    "public": public_item is not None,
                }
            )
        sealed_event = next(
            (event for event in reversed(events) if event["event_type"] == "VOLUME_SEALED"),
            None,
        )
        boundary = (sealed_event or {}).get("payload", {}).get("boundary") or {}
        return {
            "available": True,
            "worldline": public_worldline(state["worldline"]),
            "volume": {
                "id": active.volume_runtime.pack.volume.id,
                "title": active.volume_runtime.pack.volume.title,
                "subtitle": active.volume_runtime.pack.volume.subtitle,
            },
            "world": public_world(active, worldline_id),
            "boundary": boundary,
            "events": ledger,
            "replay": {
                "public": {"items": public_items},
            },
        }

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
            if request.live:
                await asyncio.to_thread(
                    active.volume_runtime.ensure_live_runtime,
                    created["worldline"]["id"],
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
            legacy_worldlines = await asyncio.to_thread(active.worldline_runtime.sealed)
            volume_worldlines = [
                public_worldline(active.db.worldline(row["id"]) or row)
                for row in active.db.worldlines(status="SEALED")
                if row["kind"] == WorldlineKind.VOLUME.value
            ]
            return {"worldlines": [*legacy_worldlines, *volume_worldlines]}
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
            state = active.volume_runtime.worldline(worldline_id)
            if state["projection"].get("pending_moment"):
                events.extend(await asyncio.to_thread(resolve_agent_wakes, active, worldline_id))
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
    async def archive(
        worldline_id: str,
        lifetime_id: str | None = Query(default=None, max_length=128),
    ) -> dict[str, Any]:
        active = active_host()
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] != WorldlineKind.VOLUME.value:
            return await asyncio.to_thread(active.worldline_runtime.debrief, worldline_id)
        if row["status"] != "SEALED":
            raise HTTPException(status_code=409, detail="卷册尚未到达封存边界")
        try:
            result = volume_archive(active, worldline_id)
            if lifetime_id is not None:
                state = volume_state(active, worldline_id)
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
                result["replay"]["lifetime"] = lifetime_replay(
                    active,
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
        row = active.db.worldline(worldline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Worldline not found")
        if row["kind"] == WorldlineKind.VOLUME.value:
            try:
                return await asyncio.to_thread(
                    active.volume_runtime.seal, worldline_id, request.reason
                )
            except Exception as exc:
                raise classify_error(exc) from exc
        try:
            return await asyncio.to_thread(
                active.worldline_runtime.seal, worldline_id, request.reason
            )
        except Exception as exc:
            raise classify_error(exc) from exc

    return router

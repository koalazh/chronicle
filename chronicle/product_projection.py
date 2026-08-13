from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from .host import ChronicleHost
from .volume_runtime import VolumeRuntimeError

VolumeRow = Callable[[ChronicleHost, str], dict[str, Any]]


class ProductProjection:
    """Compile read-only Runtime state into the current product view contract."""

    def __init__(self, active: ChronicleHost, volume_row: VolumeRow):
        self.active = active
        self._volume_row = volume_row

    def volume_state(self, worldline_id: str) -> dict[str, Any]:
        row = self._volume_row(self.active, worldline_id)
        snapshot = self.active.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        return {
            "worldline": row,
            "lifetimes": self.active.db.worldline_lifetimes(worldline_id),
            "crisis_instances": self.active.db.crisis_instances(worldline_id),
            "projection": snapshot["projection"],
        }

    @staticmethod
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

    def lifetime_seat(self, worldline_id: str, lifetime_id: str) -> str:
        for lifetime in self.active.db.worldline_lifetimes(worldline_id):
            if lifetime["id"] == lifetime_id or lifetime["seat"] == lifetime_id:
                return str(lifetime["seat"])
        return lifetime_id

    def location_name(self, location_id: str) -> str:
        for location in self.active.volume_runtime.pack.world.locations:
            if location.id == location_id:
                return location.display_name
        return "位置未明"

    def public_copy(self, value: Any) -> str:
        """Replace known internal identifiers in user-authored/public replay copy."""

        result = str(value or "")
        replacements: dict[str, str] = {}
        pack = self.active.volume_runtime.pack
        for crisis_pack in pack.packs.values():
            replacements[crisis_pack.crisis.id] = crisis_pack.crisis.title
            replacements.update(
                {actor.id: actor.display_name for actor in crisis_pack.crisis.actors}
            )
            replacements.update(
                {
                    assertion.id: str(assertion.normalized_evidence or assertion.claim)
                    for assertion in crisis_pack.assertions
                }
            )
        replacements.update(
            {lifetime.id: lifetime.display_name for lifetime in pack.lifetimes.values()}
        )
        replacements.update(
            {location.id: location.display_name for location in pack.world.locations}
        )
        replacements.update(
            {entity.id: entity.display_name for entity in pack.world.entities}
        )
        for field in pack.world.historical_field:
            field_id = str(field.get("id", ""))
            title = str(field.get("title") or "历史现场")
            if field_id:
                replacements[field_id] = title
        for identifier in sorted(replacements, key=len, reverse=True):
            result = result.replace(identifier, replacements[identifier])
        return result

    def product_item_text(self, item: Any) -> str:
        """Return readable product copy without falling back to internal IDs."""

        def readable(value: Any) -> str:
            if not isinstance(value, str):
                return ""
            candidate = value.strip()
            if not candidate:
                return ""
            resolved = self.public_copy(candidate)
            if resolved != candidate:
                return resolved
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,127}", candidate) and (
                any(character.isdigit() for character in candidate)
                or "_" in candidate
                or "-" in candidate
                or candidate.isupper()
            ):
                return ""
            return candidate

        if isinstance(item, str):
            return readable(item) or "一项已知事实。"
        if isinstance(item, dict):
            for key in (
                "content",
                "observation",
                "text",
                "summary",
                "description",
                "declaration",
                "reason",
                "title",
            ):
                value = readable(item.get(key))
                if value:
                    return value
            nested = item.get("value")
            if isinstance(nested, dict):
                for key in ("objective", "content", "description", "reason", "summary"):
                    value = readable(nested.get(key))
                    if value:
                        return value
            labels = {
                "MESSAGE": "一封消息",
                "OBSERVATION": "一项观察",
                "INVESTIGATION": "一项调查回报",
                "OPERATION": "一项行动",
                "PLAN": "一项计划",
                "COMMITMENT": "一项约定",
                "REVISIT": "一次重新判断",
            }
            return labels.get(str(item.get("kind", "")).upper(), "这一项暂未留下文字说明")
        return readable(item) or "这一项暂未留下文字说明"

    def product_items(self, items: Any) -> list[dict[str, str]]:
        if not isinstance(items, list):
            return []
        return [{"text": self.product_item_text(item)} for item in items]

    def public_lifetime(
        self,
        row: dict[str, Any],
        projection: dict[str, Any],
        lifetime: dict[str, Any],
    ) -> dict[str, Any]:
        lifetime_id = str(lifetime["seat"])
        definition = self.active.volume_runtime.pack.lifetimes.get(lifetime_id)
        current_location = str(projection.get("positions", {}).get(lifetime_id, ""))
        eligibility = self.active.volume_runtime.presence_eligibility(
            str(row["id"]), lifetime_id
        )
        reason_copy = {
            "AVAILABLE": "此刻有未决之事把他推到前台。",
            "ALREADY_INHABITED": "你正在这段人生里。",
            "ANOTHER_LIFETIME_HELD": "你已经从另一个人的位置进入过这一件事。",
            "ACTIVE_CRISIS_PRESENCE_LOCK": "你已经从另一个人的位置进入过这一件事。",
            "NO_CURRENT_QUESTION": "此刻还没有未决之事把他推到前台。",
            "LIFETIME_NOT_ACTIVE": "这段人生暂时无法进入。",
            "WORLDLINE_NOT_ACTIVE": "这一卷已经走到过去。",
        }
        reasons = [
            reason_copy.get(
                str(eligibility["reason_code"]), "此刻还没有可以进入的未决之事。"
            )
        ]
        return {
            "id": lifetime_id,
            "display_name": definition.display_name if definition else "一段人生",
            "location": {
                "id": current_location,
                "display_name": self.location_name(current_location),
            },
            "available": bool(eligibility["allowed"]),
            "availability_reasons": reasons,
            "inhabited": lifetime_id
            == self.lifetime_seat(str(row["id"]), str(row.get("human_lifetime_id") or "")),
        }

    def public_surface(
        self,
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
                actor["location"] = self.location_name(str(actor.get("location", "")))
        return surface

    def public_world(self, worldline_id: str) -> dict[str, Any]:
        state = self.volume_state(worldline_id)
        row = state["worldline"]
        projection = state["projection"]
        pack = self.active.volume_runtime.pack
        people = [
            self.public_lifetime(row, projection, lifetime)
            for lifetime in state["lifetimes"]
        ]

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
                            {"id": participant_id, "display_name": "一位相关人物"},
                        )
                        for participant_id in instance.get("participants", [])
                    ],
                    "surface": self.public_surface(crisis_pack, instance, projection),
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
                    "title": str(field_event.get("title") or "历史现场"),
                    "content": self.public_copy(
                        field_event.get("description")
                        or field_event.get("content")
                        or field_event.get("summary")
                        or ""
                    ),
                }
            )
        return {
            "worldline": self.public_worldline(row),
            "volume": {
                "id": pack.volume.id,
                "title": pack.volume.title,
                "subtitle": pack.volume.subtitle,
                "native_period": pack.volume.native_period,
            },
            "tick": int(projection.get("tick", row["current_tick"])),
            "locations": [
                {"id": location.id, "display_name": location.display_name}
                for location in pack.world.locations
            ],
            "people": people,
            "public_facts": facts,
            "active_knots": knots,
        }

    def public_lifetimes(self, worldline_id: str) -> dict[str, Any]:
        state = self.volume_state(worldline_id)
        return {
            "worldline": self.public_worldline(state["worldline"]),
            "lifetimes": [
                self.public_lifetime(state["worldline"], state["projection"], lifetime)
                for lifetime in state["lifetimes"]
            ],
        }

    def public_follow(self, worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        state = self.volume_state(worldline_id)
        lifetime = next(
            (item for item in state["lifetimes"] if item["seat"] == lifetime_id), None
        )
        if lifetime is None:
            raise HTTPException(status_code=404, detail="Lifetime not found")
        public = self.public_lifetime(state["worldline"], state["projection"], lifetime)
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
        for event in self.active.db.worldline_events(worldline_id):
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
            item = {"id": event["id"], "tick": int(event["tick"]), "kind": labels[event_type]}
            if event_type == "MESSAGE_DISPATCHED" and payload.get("sender") == lifetime_id:
                item["declaration"] = self.public_copy(payload.get("content", ""))
            trace.append(item)
        return {
            "worldline": self.public_worldline(state["worldline"]),
            "lifetime": public,
            "trace": trace,
        }

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

    def replay_event_text(self, event: dict[str, Any]) -> str:
        event_type = str(event["event_type"])
        payload = event.get("payload", {})
        if event_type == "CRISIS_ACTIVATED":
            crisis = self.active.volume_runtime.pack.packs.get(str(payload.get("crisis_id", "")))
            return crisis.crisis.title if crisis else "一处局势开始收紧"
        if event_type == "CRISIS_CHECKPOINT_ENTERED":
            crisis = self.active.volume_runtime.pack.packs.get(str(payload.get("crisis_id", "")))
            return crisis.crisis.subtitle if crisis else "一个未决节点进入视野"
        if event_type == "FIELD_EVENT_APPLIED":
            field = payload.get("field_event", {})
            return str(field.get("title") or "一次公共历史观察完成")
        if event_type == "CRISIS_PRESSURE_APPLIED":
            pressure = payload.get("pressure", {})
            return str(pressure.get("title") or "外部压力改变了局面")
        if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            source = str(payload.get("source", ""))
            if source == "historical_field":
                return self.public_copy(payload.get("content", "一项公开军情抵达"))
            return "一项消息抵达" if event_type == "MESSAGE_DELIVERED" else "一项声明发出"
        if event_type == "CRISIS_SETTLED":
            outcome = payload.get("outcome", {})
            return self.public_copy(outcome.get("summary") or "事情已经成为这样。")
        if event_type in {"PLAN_UPDATED", "HUMAN_INTENT_STAGED", "AGENT_INTENT_STAGED"}:
            plan = payload.get("plan") or payload.get("intent") or {}
            return self.public_copy(plan.get("objective") or self.replay_labels[event_type])
        if event_type == "BELIEF_UPDATED":
            return self.public_copy(payload.get("assessment") or self.replay_labels[event_type])
        return self.replay_labels.get(event_type, "一项世界事实发生了变化")

    def public_replay_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
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
            "kind": self.replay_labels.get(event_type, "世界事实"),
            "text": self.replay_event_text(event),
        }
        if event_type == "CRISIS_SETTLED":
            item["meaning"] = True
        return item

    def lifetime_replay_event(
        self, event: dict[str, Any], lifetime_id: str
    ) -> dict[str, Any] | None:
        public = self.public_replay_event(event)
        if public is not None:
            return public
        payload = event.get("payload", {})
        event_type = str(event["event_type"])
        visible = event.get("seat_id") == lifetime_id
        visible = visible or payload.get("sender") == lifetime_id
        visible = visible or payload.get("recipient") == lifetime_id
        explicit_visibility = payload.get("visibility")
        visible = visible or isinstance(explicit_visibility, list) and lifetime_id in explicit_visibility
        if not visible or event_type not in self.replay_labels:
            return None
        return {
            "id": str(event["id"]),
            "tick": int(event["tick"]),
            "kind": self.replay_labels[event_type],
            "text": self.replay_event_text(event),
            "private_to_lifetime": True,
        }

    def judgment_course_text(self, course: Any) -> str:
        if not isinstance(course, dict):
            return "此前还没有明确打算。"
        summary = str(course.get("course") or course.get("objective") or "").strip()
        return self.public_copy(summary) if summary else "此前还没有明确打算。"

    def judgment_event_text(self, event: dict[str, Any]) -> str:
        """Project one admitted fact into archive copy without exposing ledger vocabulary."""

        event_type = str(event.get("event_type", ""))
        payload = event.get("payload", {})
        if event_type == "DECISION_DEPENDENCY_DUE":
            return "此前等待的期限已经到来。"
        if event_type in {"OBSERVATION_OBTAINED", "INVESTIGATION_COMPLETED"}:
            observation = payload.get("observation", {})
            value = observation.get("content") if isinstance(observation, dict) else observation
            return self.public_copy(value or "一项调查结果进入所知范围。")
        if event_type in {"OPERATION_COMPLETED", "ENTITY_STATE_CHANGED"}:
            return "一项行动留下了可见结果。"
        return self.replay_event_text(event)

    def judgment_why_now(
        self,
        event: dict[str, Any],
        previous_course: Any,
        attention_events: list[dict[str, Any]],
    ) -> str:
        event_type = str(event.get("event_type", ""))
        if event_type == "DECISION_HORIZON_HELD":
            return "新的事实还没有改变此前判断的基础。"
        if previous_course is None:
            return "这是这段人生第一次留下明确打算。"
        matching = [
            attention
            for attention in attention_events
            if int(attention.get("tick", -1)) <= int(event.get("tick", 0))
            and str(attention.get("payload", {}).get("decision", "")) == "REOPEN"
        ]
        if matching:
            reason = str(matching[-1].get("payload", {}).get("reason_code", ""))
            return {
                "OPEN_DEPENDENCY_MATCH": "此前等待的一项事实终于到达。",
                "STRUCTURED_COMMITMENT_CHANGE": "一项正式约定发生了变化。",
                "STRUCTURAL_WORLD_SHOCK": "世界边界发生了结构性变化。",
                "OWN_CONSEQUENCE_UNEXPECTED": "此前的行动留下了意外后果。",
                "NO_CURRENT_COURSE": "新的事实进入时，还没有现成的打算。",
            }.get(reason, "新的事实进入了这段人生。")
        return "你在新的判断下改了主意。"

    def judgment_history(
        self, lifetime: dict[str, Any], events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Rebuild the public judgment history from append-only Horizon events."""

        lifetime_id = str(lifetime["seat"])
        horizon_types = {
            "DECISION_HORIZON_ESTABLISHED",
            "DECISION_HORIZON_REVISED",
            "DECISION_HORIZON_HELD",
        }
        horizons = [
            event
            for event in events
            if str(event.get("event_type", "")) in horizon_types
            and (
                str(event.get("seat_id", "")) == lifetime_id
                or str(event.get("payload", {}).get("seat", "")) == lifetime_id
            )
        ]
        horizons.sort(key=lambda item: (int(item.get("tick", 0)), str(item.get("id", ""))))
        if not horizons:
            return []

        event_by_id = {str(item.get("id", "")): item for item in events}
        attention_events = [
            event
            for event in events
            if event.get("event_type") == "ATTENTION_EVALUATED"
            and str(event.get("seat_id", "")) == lifetime_id
        ]
        later_known = []
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
        for message_id, dispatch in dispatches.items():
            delivery = deliveries.get(message_id)
            if delivery is not None and int(dispatch.get("tick", 0)) < int(delivery.get("tick", 0)):
                later_known.append((int(delivery["tick"]), self.judgment_event_text(delivery)))
        later_known.sort(key=lambda item: item[0])

        history: list[dict[str, Any]] = []
        previous_course: Any = None
        hidden_types = {
            "TIME_ADVANCED",
            "ATTENTION_EVALUATED",
            "DELIBERATION_COMMITTED",
            "DECISION_HORIZON_ESTABLISHED",
            "DECISION_HORIZON_REVISED",
            "DECISION_HORIZON_HELD",
            "PLAN_UPDATED",
            "BELIEF_UPDATED",
            "INTENT_COMMITTED",
            "AGENT_INTENT_ACCEPTED",
            "HUMAN_INTENT_ACCEPTED",
            "MOMENT_COMMITTED",
        }
        for index, horizon in enumerate(horizons):
            tick = int(horizon.get("tick", 0))
            next_tick = int(horizons[index + 1]["tick"]) if index + 1 < len(horizons) else None
            course = horizon.get("payload", {}).get("course")
            event_type = str(horizon.get("event_type", ""))
            if event_type == "DECISION_HORIZON_HELD":
                label = "暂时维持"
                decision = "暂时维持原来的打算"
            elif event_type == "DECISION_HORIZON_ESTABLISHED":
                label = "第一次判断"
                decision = "形成了新的打算"
            else:
                label = "重新判断"
                decision = "改成了新的打算"

            facts: list[str] = []
            for attention in attention_events:
                attention_tick = int(attention.get("tick", 0))
                if attention_tick <= tick or (next_tick is not None and attention_tick > next_tick):
                    continue
                for event_id in attention.get("payload", {}).get("new_known_event_ids", []):
                    admitted = event_by_id.get(str(event_id))
                    if admitted is None:
                        continue
                    value = self.judgment_event_text(admitted)
                    if value not in facts:
                        facts.append(value)
            for known_tick, value in later_known:
                if known_tick <= tick or (next_tick is not None and known_tick > next_tick):
                    continue
                if value not in facts:
                    facts.append(value)

            consequences: list[str] = []
            for candidate in events:
                candidate_tick = int(candidate.get("tick", 0))
                candidate_type = str(candidate.get("event_type", ""))
                if candidate_tick <= tick or (next_tick is not None and candidate_tick > next_tick):
                    continue
                if candidate_type in hidden_types:
                    continue
                public = self.lifetime_replay_event(candidate, lifetime_id)
                if public is None:
                    continue
                value = str(public.get("text") or "").strip()
                if value and value not in consequences:
                    consequences.append(value)
                if len(consequences) >= 4:
                    break

            history.append(
                {
                    "id": str(horizon["id"]),
                    "tick": tick,
                    "label": label,
                    "before": self.judgment_course_text(previous_course),
                    "decision": decision,
                    "course": self.judgment_course_text(course),
                    "why_now": self.judgment_why_now(
                        horizon, previous_course, attention_events
                    ),
                    "new_facts": [{"text": value} for value in facts[:4]],
                    "consequences": [{"text": value} for value in consequences],
                }
            )
            previous_course = course
        return history

    def lifetime_replay(
        self,
        state: dict[str, Any],
        lifetime: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lifetime_id = str(lifetime["seat"])
        items = [
            item
            for event in events
            if (item := self.lifetime_replay_event(event, lifetime_id)) is not None
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
            delivery_item = self.lifetime_replay_event(delivery, lifetime_id)
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
            "display_name": self.public_lifetime(
                state["worldline"], state["projection"], lifetime
            )["display_name"],
            "items": items,
            "known_at_time": known_at_time,
            "later_known": later_known,
            "unknown_at_time": unknown_at_time,
            "judgment_history": self.judgment_history(lifetime, events),
        }

    def volume_archive(self, worldline_id: str) -> dict[str, Any]:
        state = self.volume_state(worldline_id)
        events = self.active.db.worldline_events(worldline_id)
        public_items = [
            item
            for event in events
            if (item := self.public_replay_event(event)) is not None
        ]
        ledger = []
        for event in events:
            public_item = self.public_replay_event(event)
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
            "worldline": self.public_worldline(state["worldline"]),
            "volume": {
                "id": self.active.volume_runtime.pack.volume.id,
                "title": self.active.volume_runtime.pack.volume.title,
                "subtitle": self.active.volume_runtime.pack.volume.subtitle,
            },
            "world": self.public_world(worldline_id),
            "boundary": boundary,
            "events": ledger,
            "replay": {"public": {"items": public_items}},
        }

    def desk_course_items(self, context: dict[str, Any]) -> list[dict[str, str]]:
        course = context.get("current_course") or context.get("previous_course")
        if not isinstance(course, dict):
            return []
        summary = str(course.get("course") or course.get("objective") or "").strip()
        items: list[dict[str, str]] = []
        if summary:
            items.append({"text": self.public_copy(summary)})
        for step in course.get("steps", []):
            value = str(step).strip()
            if value and value != summary:
                items.append({"text": self.public_copy(value)})
        return items

    def desk_binding_items(self, context: dict[str, Any]) -> list[dict[str, str]]:
        binding = context.get("binding_reality")
        if not isinstance(binding, dict):
            return []
        items: list[dict[str, str]] = []
        position = binding.get("position")
        if isinstance(position, dict):
            display_name = str(position.get("display_name") or "").strip()
            if display_name:
                items.append({"text": f"你现在在{display_name}。"})
        labels = {
            "active_operations": "仍在进行的行动",
            "active_investigations": "仍在等待的调查",
            "active_offers": "仍未落定的条件",
            "active_agreements": "已经生效的约定",
            "commitments": "已经承担的承诺",
            "owned_assets": "仍在手上的资源",
        }
        for key, label in labels.items():
            values = binding.get(key, [])
            if not isinstance(values, list):
                continue
            for value in values:
                description = self.product_item_text(value)
                if description:
                    items.append({"text": f"{label}：{description}"})
        return items

    def desk_why_now(self, context: dict[str, Any]) -> dict[str, Any]:
        why_now = context.get("why_now")
        if not isinstance(why_now, dict):
            why_now = {}
        reopened = str(why_now.get("decision", "")) == "REOPEN"
        facts = self.product_items(why_now.get("facts", []))
        return {
            "open": reopened,
            "text": "现实第一次改变了此前判断的基础。" if reopened else "此前的判断仍在生效。",
            "facts": facts,
        }

    def public_desk(
        self, worldline_id: str, human_attention: dict[str, Any] | None
    ) -> dict[str, Any]:
        row = self._volume_row(self.active, worldline_id)
        lifetime_id = self.lifetime_seat(
            worldline_id, str(row.get("human_lifetime_id") or "")
        )
        if not lifetime_id:
            raise HTTPException(status_code=409, detail="请先进入一段人生")
        state = self.active.volume_runtime.worldline(worldline_id)
        lifetime = next(item for item in state["lifetimes"] if item["seat"] == lifetime_id)
        attention_wake_id = ""
        if human_attention:
            attention_wake_id = next(
                (
                    str(wake_id)
                    for wake_id in human_attention.get("wake_ids", [])
                    if (
                        wake := self.active.db.crisis_wake(str(wake_id))
                    ) is not None
                    and str(wake.get("actor_id", "")) == lifetime_id
                ),
                "",
            )
        context = self.active.volume_runtime.lifetime_context(
            worldline_id, lifetime_id, wake_id=attention_wake_id or None
        )
        return {
            "worldline": self.public_worldline(row),
            "lifetime": self.public_lifetime(row, state["projection"], lifetime),
            "desk": {
                "position": context.get("position", {}),
                "arrivals": self.product_items(context.get("recent_knowledge", [])),
                "known": self.product_items(context.get("relevant_evidence", [])),
                "uncertainty": self.product_items(context.get("known_uncertainty", [])),
                "current_plan": self.product_items(context.get("current_plan", [])),
                "active_obligations": self.product_items(context.get("active_obligations", [])),
                "role": context.get("role", {}),
                "current_course": self.desk_course_items(context),
                "since_last_deliberation": self.product_items(
                    (context.get("since_last_deliberation") or {}).get("facts", [])
                ),
                "why_now": self.desk_why_now(context),
                "binding_reality": self.desk_binding_items(context),
                "reconsideration": {
                    "available": True,
                    "attention_open": human_attention is not None,
                    "prompt": "现在还这样办吗？",
                },
            },
        }

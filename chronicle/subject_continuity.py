from __future__ import annotations

import copy
import json
import re
from typing import Any

from .crisis import VolumePack
from .db import ChronicleDB
from .decision_horizon import current_course_from_plan


class SubjectContinuityError(ValueError):
    """A bounded Subject context or evidence reference is invalid."""


class LifetimeContextBuilder:
    """Build a bounded, actor-scoped context from Ledger and Lifetime state."""

    MAX_BELIEFS = 8
    MAX_DIRECT_EVIDENCE = 6
    MAX_RECENT_KNOWLEDGE = 6
    MAX_MEMORY_LINES = 6
    MAX_OBLIGATIONS = 8

    _PUBLIC_EVENT_TYPES = {
        "CRISIS_ACTIVATED",
        "CRISIS_CHECKPOINT_ENTERED",
        "CRISIS_PRESSURE_APPLIED",
        "CRISIS_PRESSURE_SKIPPED",
        "CRISIS_SETTLED",
        "FIELD_EVENT_APPLIED",
    }
    _TRIGGER_PAYLOAD_KEYS = {
        "content",
        "crisis_id",
        "delivery_tick",
        "belief",
        "belief_key",
        "evidence_event_ids",
        "from",
        "global_tick",
        "intent",
        "message_id",
        "recipient",
        "reason",
        "revisit_id",
        "sender",
        "source",
        "source_crisis_id",
        "seat",
        "tick",
        "trigger_event_id",
        "wake_id",
    }

    def __init__(self, db: ChronicleDB, pack: VolumePack):
        self.db = db
        self.pack = pack

    def build(
        self,
        worldline_id: str,
        lifetime_id: str,
        projection: dict[str, Any],
        *,
        wake: dict[str, Any] | None = None,
        trigger_event_id: str = "",
    ) -> dict[str, Any]:
        lifetime = self._lifetime(worldline_id, lifetime_id)
        tick = int(projection.get("tick", 0))
        events = self.db.worldline_events(worldline_id)
        events_by_id = {str(event["id"]): event for event in events}
        trigger_id = str(trigger_event_id or (wake or {}).get("trigger_event_id", ""))
        raw_trigger = events_by_id.get(trigger_id)
        trigger = self._event_view(raw_trigger)
        tokens = self._relevance_tokens(lifetime, trigger, wake)
        crisis_context = self._crisis_context(projection, lifetime["seat"], tick)
        relevant_beliefs = self._relevant_beliefs(lifetime["beliefs"], tokens)
        knowledge = self._bounded_knowledge(lifetime["knowledge"], tokens)
        memory = self._selective_memory(str(lifetime["memory_text"]), tokens)
        position_id = str(projection.get("positions", {}).get(lifetime["seat"], ""))
        position = {
            "id": position_id,
            "display_name": self._location_name(position_id),
        }
        assets = self._assets(projection, lifetime["seat"], crisis_context)
        current_plan = list(lifetime.get("plan", []))[:1]
        current_course = current_course_from_plan(current_plan, fallback_tick=tick)
        due_revisits = [
            copy.deepcopy(item)
            for item in lifetime.get("revisits", [])
            if item.get("status") == "DUE"
            or (
                item.get("status") == "PENDING"
                and item.get("due_tick") is not None
                and int(item["due_tick"]) <= tick
            )
        ][: self.MAX_OBLIGATIONS]
        obligations = self._obligations(lifetime, current_plan, due_revisits, crisis_context)
        why_now = self._why_now(events_by_id, lifetime, raw_trigger)
        since_last_deliberation = self._since_last_deliberation(lifetime, current_course)
        binding_reality = self._binding_reality(
            lifetime,
            position,
            assets,
            crisis_context,
        )
        relevant_experience = {
            "beliefs": copy.deepcopy(relevant_beliefs),
            "evidence": copy.deepcopy(knowledge["relevant"]),
            "memory": copy.deepcopy(memory),
        }
        return {
            "worldline_id": worldline_id,
            "lifetime_id": lifetime["id"],
            "seat": lifetime["seat"],
            "tick": tick,
            "trigger": trigger,
            "wake": {
                "id": str((wake or {}).get("id", "")),
                "wake_type": str((wake or {}).get("wake_type", "")),
            },
            # V6 deliberation uses actor-known reality before selective memory.
            "why_now": why_now,
            "since_last_deliberation": since_last_deliberation,
            "binding_reality": binding_reality,
            "previous_course": copy.deepcopy(current_course),
            "relevant_experience": relevant_experience,
            "affordances": self._affordances(crisis_context),
            "role": {
                "display_name": lifetime.get("display_name", lifetime["seat"]),
                "genesis_context": copy.deepcopy(lifetime.get("genesis_context", {})),
                "authority": list(lifetime.get("authority", [])),
                "crisis_roles": [
                    {
                        "crisis_id": item["crisis_id"],
                        "role_charter": item["role_charter"],
                    }
                    for item in crisis_context
                    if item.get("role_charter")
                ],
            },
            "position": position,
            "assets": assets,
            "resources": copy.deepcopy(lifetime.get("resources", {})),
            "authority": list(lifetime.get("authority", [])),
            "active_obligations": obligations,
            "current_plan": current_plan,
            "current_course": current_course,
            "due_revisits": due_revisits,
            "active_crisis_context": crisis_context,
            "beliefs": relevant_beliefs,
            "relevant_evidence": knowledge["relevant"],
            "recent_knowledge": knowledge["recent"],
            "subjective_memory": memory,
            "known_uncertainty": self._uncertainty(projection, trigger, lifetime["seat"]),
        }

    def _why_now(
        self,
        events_by_id: dict[str, dict[str, Any]],
        lifetime: dict[str, Any],
        trigger: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not trigger:
            return {"reason_code": "NO_TRIGGER", "facts": []}

        payload = trigger.get("payload", {})
        if trigger.get("event_type") == "ATTENTION_EVALUATED" and isinstance(payload, dict):
            facts = [
                self._event_view(event)
                for event_id in payload.get("trigger_event_ids", [])
                if (event := events_by_id.get(str(event_id))) is not None
                and self._event_visible_to_lifetime(event, lifetime)
            ]
            return {
                "attention_event_id": str(trigger.get("id", "")),
                "decision": str(payload.get("decision", "")),
                "reason_code": str(payload.get("reason_code", "")),
                "matched_dependency_ids": [
                    str(item)
                    for item in payload.get("matched_dependency_ids", [])
                    if str(item)
                ],
                "facts": facts,
            }

        event = events_by_id.get(str(trigger.get("id", "")))
        facts = [self._event_view(event)] if event and self._event_visible_to_lifetime(event, lifetime) else []
        return {"reason_code": "WAKE_TRIGGER", "facts": facts}

    def _since_last_deliberation(
        self, lifetime: dict[str, Any], current_course: dict[str, Any] | None
    ) -> dict[str, Any]:
        boundary_tick = int((current_course or {}).get("last_deliberated_tick", 0))
        facts = []
        for item in lifetime.get("knowledge", []):
            if not isinstance(item, dict):
                continue
            knowledge_tick = self._knowledge_tick(item)
            if knowledge_tick is not None and knowledge_tick > boundary_tick:
                facts.append(copy.deepcopy(item))
        return {"after_tick": boundary_tick, "facts": facts}

    def _binding_reality(
        self,
        lifetime: dict[str, Any],
        position: dict[str, Any],
        assets: list[dict[str, Any]],
        crisis_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "position": copy.deepcopy(position),
            "authority": list(lifetime.get("authority", [])),
            "active_operations": self._crisis_items(crisis_context, "active_operations"),
            "active_investigations": self._crisis_items(
                crisis_context, "active_investigations"
            ),
            "active_offers": self._crisis_items(crisis_context, "active_offers"),
            "active_agreements": self._crisis_items(crisis_context, "active_agreements"),
            "commitments": copy.deepcopy(lifetime.get("commitments", [])),
            "owned_assets": copy.deepcopy(assets),
            "resources": copy.deepcopy(lifetime.get("resources", {})),
        }

    @staticmethod
    def _crisis_items(
        crisis_context: list[dict[str, Any]], key: str
    ) -> list[dict[str, Any]]:
        return [
            {"crisis_id": context["crisis_id"], "item": copy.deepcopy(item)}
            for context in crisis_context
            for item in context.get(key, [])
        ]

    @staticmethod
    def _affordances(crisis_context: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        return {
            key: [
                {"crisis_id": context["crisis_id"], "item": copy.deepcopy(item)}
                for context in crisis_context
                for item in context.get("subject_affordances", {}).get(key, [])
            ]
            for key in ("operations", "investigations", "offer_terms")
        }

    @staticmethod
    def _knowledge_tick(item: dict[str, Any]) -> int | None:
        for key in ("received_tick", "tick", "obtained_tick", "due_tick"):
            value = item.get(key)
            if isinstance(value, bool):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def validate_evidence(
        self,
        worldline_id: str,
        lifetime_id: str,
        evidence_event_ids: list[str] | None,
        *,
        fallback_event_id: str = "",
    ) -> list[str]:
        lifetime = self._lifetime(worldline_id, lifetime_id)
        requested = [str(item).strip() for item in evidence_event_ids or [] if str(item).strip()]
        if not requested and fallback_event_id:
            requested = [str(fallback_event_id)]
        requested = list(dict.fromkeys(requested))
        events = self.db.worldline_events(worldline_id)
        events_by_id = {str(event["id"]): event for event in events}
        for event_id in requested:
            event = events_by_id.get(event_id)
            if event is None or not self._event_visible_to_lifetime(event, lifetime):
                raise SubjectContinuityError(
                    f"evidence event is not known to Lifetime {lifetime['seat']}: {event_id}"
                )
        return requested

    def causal_trace(self, worldline_id: str, target_event_id: str) -> dict[str, Any]:
        events = self.db.worldline_events(worldline_id)
        events_by_id = {str(event["id"]): event for event in events}
        target = events_by_id.get(str(target_event_id))
        if target is None:
            raise SubjectContinuityError(f"event not found: {target_event_id}")
        seat = str(target.get("seat_id") or target.get("payload", {}).get("seat") or "")
        lifetime = self._lifetime(worldline_id, seat) if seat else None
        ancestors = self._ancestor_events(events_by_id, str(target["id"]))
        decision = next(
            (
                event
                for event in reversed(ancestors)
                if event["event_type"]
                in {"INTENT_COMMITTED", "HUMAN_DECISION_APPLIED", "AGENT_INTENT_ACCEPTED"}
            ),
            None,
        )
        expectation = next(
            (event for event in reversed(ancestors) if event["event_type"] == "BELIEF_UPDATED"),
            None,
        )
        evidence_ids = list((expectation or {}).get("payload", {}).get("evidence_event_ids", []))
        decision_tick = int((decision or target)["tick"])
        known_at_time = []
        if lifetime is not None:
            known_at_time = [
                self._event_view(event)
                for event in events
                if int(event["tick"]) <= decision_tick
                and self._event_visible_to_lifetime(event, lifetime)
            ][-12:]
        projection = self.db.worldline_snapshot(worldline_id, decision_tick)
        unknown_at_time = []
        if projection is not None:
            for message in projection["projection"].get("messages", []):
                delivery_tick = int(message.get("delivery_tick", message.get("arrival_tick", 0)))
                if message.get("status") == "in_transit" and delivery_tick > decision_tick:
                    if not seat or message.get("recipient") == seat:
                        unknown_at_time.append(
                            {
                                "id": message.get("id", ""),
                                "sender": message.get("sender", ""),
                                "recipient": message.get("recipient", ""),
                                "delivery_tick": delivery_tick,
                            }
                        )
        return {
            "world_action": self._event_view(target),
            "decision": self._event_view(decision),
            "current_expectation": self._event_view(expectation),
            "evidence_event_ids": evidence_ids,
            "earlier_episode": [
                self._event_view(events_by_id[event_id])
                for event_id in evidence_ids
                if event_id in events_by_id
            ],
            "known_at_time": known_at_time,
            "unknown_at_time": unknown_at_time[:8],
            "controller": self._controller_for(decision),
        }

    def _lifetime(self, worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        lifetime = self.db.worldline_lifetime_by_id(worldline_id, lifetime_id)
        lifetime = lifetime or self.db.worldline_lifetime(worldline_id, lifetime_id)
        if lifetime is None:
            raise SubjectContinuityError(f"Lifetime not found: {lifetime_id}")
        return lifetime

    def _crisis_context(
        self, projection: dict[str, Any], seat: str, tick: int
    ) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        instances = projection.get("crisis_instances", {})
        for crisis_id in sorted(projection.get("active_crisis_ids", [])):
            state = instances.get(crisis_id, {})
            if seat not in state.get("participants", []):
                continue
            pack = self.pack.pack(crisis_id)
            overlay = pack.actor_by_id.get(seat)
            scoped_projection = copy.deepcopy(state)
            scoped_projection["positions"] = copy.deepcopy(projection.get("positions", {}))
            subject_affordances = {
                "operations": pack.operation_affordances(
                    seat, scoped_projection, tick
                ),
                "investigations": pack.investigation_affordances(
                    seat, scoped_projection, tick
                ),
                "offer_terms": pack.offer_term_affordances(seat),
            }
            contexts.append(
                {
                    "crisis_id": crisis_id,
                    "title": pack.crisis.title,
                    "status": state.get("status", ""),
                    "phase": state.get("phase", ""),
                    "activation_tick": int(state.get("activation_tick", tick)),
                    "local_tick": int(state.get("local_tick", 0)),
                    "participants": list(state.get("participants", [])),
                    "role_charter": (
                        overlay.role_charter.model_dump(mode="json") if overlay else {}
                    ),
                    "active_operations": self._subject_items(state.get("operations", []), seat),
                    "active_investigations": self._subject_items(
                        state.get("investigations", []), seat
                    ),
                    "active_offers": self._subject_items(state.get("offers", []), seat),
                    "active_agreements": self._subject_items(state.get("agreements", []), seat),
                    "available_affordances": copy.deepcopy(state.get("available_affordances", {})),
                    "subject_affordances": subject_affordances,
                }
            )
        return contexts

    def _assets(
        self, projection: dict[str, Any], seat: str, crisis_context: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        asset_ids: set[str] = set()
        for context in crisis_context:
            overlay = self.pack.pack(context["crisis_id"]).actor_by_id.get(seat)
            if overlay:
                asset_ids.update(overlay.asset_ids)
        result: list[dict[str, Any]] = []
        for asset_id in sorted(asset_ids):
            entity = projection.get("entities", {}).get(asset_id)
            if entity is None:
                for context in crisis_context:
                    entity = (
                        projection.get("crisis_instances", {})
                        .get(context["crisis_id"], {})
                        .get("entities", {})
                        .get(asset_id)
                    )
                    if entity is not None:
                        break
            result.append(
                {
                    "id": asset_id,
                    "display_name": (entity or {}).get("display_name", asset_id),
                    "state": (entity or {}).get("state", ""),
                }
            )
        return result[: self.MAX_OBLIGATIONS]

    def _obligations(
        self,
        lifetime: dict[str, Any],
        current_plan: list[Any],
        due_revisits: list[dict[str, Any]],
        crisis_context: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        obligations: list[dict[str, Any]] = []
        if current_plan:
            obligations.append({"kind": "plan", "value": copy.deepcopy(current_plan[0])})
        for commitment in lifetime.get("commitments", []):
            obligations.append({"kind": "commitment", "value": copy.deepcopy(commitment)})
        obligations.extend({"kind": "revisit", "value": item} for item in due_revisits)
        for context in crisis_context:
            for key in (
                "active_operations",
                "active_investigations",
                "active_offers",
                "active_agreements",
            ):
                obligations.extend(
                    {
                        "kind": key.removesuffix("s"),
                        "crisis_id": context["crisis_id"],
                        "value": item,
                    }
                    for item in context[key]
                )
        return obligations[: self.MAX_OBLIGATIONS]

    @staticmethod
    def _subject_items(values: Any, seat: str) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            if not isinstance(value, dict):
                continue
            visible_to = value.get("visible_to")
            if isinstance(visible_to, list) and visible_to and seat not in visible_to:
                continue
            if (
                value.get("actor_id") == seat
                or value.get("issuer") == seat
                or value.get("recipient") == seat
                or seat in value.get("parties", [])
                or value.get("visibility") == "PUBLIC"
            ):
                result.append(copy.deepcopy(value))
        return result[:6]

    def _relevance_tokens(
        self,
        lifetime: dict[str, Any],
        trigger: dict[str, Any],
        wake: dict[str, Any] | None,
    ) -> set[str]:
        source = json.dumps(
            {
                "seat": lifetime["seat"],
                "trigger": trigger,
                "wake": wake or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        ).casefold()
        return {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]{2,}", source)
            if len(token) >= 2
        }

    @staticmethod
    def _relevant_beliefs(beliefs: dict[str, Any], tokens: set[str]) -> dict[str, Any]:
        ranked = []
        for key, value in beliefs.items():
            text = json.dumps({"key": key, "value": value}, ensure_ascii=False).casefold()
            score = sum(token in text for token in tokens)
            ranked.append((score, str(key), value))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return {
            key: copy.deepcopy(value)
            for _score, key, value in ranked[: LifetimeContextBuilder.MAX_BELIEFS]
        }

    def _bounded_knowledge(self, knowledge: list[Any], tokens: set[str]) -> dict[str, list[Any]]:
        direct = [item for item in knowledge if self._matches(item, tokens)]
        direct_ids = {id(item) for item in direct}
        recent = [
            item for item in knowledge[-self.MAX_RECENT_KNOWLEDGE :] if id(item) not in direct_ids
        ]
        return {
            "relevant": copy.deepcopy(direct[-self.MAX_DIRECT_EVIDENCE :]),
            "recent": copy.deepcopy(recent[-self.MAX_RECENT_KNOWLEDGE :]),
        }

    @staticmethod
    def _matches(value: Any, tokens: set[str]) -> bool:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
        return any(token in text for token in tokens)

    def _selective_memory(self, memory_text: str, tokens: set[str]) -> dict[str, Any]:
        lines = [line.strip() for line in memory_text.splitlines() if line.strip()]
        matching = [line for line in lines if any(token in line.casefold() for token in tokens)]
        selected = list(dict.fromkeys(matching))
        for line in lines[-self.MAX_MEMORY_LINES :]:
            if line not in selected:
                selected.append(line)
            if len(selected) >= self.MAX_MEMORY_LINES:
                break
        selected = selected[: self.MAX_MEMORY_LINES]
        return {
            "text": "\n".join(selected),
            "selected_lines": selected,
            "total_lines": len(lines),
        }

    def _uncertainty(
        self, projection: dict[str, Any], trigger: dict[str, Any], seat: str
    ) -> list[str]:
        uncertainty = ["其他人的私下所知不会自动进入你眼前。"]
        if trigger:
            uncertainty.append("当前判断只建立在已冻结的触发和可见证据上。")
        if any(
            message.get("status") == "in_transit" and message.get("recipient") == seat
            for message in projection.get("messages", [])
        ):
            uncertainty.append("仍有在途消息，抵达后可能改变当前判断。")
        return uncertainty

    def _location_name(self, location_id: str) -> str:
        location = self.pack.world.location_by_id.get(location_id)
        return location.display_name if location else location_id

    @staticmethod
    def _event_view(event: dict[str, Any] | None) -> dict[str, Any]:
        if event is None:
            return {}
        payload = event.get("payload", {})
        bounded_payload = {
            key: copy.deepcopy(payload[key])
            for key in LifetimeContextBuilder._TRIGGER_PAYLOAD_KEYS
            if isinstance(payload, dict) and key in payload
        }
        return {
            "event_id": str(event["id"]),
            "event_type": str(event["event_type"]),
            "tick": int(event["tick"]),
            "seat_id": str(event.get("seat_id") or ""),
            "payload": bounded_payload,
        }

    def _event_visible_to_lifetime(self, event: dict[str, Any], lifetime: dict[str, Any]) -> bool:
        seat = str(lifetime["seat"])
        if str(event.get("seat_id") or "") == seat:
            return True
        payload = event.get("payload", {})
        if isinstance(payload, dict) and seat in payload.get("visibility", []):
            return True
        if event.get("event_type") in self._PUBLIC_EVENT_TYPES:
            crisis_id = str(payload.get("crisis_id", "")) if isinstance(payload, dict) else ""
            if not crisis_id:
                return True
            try:
                return seat in self.pack.pack(crisis_id).participant_ids
            except Exception:
                return False
        knowledge = lifetime.get("knowledge", [])
        identifiers = set()
        if isinstance(payload, dict):
            identifiers.update(
                str(payload.get(key, ""))
                for key in ("message_id", "observation_id", "event_id")
                if payload.get(key)
            )
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            known_ids = {
                str(item.get(key, ""))
                for key in ("message_id", "observation_id", "event_id", "delivery_event_id")
                if item.get(key)
            }
            if str(event["id"]) in known_ids or identifiers.intersection(known_ids):
                return True
        return False

    @staticmethod
    def _ancestor_events(
        events_by_id: dict[str, dict[str, Any]], target_event_id: str
    ) -> list[dict[str, Any]]:
        pending = [target_event_id]
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        while pending:
            event_id = pending.pop()
            if event_id in seen or event_id not in events_by_id:
                continue
            seen.add(event_id)
            event = events_by_id[event_id]
            result.append(event)
            pending.extend(
                str(parent_id)
                for parent_id in reversed(event.get("causal_parent_ids", []))
                if str(parent_id)
            )
        result.sort(key=lambda item: (int(item["tick"]), int(item.get("sequence", 0))))
        return result

    @staticmethod
    def _controller_for(event: dict[str, Any] | None) -> str:
        if event is None:
            return ""
        payload = event.get("payload", {})
        if isinstance(payload, dict):
            source = str(payload.get("source", ""))
            if source in {"human", "agent"}:
                return source
        return ""

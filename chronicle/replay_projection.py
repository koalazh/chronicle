from __future__ import annotations

import json
from collections import Counter, deque
from collections.abc import Callable
from typing import Any

EventProjection = Callable[[dict[str, Any]], dict[str, Any]]
VisibleTo = Callable[[dict[str, Any]], list[str]]

_MATERIAL_EVENT_TYPES = frozenset(
    {
        "HUMAN_DECISION_APPLIED",
        "HUMAN_SILENCE",
        "MESSAGE_DISPATCHED",
        "MESSAGE_DELIVERED",
        "INVESTIGATION_STARTED",
        "INVESTIGATION_COMPLETED",
        "OBSERVATION_OBTAINED",
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "OFFER_ACCEPTED",
        "OFFER_REJECTED",
        "OFFER_WITHDRAWN",
        "OFFER_EXPIRED",
        "AGREEMENT_CREATED",
        "AGREEMENT_FULFILLED",
        "AGREEMENT_BREACHED",
        "PRESSURE_APPLIED",
        "OPERATION_STARTED",
        "OPERATION_COMPLETED",
        "MOVEMENT_STARTED",
        "MOVEMENT_ARRIVED",
        "ENTITY_STATE_CHANGED",
        "RESOLUTION_GATE_REACHED",
        "RESOLUTION_APPLIED",
        "CRISIS_SETTLED",
    }
)
_ROOT_EVENT_TYPES = frozenset(
    {
        "HUMAN_DECISION_APPLIED",
        "HUMAN_SILENCE",
        "MESSAGE_DISPATCHED",
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "AGREEMENT_CREATED",
        "INVESTIGATION_STARTED",
        "PRESSURE_APPLIED",
        "OPERATION_STARTED",
        "MOVEMENT_STARTED",
    }
)
_PREFERRED_COMPRESSION_TYPES = frozenset(
    {
        "MESSAGE_DISPATCHED",
        "OBSERVATION_OBTAINED",
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "OFFER_ACCEPTED",
        "AGREEMENT_CREATED",
        "AGREEMENT_FULFILLED",
        "AGREEMENT_BREACHED",
        "PRESSURE_APPLIED",
        "OPERATION_STARTED",
        "OPERATION_COMPLETED",
        "MOVEMENT_ARRIVED",
        "ENTITY_STATE_CHANGED",
        "RESOLUTION_APPLIED",
    }
)


def compare_material_runs(
    left_events: list[dict[str, Any]],
    right_events: list[dict[str, Any]],
    *,
    project_event: EventProjection,
) -> dict[str, Any]:
    """Compare two sealed Ledgers through durable World facts only.

    This deliberately ignores free-form communications, plans, reflections, and
    event identifiers.  A first difference therefore means that a World object,
    Agreement, Operation, or obtained Observation actually became different.
    """

    divergence = _first_material_divergence(left_events, right_events)
    if divergence is None:
        return {
            "first_material_divergence": None,
            "consequence_paths": {
                "title": "这两局尚未出现可建模的世界分歧",
                "left": {"entered_outcome": False, "steps": []},
                "right": {"entered_outcome": False, "steps": []},
            },
        }

    left_events_at_fork = divergence["left"]
    right_events_at_fork = divergence["right"]
    return {
        "first_material_divergence": {
            "tick": divergence["tick"],
            "summary": (
                f"危局第 {divergence['tick']} 日，两局第一次进入不同的可验证现实。"
            ),
            "left": [project_event(event) for event in left_events_at_fork[:3]],
            "right": [project_event(event) for event in right_events_at_fork[:3]],
        },
        "consequence_paths": {
            "title": "这处差异后来如何进入结局",
            "left": _comparison_consequence_path(
                left_events,
                [str(event["id"]) for event in left_events_at_fork],
                project_event,
            ),
            "right": _comparison_consequence_path(
                right_events,
                [str(event["id"]) for event in right_events_at_fork],
                project_event,
            ),
        },
    }


def _first_material_divergence(
    left_events: list[dict[str, Any]], right_events: list[dict[str, Any]]
) -> dict[str, Any] | None:
    left_by_tick = _comparison_facts_by_tick(left_events)
    right_by_tick = _comparison_facts_by_tick(right_events)
    for tick in sorted(set(left_by_tick).union(right_by_tick)):
        left = left_by_tick.get(tick, [])
        right = right_by_tick.get(tick, [])
        if Counter(key for key, _ in left) == Counter(key for key, _ in right):
            continue
        return {
            "tick": tick,
            "left": _unmatched_comparison_events(left, right),
            "right": _unmatched_comparison_events(right, left),
        }
    return None


def _comparison_facts_by_tick(
    events: list[dict[str, Any]],
) -> dict[int, list[tuple[str, dict[str, Any]]]]:
    by_tick: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for event in events:
        fact = _comparison_fact(event)
        if fact is None:
            continue
        by_tick.setdefault(int(event["tick"]), []).append(
            (json_key(fact), event)
        )
    return by_tick


def _unmatched_comparison_events(
    candidates: list[tuple[str, dict[str, Any]]],
    other: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    remaining = Counter(key for key, _ in other)
    unmatched: list[dict[str, Any]] = []
    for key, event in candidates:
        if remaining[key]:
            remaining[key] -= 1
            continue
        unmatched.append(event)
    return unmatched


def _comparison_consequence_path(
    events: list[dict[str, Any]],
    source_event_ids: list[str],
    project_event: EventProjection,
) -> dict[str, Any]:
    target_event_id = next(
        (
            str(event["id"])
            for event in reversed(events)
            if event["event_type"] == "CRISIS_SETTLED"
        ),
        "",
    )
    events_by_id = {str(event["id"]): event for event in events}
    children = _children(events)
    for source_event_id in source_event_ids:
        path = [
            events_by_id[event_id]
            for event_id in _path_to_target(source_event_id, target_event_id, children)
            if _comparison_fact(events_by_id[event_id]) is not None
        ]
        if path:
            return {
                "entered_outcome": True,
                "steps": [
                    project_event(event) for event in _compress_material_events(path)
                ],
            }
    return {"entered_outcome": False, "steps": []}


def _comparison_fact(event: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an event into a fact whose equality is independent of prose."""

    event_type = str(event["event_type"])
    payload = event["payload"]
    if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
        return {
            "kind": "message",
            "stage": event_type,
            "sender": str(payload.get("sender", "")),
            "recipient": str(payload.get("recipient", "")),
            "arrival_tick": payload.get("arrival_tick"),
        }
    if event_type in {"INVESTIGATION_STARTED", "INVESTIGATION_COMPLETED"}:
        investigation = payload.get("investigation", {})
        return {
            "kind": "investigation",
            "stage": event_type,
            "actor": str(investigation.get("actor_id", event.get("seat_id") or "")),
            "definition": str(investigation.get("definition_id", "")),
            "target": str(investigation.get("target_id", "")),
            "method": str(investigation.get("method", "")),
            "expected_result_tick": investigation.get("expected_result_tick"),
        }
    if event_type == "OBSERVATION_OBTAINED":
        observation = payload.get("observation", {})
        return {
            "kind": "observation",
            "actor": str(event.get("seat_id") or ""),
            "content": str(observation.get("content", "")),
            "source": str(observation.get("source", "")),
            "source_ids": sorted(str(item) for item in observation.get("source_ids", [])),
            "reliability": str(observation.get("reliability", "")),
            "related_assertions": sorted(
                str(item) for item in observation.get("related_assertions", [])
            ),
        }
    if event_type in {
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "OFFER_ACCEPTED",
        "OFFER_REJECTED",
        "OFFER_WITHDRAWN",
        "OFFER_EXPIRED",
    }:
        offer = payload.get("counter_offer") if event_type == "OFFER_COUNTERED" else payload.get("offer")
        return {
            "kind": "offer",
            "stage": event_type,
            "offer": _comparison_offer(offer),
        }
    if event_type in {"AGREEMENT_CREATED", "AGREEMENT_FULFILLED", "AGREEMENT_BREACHED"}:
        agreement = payload.get("agreement", {})
        return {
            "kind": "agreement",
            "stage": event_type,
            "parties": sorted(str(item) for item in agreement.get("parties", [])),
            "terms": _comparison_terms(agreement.get("terms", [])),
            "status": str(agreement.get("status", "")),
        }
    if event_type in {"OPERATION_STARTED", "OPERATION_COMPLETED"}:
        operation = payload.get("operation", {})
        return {
            "kind": "operation",
            "stage": event_type,
            "actor": str(operation.get("actor_id", event.get("seat_id") or "")),
            "definition": str(operation.get("definition_id", "")),
            "targets": [str(item) for item in operation.get("target_ids", [])],
            "expected_complete_tick": operation.get("expected_complete_tick"),
            "status": str(operation.get("status", "")),
            "result_state": {
                str(key): str(value)
                for key, value in sorted(operation.get("result_state", {}).items())
            },
        }
    if event_type in {"MOVEMENT_STARTED", "MOVEMENT_ARRIVED"}:
        return {
            "kind": "movement",
            "stage": event_type,
            "actor": str(payload.get("actor_id", event.get("seat_id") or "")),
            "from": str(payload.get("from", "")),
            "to": str(payload.get("to", "")),
            "arrival_tick": payload.get("arrival_tick"),
            "status": str(payload.get("status", "")),
        }
    if event_type in {"PRESSURE_APPLIED", "PRESSURE_SKIPPED"}:
        pressure = payload.get("pressure", {})
        return {
            "kind": "pressure",
            "stage": event_type,
            "pressure": str(pressure.get("id", "")),
            "effects": _comparison_effects(pressure.get("effects", [])),
            "status": str(pressure.get("status", "")),
        }
    if event_type in {"ENTITY_STATE_CHANGED", "RESOLUTION_ENTITY_EFFECT"}:
        return {
            "kind": "entity_state",
            "stage": event_type,
            "entity": str(payload.get("entity_id", "")),
            "before": str(payload.get("before", "")),
            "after": str(payload.get("after", "")),
        }
    if event_type == "RESOLUTION_AGREEMENT_EFFECT":
        return {
            "kind": "agreement_state",
            "stage": event_type,
            "before": str(payload.get("before", "")),
            "after": str(payload.get("after", "")),
            "description": str(payload.get("description", "")),
        }
    if event_type == "RESOLUTION_APPLIED":
        result = payload.get("result", {})
        return {
            "kind": "resolution",
            "result_kind": str(result.get("kind", "")),
            "variant": str(result.get("variant", "")),
            "ambiguity_used": bool(result.get("ambiguity_used", False)),
        }
    if event_type in {"RESOLUTION_REPORT_DISPATCHED", "RESOLUTION_REPORT_DELIVERED"}:
        report = payload.get("report", {})
        return {
            "kind": "resolution_information",
            "stage": event_type,
            "recipient": str(report.get("recipient", event.get("seat_id") or "")),
            "resolution_kind": str(report.get("resolution_kind", "")),
        }
    if event_type == "CRISIS_SETTLED":
        return {
            "kind": "settlement",
            "settlement_type": str(payload.get("settlement_type", "")),
            "reason": str(payload.get("reason", "")),
        }
    return None


def _comparison_offer(offer: Any) -> dict[str, Any]:
    value = offer if isinstance(offer, dict) else {}
    return {
        "issuer": str(value.get("issuer", "")),
        "recipient": str(value.get("recipient", "")),
        "terms": _comparison_terms(value.get("terms", [])),
        "expires_tick": value.get("expires_tick"),
        "status": str(value.get("status", "")),
    }


def _comparison_terms(terms: Any) -> list[dict[str, str]]:
    if not isinstance(terms, list):
        return []
    return sorted(
        [
            {
                "type": str(term.get("type", "")),
                "subject": str(term.get("subject", "")),
                "value": str(term.get("value", "")),
            }
            for term in terms
            if isinstance(term, dict)
        ],
        key=json_key,
    )


def _comparison_effects(effects: Any) -> list[dict[str, str]]:
    if not isinstance(effects, list):
        return []
    return sorted(
        [
            {
                "subject": str(effect.get("subject", "")),
                "state": str(effect.get("state", "")),
            }
            for effect in effects
            if isinstance(effect, dict)
        ],
        key=json_key,
    )


def json_key(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def material_causal_roots(
    events: list[dict[str, Any]],
    *,
    target_event_id: str,
    project_event: EventProjection,
) -> list[dict[str, Any]]:
    """Project the few initiating world changes that enter a settled result."""

    return [
        project_event(event)
        for event in _causal_root_events(events, target_event_id)
    ]


def replay_layers(
    events: list[dict[str, Any]],
    *,
    outcome: dict[str, Any],
    human_actor_id: str | None,
    project_event: EventProjection,
    visible_to: VisibleTo,
    all_actor_ids: set[str],
) -> dict[str, Any]:
    """Build the four V4 Replay layers from immutable Ledger facts."""

    target_event_id = next(
        (
            str(event["id"])
            for event in reversed(events)
            if event["event_type"] == "CRISIS_SETTLED"
        ),
        "",
    )
    if human_actor_id:
        attribution = {
            "mode": "TAKEOVER",
            "title": "你真正改变了什么",
            "chains": _human_causal_chains(
                events, human_actor_id, target_event_id, project_event
            ),
        }
    else:
        attribution = {
            "mode": "WATCH",
            "title": "几条 Life 如何互相改变",
            "chains": _watch_causal_chains(events, target_event_id, project_event),
        }
    return {
        "outcome": outcome,
        "causal_attribution": attribution,
        "perspective_reveal": {
            "title": "在你看不见的地方",
            "items": _hidden_world_items(
                events, human_actor_id, project_event, visible_to, all_actor_ids
            ),
        },
        "historical_compatibility": list(outcome.get("historical_compatibility", [])),
    }


def _causal_root_events(
    events: list[dict[str, Any]], target_event_id: str
) -> list[dict[str, Any]]:
    events_by_id = {str(event["id"]): event for event in events}
    ancestor_ids = _ancestors(events_by_id, target_event_id)
    children = _children(events)
    candidates = [
        event
        for event in events
        if str(event["id"]) in ancestor_ids
        and event["event_type"] in _ROOT_EVENT_TYPES
        and _has_material_descendant(
            str(event["id"]), target_event_id, events_by_id, children
        )
    ]
    candidate_ids = {str(event["id"]) for event in candidates}
    roots: list[dict[str, Any]] = []
    for event in candidates:
        event_id = str(event["id"])
        if any(
            ancestor_id in candidate_ids
            for ancestor_id in _ancestors(events_by_id, event_id)
            if ancestor_id != event_id
        ):
            continue
        roots.append(event)
    return roots[:6]


def _human_causal_chains(
    events: list[dict[str, Any]],
    human_actor_id: str,
    target_event_id: str,
    project_event: EventProjection,
) -> list[dict[str, Any]]:
    events_by_id = {str(event["id"]): event for event in events}
    ancestor_ids = _ancestors(events_by_id, target_event_id)
    children = _children(events)
    chains: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("seat_id") or "") != human_actor_id:
            continue
        if event["event_type"] not in {"HUMAN_DECISION_APPLIED", "HUMAN_SILENCE"}:
            continue
        if str(event["id"]) not in ancestor_ids:
            continue
        material = _material_path(
            str(event["id"]), target_event_id, events_by_id, children
        )
        if len(material) < 3:
            continue
        chains.append(
            {
                "summary": str(
                    event["payload"].get("summary") or "暂不追加命令，继续观察。"
                ),
                "steps": [
                    project_event(item)
                    for item in _compress_material_events(material)
                ],
            }
        )
    return chains[:6]


def _watch_causal_chains(
    events: list[dict[str, Any]],
    target_event_id: str,
    project_event: EventProjection,
) -> list[dict[str, Any]]:
    events_by_id = {str(event["id"]): event for event in events}
    children = _children(events)
    chains: list[dict[str, Any]] = []
    for root in _causal_root_events(events, target_event_id):
        material = _material_path(
            str(root["id"]), target_event_id, events_by_id, children
        )
        if len(material) < 2:
            continue
        chains.append(
            {
                "summary": project_event(root)["text"],
                "steps": [
                    project_event(item)
                    for item in _compress_material_events(material)
                ],
            }
        )
    return chains[:6]


def _hidden_world_items(
    events: list[dict[str, Any]],
    human_actor_id: str | None,
    project_event: EventProjection,
    visible_to: VisibleTo,
    all_actor_ids: set[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in events:
        if event["event_type"] not in _MATERIAL_EVENT_TYPES:
            continue
        recipients = set(visible_to(event))
        actor_id = str(event.get("seat_id") or "")
        if human_actor_id is not None:
            if human_actor_id in recipients or actor_id == human_actor_id:
                continue
        elif recipients == all_actor_ids:
            continue
        items.append(project_event(event))
    return items[:6]


def _ancestors(
    events_by_id: dict[str, dict[str, Any]], target_event_id: str
) -> set[str]:
    if not target_event_id or target_event_id not in events_by_id:
        return set()
    result: set[str] = set()
    pending = [target_event_id]
    while pending:
        event_id = pending.pop()
        if event_id in result:
            continue
        result.add(event_id)
        pending.extend(
            str(parent_id)
            for parent_id in events_by_id[event_id].get("causal_parent_ids", [])
            if str(parent_id) in events_by_id
        )
    return result


def _children(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for event in events:
        for parent_id in event.get("causal_parent_ids", []):
            result.setdefault(str(parent_id), []).append(str(event["id"]))
    return result


def _has_material_descendant(
    source_event_id: str,
    target_event_id: str,
    events_by_id: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
) -> bool:
    return len(_material_path(source_event_id, target_event_id, events_by_id, children)) > 1


def _material_path(
    source_event_id: str,
    target_event_id: str,
    events_by_id: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
) -> list[dict[str, Any]]:
    return [
        events_by_id[event_id]
        for event_id in _path_to_target(source_event_id, target_event_id, children)
        if events_by_id[event_id]["event_type"] in _MATERIAL_EVENT_TYPES
    ]


def _path_to_target(
    source_event_id: str,
    target_event_id: str,
    children: dict[str, list[str]],
) -> list[str]:
    if not source_event_id or not target_event_id:
        return []
    pending: deque[str] = deque([source_event_id])
    parents: dict[str, str | None] = {source_event_id: None}
    while pending:
        event_id = pending.popleft()
        if event_id == target_event_id:
            path: list[str] = []
            current: str | None = event_id
            while current is not None:
                path.append(current)
                current = parents[current]
            return list(reversed(path))
        for child_id in children.get(event_id, []):
            if child_id not in parents:
                parents[child_id] = event_id
                pending.append(child_id)
    return []


def _compress_material_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(events) <= 6:
        return events
    selected = [events[0]]
    selected_ids = {str(events[0]["id"])}
    for event in events[1:-1]:
        if event["event_type"] not in _PREFERRED_COMPRESSION_TYPES:
            continue
        if len(selected) >= 5:
            break
        selected.append(event)
        selected_ids.add(str(event["id"]))
    for event in events[1:-1]:
        if len(selected) >= 5:
            break
        if str(event["id"]) in selected_ids:
            continue
        selected.append(event)
    selected.append(events[-1])
    return selected

from __future__ import annotations

from collections import deque
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

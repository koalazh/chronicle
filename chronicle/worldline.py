from __future__ import annotations

import copy
import json
from typing import Any, Iterable

from .models import CanonEvent, WorldEffect


def empty_projection(tick: int = 0) -> dict[str, Any]:
    return {
        "tick": tick,
        "location_control": {},
        "route_pressure": {},
        "capital_status": "standing",
        "command_state": "active",
        "force_posture": {},
        "information_state": {},
        "season": {},
        "court_decision": {},
        "relief_order": {},
        "supply_state": {},
        "command_conflict": {},
        "belief_pressure": {},
        "simulation_boundary": False,
        "effects": {},
        "last_event_id": None,
        "locations": {},
        "orders": [],
        "messages": [],
        "preparations": [],
        "force_redeployments": [],
        "authority_changes": [],
        "disclosures": {},
    }


def apply_world_effect(projection: dict[str, Any], effect: WorldEffect | dict[str, Any]) -> None:
    effect_type = effect.type if isinstance(effect, WorldEffect) else str(effect.get("type", ""))
    target = effect.target if isinstance(effect, WorldEffect) else str(effect.get("target", ""))
    value = effect.value if isinstance(effect, WorldEffect) else effect.get("value")
    projection.setdefault("effects", {}).setdefault(effect_type, {})[target] = value
    if effect_type == "control_change":
        projection.setdefault("location_control", {})[target] = value
    elif effect_type == "route_pressure":
        projection.setdefault("route_pressure", {})[target] = value
    elif effect_type == "capital_status":
        projection["capital_status"] = value
    elif effect_type == "command_state":
        projection["command_state"] = value
    elif effect_type in {"force_posture", "force_readiness"}:
        projection.setdefault("force_posture", {})[target] = value
    elif effect_type in {"information_state", "capital_security"}:
        projection.setdefault("information_state", {})[target] = value
    elif effect_type in {
        "season_open",
        "court_decision",
        "relief_order",
        "supply_state",
        "command_conflict",
        "belief_pressure",
    }:
        projection_name = {
            "season_open": "season",
            "court_decision": "court_decision",
            "relief_order": "relief_order",
            "supply_state": "supply_state",
            "command_conflict": "command_conflict",
            "belief_pressure": "belief_pressure",
        }[effect_type]
        projection.setdefault(projection_name, {})[target] = value
    elif effect_type == "simulation_boundary":
        projection["simulation_boundary"] = bool(value)


def project_canon(events: Iterable[CanonEvent], tick: int) -> dict[str, Any]:
    projection = empty_projection(tick)
    for event in events:
        if event.tick > tick:
            break
        projection["tick"] = event.tick
        projection["last_event_id"] = event.id
        for effect in event.world_effects:
            apply_world_effect(projection, effect)
    projection["tick"] = tick
    return projection


def apply_ledger_event(projection: dict[str, Any], event: dict[str, Any]) -> None:
    """Apply one derived event; the ledger remains the authority for branch facts."""

    event_type = event["event_type"]
    payload = event.get("payload_json", event.get("payload", {}))
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    projection["tick"] = max(int(projection.get("tick", 0)), int(event.get("tick", 0)))
    if event_type == "CANON_EVENT":
        projection["last_event_id"] = payload.get("event_id", projection.get("last_event_id"))
        for effect in payload.get("world_effects", []):
            apply_world_effect(projection, effect)
    elif event_type in {"ENTRY_ENTERED", "BRANCH_EFFECT_APPLIED"}:
        for effect in payload.get("world_effects", []):
            apply_world_effect(projection, effect)
    elif event_type == "MESSAGE_DISPATCHED":
        messages = projection.setdefault("messages", [])
        message = copy.deepcopy(payload)
        message.setdefault("status", "in_transit")
        if not any(item.get("id") == message.get("id") for item in messages):
            messages.append(message)
    elif event_type == "MESSAGE_DELIVERED":
        for message in projection.setdefault("messages", []):
            if message.get("id") == payload.get("message_id"):
                message.update({"status": "delivered", "delivered_tick": event["tick"]})
    elif event_type == "ORDER_ISSUED":
        projection.setdefault("orders", []).append(copy.deepcopy(payload))
    elif event_type == "MOVEMENT_PREPARED":
        projection.setdefault("preparations", []).append(copy.deepcopy(payload))
    elif event_type == "FORCE_REDEPLOYED":
        projection.setdefault("force_redeployments", []).append(copy.deepcopy(payload))
    elif event_type == "PRINCIPAL_MOVED":
        seat = payload.get("seat", "")
        target = payload.get("target", "")
        if seat and target:
            projection.setdefault("locations", {})[seat] = target
    elif event_type == "AUTHORITY_APPOINTED":
        projection.setdefault("authority_changes", []).append(copy.deepcopy(payload))
    elif event_type == "DISCLOSURE_SET":
        projection.setdefault("disclosures", {})[payload.get("target", "world")] = payload.get("value")
    elif event_type == "WORLDLINE_SEALED":
        projection["sealed"] = True

    projection["last_ledger_event_id"] = event.get("id")


def project_worldline(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered = list(events)
    if not ordered:
        return empty_projection()
    first = ordered[0]
    first_payload = first.get("payload_json", first.get("payload", {}))
    if isinstance(first_payload, str):
        first_payload = json.loads(first_payload)
    base = first_payload.get("base_projection")
    if base is None and first.get("event_type") == "LEGACY_IMPORT":
        base = first_payload.get("state_json")
    projection = empty_projection(int(first.get("tick", 0)))
    if isinstance(base, dict):
        projection.update(copy.deepcopy(base))
    for event in ordered[1:]:
        apply_ledger_event(projection, event)
    projection["tick"] = int(ordered[-1].get("tick", projection.get("tick", 0)))
    return projection


def descendant_events(events: Iterable[dict[str, Any]], root_ids: set[str]) -> list[dict[str, Any]]:
    selected = set(root_ids)
    changed = True
    ordered = list(events)
    while changed:
        changed = False
        for event in ordered:
            parents = event.get("causal_parent_ids", [])
            if isinstance(parents, str):
                parents = json.loads(parents)
            if event.get("id") not in selected and selected.intersection(parents):
                selected.add(event["id"])
                changed = True
    return [event for event in ordered if event.get("id") in selected]

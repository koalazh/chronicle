from __future__ import annotations

from typing import Any

WATCH_ATTENTION_EVENT_TYPES = frozenset(
    {
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "OFFER_ACCEPTED",
        "OFFER_REJECTED",
        "OFFER_WITHDRAWN",
        "OFFER_EXPIRED",
        "AGREEMENT_CREATED",
        "AGREEMENT_FULFILLED",
        "AGREEMENT_BREACHED",
        "OPERATION_STARTED",
        "OPERATION_COMPLETED",
        "INVESTIGATION_COMPLETED",
        "OBSERVATION_OBTAINED",
        "MOVEMENT_STARTED",
        "MOVEMENT_ARRIVED",
        "PRESSURE_APPLIED",
        "RESOLUTION_GATE_REACHED",
        "RESOLUTION_APPLIED",
        "CRISIS_SETTLED",
    }
)


def watch_attention(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Classify the first new public event worth surfacing to a Watch user."""

    for event in events:
        event_type = str(event["event_type"])
        if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            if event["payload"].get("source") == "checkpoint":
                continue
        elif event_type not in WATCH_ATTENTION_EVENT_TYPES:
            continue
        return {
            "mode": "WATCH",
            "tick": int(event["tick"]),
            "event_id": event["id"],
            "event_type": event_type,
        }
    return None


VOLUME_ATTENTION_EVENT_TYPES = {
    "CRISIS_ACTIVATED": "PRESENCE_OPPORTUNITY",
    "CRISIS_CHECKPOINT_ENTERED": "PRESENCE_OPPORTUNITY",
    "MESSAGE_DELIVERED": "DECISION",
    "CRISIS_PRESSURE_APPLIED": "MEANING",
    "CRISIS_SETTLED": "MEANING",
    "FIELD_EVENT_APPLIED": "MEANING",
}


def volume_attention(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Classify already-committed events for the V6 editorial shell."""

    for event in events:
        event_type = str(event.get("event_type", ""))
        kind = VOLUME_ATTENTION_EVENT_TYPES.get(event_type)
        if kind is None:
            continue
        return {
            "kind": kind,
            "tick": int(event.get("tick", 0)),
            "event_id": str(event.get("id", "")),
        }
    return None

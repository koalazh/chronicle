from __future__ import annotations

from typing import Any

WAKE_PRIORITIES = {
    "RESOLUTION_GATE": 0,
    "RESOLUTION_RESULT": 1,
    "AGREEMENT_CHANGE": 2,
    "OFFER_CHANGE": 3,
    "OPERATION_RESULT": 4,
    "INVESTIGATION_RESULT": 5,
    "OBSERVATION": 6,
    "MESSAGE": 7,
    "PRESSURE": 8,
    "REVISIT_DUE": 9,
    "REFLECTION": 10,
    "ORIENT": 11,
}

COALESCIBLE_WAKE_TYPES = frozenset(
    {
        "RESOLUTION_RESULT",
        "AGREEMENT_CHANGE",
        "OFFER_CHANGE",
        "OPERATION_RESULT",
        "INVESTIGATION_RESULT",
        "OBSERVATION",
        "MESSAGE",
        "PRESSURE",
        "REVISIT_DUE",
    }
)


def wake_sort_key(wake: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        WAKE_PRIORITIES.get(str(wake["wake_type"]), 99),
        str(wake["wake_type"]),
        str(wake["trigger_event_id"]),
        str(wake["id"]),
    )


def wake_batches(wakes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Merge ordinary same-tick inputs into one logical Subject attention."""

    merged = sorted(
        (wake for wake in wakes if wake["wake_type"] in COALESCIBLE_WAKE_TYPES),
        key=wake_sort_key,
    )
    batches = [[wake] for wake in wakes if wake["wake_type"] not in COALESCIBLE_WAKE_TYPES]
    if merged:
        batches.append(merged)
    return sorted(batches, key=lambda batch: wake_sort_key(batch[0]))

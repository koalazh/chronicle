from __future__ import annotations

from enum import StrEnum
from typing import Any

from .crisis import (
    CrisisPack,
    HistoricalCompatibilityPrecondition,
    HistoricalCompatibilityPreconditionKind,
)


class HistoricalCompatibilityStatus(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    CONTINGENT = "CONTINGENT"
    INVALIDATED = "INVALIDATED"
    UNKNOWN = "UNKNOWN"


def evaluate_historical_compatibility(
    pack: CrisisPack, projection: dict[str, Any]
) -> list[dict[str, Any]]:
    """Evaluate only curated reference-event prerequisites against World Truth.

    This deliberately asks whether current modeled facts retain a reference
    event's stated necessary conditions. It does not predict a later event.
    """

    results: list[dict[str, Any]] = []
    for anchor in pack.crisis.anchors:
        if not anchor.compatibility_preconditions:
            continue
        checks = [
            _evaluate_precondition(precondition, projection)
            for precondition in anchor.compatibility_preconditions
        ]
        status = _aggregate_status([check["status"] for check in checks])
        results.append(
            {
                "anchor_id": anchor.id,
                "title": anchor.title,
                "status": status.value,
                "assertion_ids": list(anchor.assertion_ids),
                "preconditions": checks,
                "summary": _summary(status),
            }
        )
    return results


def _evaluate_precondition(
    precondition: HistoricalCompatibilityPrecondition, projection: dict[str, Any]
) -> dict[str, Any]:
    status: HistoricalCompatibilityStatus
    actual_value = ""
    if precondition.kind == HistoricalCompatibilityPreconditionKind.UNMODELED:
        status = HistoricalCompatibilityStatus.UNKNOWN
        actual_value = "UNMODELED"
    elif precondition.kind == HistoricalCompatibilityPreconditionKind.ENTITY_STATE:
        entity = projection.get("entities", {}).get(precondition.subject)
        if entity is None:
            status = HistoricalCompatibilityStatus.UNKNOWN
            actual_value = "UNAVAILABLE"
        else:
            actual_value = str(entity.get("state", ""))
            status = _state_status(precondition, actual_value)
    elif precondition.kind == HistoricalCompatibilityPreconditionKind.ACTOR_POSITION:
        position = projection.get("positions", {}).get(precondition.subject)
        if position is None:
            status = HistoricalCompatibilityStatus.UNKNOWN
            actual_value = "UNAVAILABLE"
        else:
            actual_value = str(position)
            status = _state_status(precondition, actual_value)
    else:
        status = HistoricalCompatibilityStatus.UNKNOWN
        actual_value = "UNSUPPORTED"
    return {
        "id": precondition.id,
        "kind": precondition.kind.value,
        "description": precondition.description,
        "subject": precondition.subject,
        "actual_value": actual_value,
        "status": status.value,
    }


def _state_status(
    precondition: HistoricalCompatibilityPrecondition, actual_value: str
) -> HistoricalCompatibilityStatus:
    if actual_value in precondition.contradicted_values:
        return HistoricalCompatibilityStatus.INVALIDATED
    if actual_value in precondition.satisfied_values:
        return HistoricalCompatibilityStatus.COMPATIBLE
    return HistoricalCompatibilityStatus.CONTINGENT


def _aggregate_status(statuses: list[str]) -> HistoricalCompatibilityStatus:
    values = {HistoricalCompatibilityStatus(status) for status in statuses}
    if HistoricalCompatibilityStatus.INVALIDATED in values:
        return HistoricalCompatibilityStatus.INVALIDATED
    if HistoricalCompatibilityStatus.UNKNOWN in values:
        return HistoricalCompatibilityStatus.UNKNOWN
    if HistoricalCompatibilityStatus.CONTINGENT in values:
        return HistoricalCompatibilityStatus.CONTINGENT
    return HistoricalCompatibilityStatus.COMPATIBLE


def _summary(status: HistoricalCompatibilityStatus) -> str:
    return {
        HistoricalCompatibilityStatus.COMPATIBLE: (
            "当前已保留该历史节点在本模型中的必要前提；这不表示它必然发生。"
        ),
        HistoricalCompatibilityStatus.CONTINGENT: (
            "至少一项必要前提仍未定型，已知后续暂时不能直接沿用。"
        ),
        HistoricalCompatibilityStatus.INVALIDATED: (
            "至少一项明确建模的必要前提已经不成立，已知后续不能直接沿用。"
        ),
        HistoricalCompatibilityStatus.UNKNOWN: (
            "模型没有表示至少一项必要前提，因此无法判断该历史节点是否仍可直接沿用。"
        ),
    }[status]

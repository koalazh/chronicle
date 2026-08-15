from __future__ import annotations

import copy
from typing import Any

from .db import stable_hash

COURSE_SCHEMA_VERSION = 1


class DecisionHorizonError(ValueError):
    """A Current Course or typed open dependency is invalid."""


_DEPENDENCY_FIELDS = {
    "DEADLINE": "due_tick",
    "MESSAGE_FROM": "actor_id",
    "OBSERVATION_FOR": "investigation_id",
    "OPERATION_OUTCOME": "operation_id",
    "OFFER_CHANGE": "offer_id",
    "AGREEMENT_CHANGE": "agreement_id",
    "ENTITY_OBSERVED_CHANGE": "entity_id",
}


def normalize_open_dependencies(
    raw_dependencies: Any,
    *,
    current_tick: int,
    require_future_deadline: bool = True,
) -> list[dict[str, Any]]:
    """Validate the small, data-only dependency vocabulary used by a Course."""

    if raw_dependencies is None:
        return []
    if not isinstance(raw_dependencies, list):
        raise DecisionHorizonError("open_dependencies must be a list")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in raw_dependencies:
        if not isinstance(raw, dict):
            raise DecisionHorizonError("each open dependency must be an object")
        dependency_type = str(raw.get("type", "")).strip().upper()
        required_field = _DEPENDENCY_FIELDS.get(dependency_type)
        if required_field is None:
            raise DecisionHorizonError(f"unsupported open dependency type: {dependency_type}")
        allowed_fields = {"id", "type", required_field}
        unsupported = sorted(set(raw) - allowed_fields)
        if unsupported:
            raise DecisionHorizonError(
                "open dependency has unsupported fields: " + ", ".join(unsupported)
            )

        value = raw.get(required_field)
        if dependency_type == "DEADLINE":
            if isinstance(value, bool):
                raise DecisionHorizonError("DEADLINE due_tick must be an integer")
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise DecisionHorizonError("DEADLINE due_tick must be an integer") from exc
            if require_future_deadline and value <= current_tick:
                raise DecisionHorizonError("DEADLINE due_tick must be after the current tick")
        else:
            value = str(value or "").strip()
            if not value:
                raise DecisionHorizonError(
                    f"{dependency_type} requires {required_field}"
                )

        dependency_id = str(raw.get("id", "")).strip()
        if not dependency_id:
            dependency_id = "dependency-" + stable_hash(
                {"type": dependency_type, required_field: value}
            )[:12]
        if dependency_id in seen_ids:
            raise DecisionHorizonError(f"duplicate open dependency id: {dependency_id}")
        seen_ids.add(dependency_id)
        normalized.append(
            {"id": dependency_id, "type": dependency_type, required_field: value}
        )
    return normalized


def current_course_from_plan(
    plan: list[Any], *, fallback_tick: int = 0
) -> dict[str, Any] | None:
    """Return the current persisted Course, or no Course when none exists."""

    raw = next((item for item in plan if isinstance(item, dict)), None)
    if raw is None or _integer(raw.get("course_schema_version"), -1) != COURSE_SCHEMA_VERSION:
        return None
    current = copy.deepcopy(raw)
    objective = str(current.get("course") or "").strip()
    updated_tick = _integer(current.get("updated_tick"), fallback_tick)
    established_tick = _integer(current.get("established_tick"), updated_tick)
    last_deliberated_tick = _integer(current.get("last_deliberated_tick"), established_tick)
    dependencies = normalize_open_dependencies(
        current.get("open_dependencies", []),
        current_tick=last_deliberated_tick,
        require_future_deadline=False,
    )
    return {
        **current,
        "course_schema_version": _integer(
            current.get("course_schema_version"), COURSE_SCHEMA_VERSION
        ),
        "course": objective,
        "status": str(current.get("status") or "IN_FORCE"),
        "established_tick": established_tick,
        "established_event_id": str(current.get("established_event_id") or ""),
        "open_dependencies": dependencies,
        "explicit_rationale": str(current.get("explicit_rationale", "") or ""),
        "evidence_event_ids": [
            str(event_id)
            for event_id in current.get("evidence_event_ids", [])
            if str(event_id)
        ],
        "last_deliberated_tick": last_deliberated_tick,
        "last_deliberated_event_id": str(
            current.get("last_deliberated_event_id") or ""
        ),
    }


def build_current_course(
    intent: dict[str, Any],
    *,
    course_version: str,
    tick: int,
    event_id: str,
) -> dict[str, Any]:
    """Build the one persisted Current Course from a validated intent."""

    return {
        "course_schema_version": COURSE_SCHEMA_VERSION,
        "version": course_version,
        "course": str(intent["objective"]),
        "status": "IN_FORCE",
        "established_tick": tick,
        "established_event_id": event_id,
        "open_dependencies": copy.deepcopy(intent.get("open_dependencies", [])),
        "explicit_rationale": str(intent.get("rationale", "")),
        "evidence_event_ids": list(intent.get("evidence_event_ids", [])),
        "last_deliberated_tick": tick,
        "last_deliberated_event_id": event_id,
        "objective": str(intent["objective"]),
        "steps": list(intent["steps"]),
        "rationale": str(intent.get("rationale", "")),
        "rationale_source": str(intent.get("rationale_source", "")),
        "experience_refs": list(intent.get("experience_refs", [])),
        "reconsider_when": list(intent.get("reconsider_when", [])),
        "updated_tick": tick,
    }


def _integer(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

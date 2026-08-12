from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .decision_horizon import current_course_from_plan


class AttentionDecision(StrEnum):
    BACKGROUND = "BACKGROUND"
    REOPEN = "REOPEN"


@dataclass(frozen=True)
class AttentionResult:
    decision: AttentionDecision
    reason_code: str
    trigger_event_ids: tuple[str, ...]
    matched_dependency_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "trigger_event_ids": list(self.trigger_event_ids),
            "matched_dependency_ids": list(self.matched_dependency_ids),
        }


def evaluate_attention(
    lifetime: dict[str, Any],
    new_known_events: list[dict[str, Any]],
    projection: dict[str, Any],
) -> AttentionResult:
    """Decide whether admitted facts warrant a new cognition boundary.

    The Host supplies only facts that were admitted to this Lifetime's
    Knowledge.  This function is deliberately pure: it never reads the
    database, calls a model, or assigns a World action.
    """

    trigger_event_ids = _event_ids(new_known_events)
    current_tick = int(projection.get("tick", 0))
    course = current_course_from_plan(
        list(lifetime.get("plan", [])), fallback_tick=current_tick
    )
    if course is None:
        return AttentionResult(
            AttentionDecision.REOPEN,
            "NO_CURRENT_COURSE",
            trigger_event_ids,
        )

    structural_shocks = [
        event
        for event in new_known_events
        if bool(event.get("structural_shock"))
    ]
    if structural_shocks:
        return AttentionResult(
            AttentionDecision.REOPEN,
            "STRUCTURAL_WORLD_SHOCK",
            _event_ids(structural_shocks),
        )

    matched_dependency_ids, matching_events = _matched_dependencies(
        course.get("open_dependencies", []), new_known_events
    )
    if matched_dependency_ids:
        return AttentionResult(
            AttentionDecision.REOPEN,
            "OPEN_DEPENDENCY_MATCH",
            _event_ids(matching_events),
            tuple(matched_dependency_ids),
        )

    unexpected_consequences = [
        event
        for event in new_known_events
        if str(event.get("actor_id", "")) == str(lifetime.get("seat", ""))
        and bool(event.get("unexpected_consequence"))
    ]
    if unexpected_consequences:
        return AttentionResult(
            AttentionDecision.REOPEN,
            "OWN_CONSEQUENCE_UNEXPECTED",
            _event_ids(unexpected_consequences),
        )

    return AttentionResult(
        AttentionDecision.BACKGROUND,
        "NO_REOPEN_CONDITION",
        trigger_event_ids,
    )


def _matched_dependencies(
    dependencies: list[dict[str, Any]], new_known_events: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    matched: list[str] = []
    matching_events: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        events = [
            event for event in new_known_events if _dependency_matches(dependency, event)
        ]
        if events:
            dependency_id = str(dependency.get("id", ""))
            if dependency_id:
                matched.append(dependency_id)
                matching_events.extend(events)
    return list(dict.fromkeys(matched)), _dedupe_events(matching_events)


def _dependency_matches(dependency: dict[str, Any], event: dict[str, Any]) -> bool:
    dependency_type = str(dependency.get("type", ""))
    if dependency_type == "DEADLINE":
        return (
            event.get("event_type") == "DECISION_DEPENDENCY_DUE"
            and int(event.get("due_tick", -1)) == int(dependency.get("due_tick", -2))
        )
    if dependency_type == "MESSAGE_FROM":
        return (
            event.get("event_type") == "MESSAGE_DELIVERED"
            and str(event.get("actor_id", "")) == str(dependency.get("actor_id", ""))
        )
    if dependency_type == "OBSERVATION_FOR":
        return (
            event.get("event_type") == "OBSERVATION_OBTAINED"
            and str(event.get("investigation_id", ""))
            == str(dependency.get("investigation_id", ""))
        )
    if dependency_type == "OPERATION_OUTCOME":
        return (
            event.get("event_type") == "OPERATION_COMPLETED"
            and str(event.get("operation_id", "")) == str(dependency.get("operation_id", ""))
        )
    if dependency_type == "OFFER_CHANGE":
        return (
            event.get("event_type") == "OFFER_CHANGED"
            and str(event.get("offer_id", "")) == str(dependency.get("offer_id", ""))
        )
    if dependency_type == "AGREEMENT_CHANGE":
        return (
            event.get("event_type") == "AGREEMENT_CHANGED"
            and str(event.get("agreement_id", "")) == str(dependency.get("agreement_id", ""))
        )
    if dependency_type == "ENTITY_OBSERVED_CHANGE":
        return (
            str(dependency.get("entity_id", ""))
            in {str(entity_id) for entity_id in event.get("entity_ids", [])}
        )
    return False


def _event_ids(events: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(event.get("event_id", "")) for event in events if str(event.get("event_id", ""))
        )
    )


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("event_id", ""))
        if event_id and event_id not in unique:
            unique[event_id] = event
    return list(unique.values())

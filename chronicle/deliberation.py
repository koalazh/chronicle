from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DELIBERATION_OUTCOMES = frozenset({"HOLD", "REVISE"})
DELIBERATION_WORLD_TOOLS = frozenset(
    {"communicate", "investigate", "manage_offer", "operate", "schedule_revisit"}
)


class DeliberationError(ValueError):
    """A V6 Deliberation proposal is not a complete typed commit."""


@dataclass(frozen=True)
class DeliberationProposal:
    outcome: str
    course: dict[str, Any]
    open_dependencies: list[dict[str, Any]]
    belief_updates: list[dict[str, Any]]
    world_actions: list[dict[str, Any]]
    rationale_source: str = ""
    belief_source: str = ""
    experience_refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        result = {
            "outcome": self.outcome,
            "course": self.course,
            "open_dependencies": self.open_dependencies,
            "belief_updates": self.belief_updates,
            "world_actions": self.world_actions,
            "rationale_source": self.rationale_source,
            "belief_source": self.belief_source,
        }
        if self.experience_refs:
            result["experience_refs"] = list(self.experience_refs)
        return result


def normalize_deliberation(raw: dict[str, Any]) -> DeliberationProposal:
    """Validate only the data shape; Host validates evidence and World effects."""

    if not isinstance(raw, dict):
        raise DeliberationError("Deliberation proposal must be an object")
    unsupported = sorted(
        set(raw)
        - {
            "outcome",
            "course",
            "open_dependencies",
            "belief_updates",
            "world_actions",
            "world_action",
            "rationale_source",
            "belief_source",
            "experience_refs",
        }
    )
    if unsupported:
        raise DeliberationError(
            "Deliberation proposal has unsupported fields: " + ", ".join(unsupported)
        )
    outcome = str(raw.get("outcome", "")).strip().upper()
    if outcome not in DELIBERATION_OUTCOMES:
        raise DeliberationError("outcome must be HOLD or REVISE")

    course = raw.get("course") or {}
    if not isinstance(course, dict):
        raise DeliberationError("course must be an object")
    unsupported_course = sorted(
        set(course) - {"summary", "objective", "steps", "evidence_event_ids", "rationale", "rationale_source"}
    )
    if unsupported_course:
        raise DeliberationError(
            "course has unsupported fields: " + ", ".join(unsupported_course)
        )
    if outcome == "REVISE" and not str(course.get("summary", course.get("objective", ""))).strip():
        raise DeliberationError("REVISE requires course.summary")

    raw_dependencies = raw.get("open_dependencies", [])
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, dict) for item in raw_dependencies
    ):
        raise DeliberationError("open_dependencies must be a list of objects")
    raw_beliefs = raw.get("belief_updates", [])
    if not isinstance(raw_beliefs, list) or not all(
        isinstance(item, dict) for item in raw_beliefs
    ):
        raise DeliberationError("belief_updates must be a list of objects")

    world_actions = raw.get("world_actions")
    if world_actions is None and raw.get("world_action") is not None:
        world_actions = [raw["world_action"]]
    world_actions = world_actions or []
    if not isinstance(world_actions, list) or len(world_actions) > 1:
        raise DeliberationError("world_actions must contain at most one action")
    normalized_actions: list[dict[str, Any]] = []
    for action in world_actions:
        if not isinstance(action, dict):
            raise DeliberationError("each world action must be an object")
        tool = str(action.get("tool", "")).strip()
        arguments = action.get("arguments", {})
        if tool not in DELIBERATION_WORLD_TOOLS:
            raise DeliberationError(f"unsupported Deliberation world action: {tool}")
        if not isinstance(arguments, dict):
            raise DeliberationError("world action arguments must be an object")
        normalized_actions.append({"tool": tool, "arguments": dict(arguments)})

    return DeliberationProposal(
        outcome=outcome,
        course=dict(course),
        open_dependencies=[dict(item) for item in raw_dependencies],
        belief_updates=[dict(item) for item in raw_beliefs],
        world_actions=normalized_actions,
        rationale_source=str(raw.get("rationale_source", "")).strip(),
        belief_source=str(raw.get("belief_source", "")).strip(),
        experience_refs=[
            str(item).strip()
            for item in raw.get("experience_refs", [])
            if str(item).strip()
        ],
    )

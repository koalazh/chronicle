from __future__ import annotations

import unicodedata
from typing import Any


def plan_text_key(value: Any) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", str(value)).casefold()
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def plan_texts_key(values: list[Any]) -> tuple[str, ...]:
    return tuple(plan_text_key(value) for value in values)


def same_material_plan(current: dict[str, Any] | None, candidate: dict[str, Any]) -> bool:
    if current is None:
        return False
    return (
        plan_text_key(current.get("objective", ""))
        == plan_text_key(candidate.get("objective", ""))
        and plan_texts_key(current.get("steps", []))
        == plan_texts_key(candidate.get("steps", []))
        and plan_texts_key(current.get("reconsider_when", []))
        == plan_texts_key(candidate.get("reconsider_when", []))
    )


def build_actor_perspective(
    *,
    run_id: str,
    actor_id: str,
    projection: dict[str, Any],
    knowledge: list[Any],
    beliefs: dict[str, Any],
    plan: list[Any],
    revisits: list[Any],
    resources: dict[str, Any],
    authority: list[Any],
    affordances: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the private projection after the Host has built its affordances."""

    return {
        "run_id": run_id,
        "actor_id": actor_id,
        "tick": int(projection["tick"]),
        "location": projection["positions"][actor_id],
        "knowledge": list(knowledge),
        "beliefs": dict(beliefs),
        "plan": list(plan),
        "revisits": list(revisits),
        "resources": dict(resources),
        "authority": list(authority),
        **affordances,
    }


def project_world_view(projection: dict[str, Any], pack: Any) -> dict[str, Any]:
    """Build the public World projection without exposing Subject private state."""

    movements = {
        movement["actor_id"]: movement
        for movement in projection.get("movements", [])
        if movement["status"] == "in_transit"
    }
    return {
        "tick": int(projection["tick"]),
        "surface": pack.surface_projection(projection, include_messages=True),
        "corridor": [
            location.model_dump(mode="json")
            for location in sorted(pack.crisis.corridor, key=lambda item: item.order)
        ],
        "actors": [
            {
                "id": actor.id,
                "display_name": actor.display_name,
                "location": projection["positions"][actor.id],
                "movement": movements.get(actor.id),
            }
            for actor in pack.crisis.actors
        ],
        "messages": list(projection.get("messages", [])),
        "entities": list(projection.get("entities", {}).values()),
        "operations": list(projection.get("operations", [])),
        "investigations": list(projection.get("investigations", [])),
        "offers": list(projection.get("offers", [])),
        "agreements": list(projection.get("agreements", [])),
        "pressures": [
            pressure
            for pressure in projection.get("pressures", [])
            if pressure.get("status") == "APPLIED"
        ],
        "resolution": dict(projection.get("resolution", {})),
        "settlement": dict(projection.get("settlement", {})),
        "boundary": pack.crisis.simulation_boundary.model_dump(mode="json"),
    }

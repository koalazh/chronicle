from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from .models import Assertion, HistoricalSource, StrictModel


class CrisisValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class HistoricalPolicy(StrEnum):
    EXOGENOUS = "EXOGENOUS"
    CONDITIONAL_ANCHOR = "CONDITIONAL_ANCHOR"
    REFERENCE_ONLY = "REFERENCE_ONLY"


class RoleCharter(StrictModel):
    who: str
    responsibility: list[str]
    authority: list[str]
    tensions: list[str]


class CrisisActorDefinition(StrictModel):
    id: str
    display_name: str
    role_charter: RoleCharter
    initial_location: str
    initial_knowledge: list[str]
    initial_beliefs: dict[str, str]
    resources: dict[str, str | int]
    world_authority: list[str]


class CorridorLocation(StrictModel):
    id: str
    display_name: str
    order: int = Field(ge=0)


class CrisisRoute(StrictModel):
    id: str
    from_location: str
    to_location: str
    travel_days: int = Field(gt=0)


class InTransitMessage(StrictModel):
    id: str
    sender: str
    recipient: str
    dispatch_tick: int
    delivery_tick: int
    content: str
    assertion_ids: list[str]
    disputed: bool = False


class CrisisCheckpoint(StrictModel):
    native_date_window: str
    summary: str
    start_tick: int = 0
    safety_horizon_days: int = Field(ge=7, le=10)
    facts: list[str]
    unresolved: list[str]
    in_transit: list[InTransitMessage]


class HistoricalAnchor(StrictModel):
    id: str
    title: str
    tick: int
    policy: HistoricalPolicy
    assertion_ids: list[str]
    actor_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)


class SimulationBoundary(StrictModel):
    stop_before: str
    reason: str
    maximum_tick: int = Field(gt=0)


class CrisisDefinition(StrictModel):
    id: str
    title: str
    subtitle: str
    checkpoint: CrisisCheckpoint
    simulation_boundary: SimulationBoundary
    actors: list[CrisisActorDefinition]
    corridor: list[CorridorLocation]
    routes: list[CrisisRoute]
    anchors: list[HistoricalAnchor]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise CrisisValidationError([f"{path}: root must be a mapping"])
    return value


@dataclass(frozen=True)
class CrisisPack:
    root: Path
    crisis: CrisisDefinition
    sources: tuple[HistoricalSource, ...]
    assertions: tuple[Assertion, ...]

    @classmethod
    def load(cls, root: Path) -> "CrisisPack":
        root = root.resolve()
        crisis = CrisisDefinition.model_validate(_read_yaml(root / "crisis.yaml"))
        source_data = _read_yaml(root / "sources.yaml")
        sources = tuple(HistoricalSource.model_validate(item) for item in source_data["sources"])
        assertions = tuple(Assertion.model_validate(item) for item in source_data["assertions"])
        pack = cls(root=root, crisis=crisis, sources=sources, assertions=assertions)
        pack.validate()
        return pack

    @property
    def actor_by_id(self) -> dict[str, CrisisActorDefinition]:
        return {actor.id: actor for actor in self.crisis.actors}

    @property
    def assertion_by_id(self) -> dict[str, Assertion]:
        return {assertion.id: assertion for assertion in self.assertions}

    @property
    def location_by_id(self) -> dict[str, CorridorLocation]:
        return {location.id: location for location in self.crisis.corridor}

    def validate(self) -> None:
        errors: list[str] = []
        actor_ids = [actor.id for actor in self.crisis.actors]
        expected_actors = {"li-zicheng", "wu-sangui", "dorgon"}
        if len(actor_ids) != len(set(actor_ids)):
            errors.append("actors: ids must be unique")
        if set(actor_ids) != expected_actors:
            errors.append("actors: before-shanhaiguan requires Li Zicheng, Wu Sangui and Dorgon")

        source_ids = {source.id for source in self.sources}
        assertion_ids = [assertion.id for assertion in self.assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            errors.append("assertions: ids must be unique")
        known_assertions = set(assertion_ids)
        required_works = {"《清实录·世祖章皇帝实录》", "《明季北略》", "《清史稿》"}
        if not required_works.issubset({source.work for source in self.sources}):
            errors.append("sources: Qing Shilu, Mingji Beilue and Qingshi Gao are required")
        for assertion in self.assertions:
            if not assertion.normalized_evidence:
                errors.append(f"assertion {assertion.id}: normalized evidence is required")
            for source_id in assertion.source_ids:
                if source_id not in source_ids:
                    errors.append(f"assertion {assertion.id}: unknown source {source_id}")

        location_ids = [location.id for location in self.crisis.corridor]
        if len(location_ids) != len(set(location_ids)):
            errors.append("corridor: location ids must be unique")
        orders = [location.order for location in self.crisis.corridor]
        if sorted(orders) != list(range(len(orders))):
            errors.append("corridor: order must be contiguous from zero")
        known_locations = set(location_ids)
        for actor in self.crisis.actors:
            if actor.initial_location not in known_locations:
                errors.append(f"actor {actor.id}: unknown initial location {actor.initial_location}")
            if not actor.role_charter.responsibility or not actor.role_charter.authority:
                errors.append(f"actor {actor.id}: role charter is incomplete")
            required_tools = {"communicate", "update_plan", "schedule_followup"}
            if not required_tools.issubset(actor.world_authority) or not {
                "hold",
                "prepare",
                "move",
            }.intersection(actor.world_authority):
                errors.append(f"actor {actor.id}: world authority is incomplete")
            for assertion_id in actor.initial_knowledge:
                if assertion_id not in known_assertions:
                    errors.append(f"actor {actor.id}: unknown knowledge assertion {assertion_id}")
        for route in self.crisis.routes:
            if route.from_location not in known_locations or route.to_location not in known_locations:
                errors.append(f"route {route.id}: endpoint is not on the corridor")

        checkpoint = self.crisis.checkpoint
        if self.crisis.simulation_boundary.maximum_tick > checkpoint.safety_horizon_days:
            errors.append("boundary: maximum tick exceeds the safety horizon")
        for message in checkpoint.in_transit:
            if message.sender not in expected_actors or message.recipient not in expected_actors:
                errors.append(f"message {message.id}: sender and recipient must be crisis actors")
            if message.delivery_tick <= checkpoint.start_tick:
                errors.append(f"message {message.id}: must arrive after the checkpoint")
            if message.dispatch_tick >= message.delivery_tick:
                errors.append(f"message {message.id}: delivery must follow dispatch")
            for assertion_id in message.assertion_ids:
                if assertion_id not in known_assertions:
                    errors.append(f"message {message.id}: unknown assertion {assertion_id}")

        for anchor in self.crisis.anchors:
            for assertion_id in anchor.assertion_ids:
                if assertion_id not in known_assertions:
                    errors.append(f"anchor {anchor.id}: unknown assertion {assertion_id}")
            unknown_actors = set(anchor.actor_ids) - expected_actors
            if unknown_actors:
                errors.append(f"anchor {anchor.id}: unknown actors {', '.join(sorted(unknown_actors))}")
            if anchor.actor_ids and anchor.policy != HistoricalPolicy.REFERENCE_ONLY:
                errors.append(
                    f"anchor {anchor.id}: post-checkpoint actor actions must be REFERENCE_ONLY"
                )
        if errors:
            raise CrisisValidationError(errors)

    def initial_perspective(self, actor_id: str) -> dict[str, Any]:
        actor = self.actor_by_id[actor_id]
        return {
            "actor_id": actor.id,
            "location": actor.initial_location,
            "knowledge": [
                self.assertion_by_id[assertion_id].claim for assertion_id in actor.initial_knowledge
            ],
            "beliefs": dict(actor.initial_beliefs),
            "resources": dict(actor.resources),
            "role_charter": actor.role_charter.model_dump(mode="json"),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.crisis.id,
            "title": self.crisis.title,
            "actors": [actor.id for actor in self.crisis.actors],
            "source_count": len(self.sources),
            "assertion_count": len(self.assertions),
            "horizon_days": self.crisis.checkpoint.safety_horizon_days,
            "maximum_tick": self.crisis.simulation_boundary.maximum_tick,
        }


def validate_crisis_pack(root: Path) -> list[str]:
    pack = CrisisPack.load(root)
    return [
        "Crisis Pack valid: "
        f"{len(pack.crisis.actors)} actors, {len(pack.sources)} sources, "
        f"{len(pack.assertions)} assertions, horizon {pack.crisis.checkpoint.safety_horizon_days} days"
    ]

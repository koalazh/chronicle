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
    playable_actor_ids: list[str]
    corridor: list[CorridorLocation]
    routes: list[CrisisRoute]
    anchors: list[HistoricalAnchor]


class CrisisReference(StrictModel):
    id: str
    path: str


class VolumeDefinition(StrictModel):
    id: str
    title: str
    subtitle: str
    native_period: str
    description: str
    crises: list[CrisisReference]


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
        if len(actor_ids) != len(set(actor_ids)):
            errors.append("actors: ids must be unique")
        if not 2 <= len(actor_ids) <= 5:
            errors.append("actors: a crisis requires between 2 and 5 decision actors")
        playable_actor_ids = self.crisis.playable_actor_ids
        if len(playable_actor_ids) != len(set(playable_actor_ids)):
            errors.append("playable_actor_ids: ids must be unique")
        unknown_playable = set(playable_actor_ids) - set(actor_ids)
        if unknown_playable:
            errors.append(
                "playable_actor_ids: unknown actors " + ", ".join(sorted(unknown_playable))
            )

        source_ids = {source.id for source in self.sources}
        assertion_ids = [assertion.id for assertion in self.assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            errors.append("assertions: ids must be unique")
        known_assertions = set(assertion_ids)
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
            if message.sender not in actor_ids or message.recipient not in actor_ids:
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
            unknown_actors = set(anchor.actor_ids) - set(actor_ids)
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
            "playable_actor_ids": list(self.crisis.playable_actor_ids),
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


@dataclass(frozen=True)
class VolumeRegistry:
    root: Path
    volume: VolumeDefinition
    packs: dict[str, CrisisPack]

    @classmethod
    def load(cls, root: Path) -> "VolumeRegistry":
        root = root.resolve()
        volume = VolumeDefinition.model_validate(_read_yaml(root / "volume.yaml"))
        errors: list[str] = []
        crisis_ids = [reference.id for reference in volume.crises]
        if not crisis_ids:
            errors.append("volume: at least one crisis is required")
        if len(crisis_ids) != len(set(crisis_ids)):
            errors.append("volume: crisis ids must be unique")
        packs: dict[str, CrisisPack] = {}
        for reference in volume.crises:
            candidate = (root / reference.path).resolve()
            if root not in candidate.parents:
                errors.append(f"volume: crisis {reference.id} path escapes the volume")
                continue
            try:
                pack = CrisisPack.load(candidate)
            except (FileNotFoundError, CrisisValidationError) as exc:
                errors.append(f"volume: crisis {reference.id} is invalid: {exc}")
                continue
            if pack.crisis.id != reference.id:
                errors.append(
                    f"volume: crisis reference {reference.id} does not match pack {pack.crisis.id}"
                )
                continue
            packs[reference.id] = pack
        if errors:
            raise CrisisValidationError(errors)
        return cls(root=root, volume=volume, packs=packs)

    @property
    def default_pack(self) -> CrisisPack:
        return self.packs[self.volume.crises[0].id]

    def pack(self, crisis_id: str) -> CrisisPack:
        try:
            return self.packs[crisis_id]
        except KeyError as exc:
            raise CrisisValidationError([f"volume: unknown crisis {crisis_id}"]) from exc

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.volume.id,
            "title": self.volume.title,
            "subtitle": self.volume.subtitle,
            "native_period": self.volume.native_period,
            "description": self.volume.description,
            "crises": [self.packs[reference.id].summary() for reference in self.volume.crises],
        }


def validate_volume(root: Path) -> list[str]:
    registry = VolumeRegistry.load(root)
    return [
        "Volume valid: "
        f"{registry.volume.id}, {len(registry.packs)} crisis"
        f"{'es' if len(registry.packs) != 1 else ''}"
    ]

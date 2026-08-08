from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import (
    ActorDefinition,
    Assertion,
    CanonEvent,
    ForkDefinition,
    HistoricalSource,
    Location,
    Route,
    ScenarioManifest,
)


class ScenarioValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ScenarioValidationError([f"{path}: root must be a mapping"])
    return data


@dataclass(frozen=True)
class ScenarioPack:
    root: Path
    manifest: ScenarioManifest
    actors: tuple[ActorDefinition, ...]
    locations: tuple[Location, ...]
    routes: tuple[Route, ...]
    sources: tuple[HistoricalSource, ...]
    assertions: tuple[Assertion, ...]
    events: tuple[CanonEvent, ...]
    fork: ForkDefinition

    @classmethod
    def load(cls, root: Path) -> "ScenarioPack":
        root = root.resolve()
        manifest = ScenarioManifest.model_validate(_read_yaml(root / "manifest.yaml"))
        actors = tuple(ActorDefinition.model_validate(item) for item in _read_yaml(root / "actors.yaml")["actors"])
        locations = tuple(Location.model_validate(item) for item in _read_yaml(root / "locations.yaml")["locations"])
        routes = tuple(Route.model_validate(item) for item in _read_yaml(root / "routes.yaml")["routes"])
        source_data = _read_yaml(root / "sources.yaml")
        sources = tuple(HistoricalSource.model_validate(item) for item in source_data["sources"])
        assertions = tuple(Assertion.model_validate(item) for item in source_data["assertions"])
        event_items: list[CanonEvent] = []
        for path in sorted((root / "events").glob("*.yaml")):
            event_items.extend(CanonEvent.model_validate(item) for item in _read_yaml(path)["events"])
        fork = ForkDefinition.model_validate(_read_yaml(root / "fork.yaml"))
        pack = cls(root, manifest, actors, locations, routes, sources, assertions, tuple(event_items), fork)
        pack.validate()
        return pack

    @property
    def actor_by_seat(self) -> dict[str, ActorDefinition]:
        return {actor.seat: actor for actor in self.actors}

    @property
    def location_by_id(self) -> dict[str, Location]:
        return {location.id: location for location in self.locations}

    @property
    def assertion_by_id(self) -> dict[str, Assertion]:
        return {assertion.id: assertion for assertion in self.assertions}

    @property
    def event_by_id(self) -> dict[str, CanonEvent]:
        return {event.id: event for event in self.events}

    def event_at_or_before(self, tick: int) -> list[CanonEvent]:
        return [event for event in self.events if event.tick <= tick]

    def event_by_tick(self, tick: int) -> CanonEvent | None:
        events = [event for event in self.events if event.tick == tick]
        return events[-1] if events else None

    def observations_for(self, seat: str, tick: int) -> list[tuple[CanonEvent, Any]]:
        delivered: list[tuple[CanonEvent, Any]] = []
        for event in self.events:
            for observation in event.observations.get(seat, []):
                if observation.delivery_tick <= tick:
                    delivered.append((event, observation))
        return sorted(delivered, key=lambda pair: (pair[1].delivery_tick, pair[0].tick, pair[1].id))

    def who_knows(self, assertion_id: str, tick: int) -> dict[str, bool]:
        return {
            seat: any(
                observation.origin_assertion_id == assertion_id
                for _, observation in self.observations_for(seat, tick)
            )
            for seat in self.actor_by_seat
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        errors.extend(_unique_ids("actor", [actor.seat for actor in self.actors]))
        errors.extend(_unique_ids("location", [location.id for location in self.locations]))
        errors.extend(_unique_ids("route", [route.id for route in self.routes]))
        errors.extend(_unique_ids("source", [source.id for source in self.sources]))
        errors.extend(_unique_ids("assertion", [assertion.id for assertion in self.assertions]))
        errors.extend(_unique_ids("event", [event.id for event in self.events]))
        actor_seats = set(self.actor_by_seat)
        location_ids = set(self.location_by_id)
        source_ids = {source.id for source in self.sources}
        assertion_ids = set(self.assertion_by_id)
        event_ids = set(self.event_by_id)

        if len(self.actors) != 3 or actor_seats != {"A", "B", "C"}:
            errors.append("actors: exactly Seats A, B and C are required")
        for actor in self.actors:
            if actor.initial_location not in location_ids:
                errors.append(f"actor {actor.seat}: unknown initial location {actor.initial_location}")

        for route in self.routes:
            if route.from_location not in location_ids or route.to_location not in location_ids:
                errors.append(f"route {route.id}: endpoint is not a known location")
            if route.travel_days <= 0:
                errors.append(f"route {route.id}: travel_days must be positive")

        for assertion in self.assertions:
            if assertion.provenance.value == "historical" and not assertion.source_ids:
                errors.append(f"assertion {assertion.id}: historical assertion needs a source")
            for source_id in assertion.source_ids:
                if source_id not in source_ids:
                    errors.append(f"assertion {assertion.id}: unknown source {source_id}")
            if not assertion.normalized_evidence:
                errors.append(f"assertion {assertion.id}: normalized_evidence is required")

        seen_ticks: list[int] = []
        referenced_assertions: set[str] = set()
        forbidden = self.forbidden_runtime_terms()
        for event in self.events:
            seen_ticks.append(event.tick)
            if not self.manifest.start_tick <= event.tick <= self.manifest.end_tick:
                errors.append(f"event {event.id}: tick outside scenario window")
            for assertion_id in event.assertion_ids:
                referenced_assertions.add(assertion_id)
                if assertion_id not in assertion_ids:
                    errors.append(f"event {event.id}: unknown assertion {assertion_id}")
            for seat, observations in event.observations.items():
                if seat not in actor_seats:
                    errors.append(f"event {event.id}: unknown observation Seat {seat}")
                for observation in observations:
                    if observation.origin_assertion_id not in assertion_ids:
                        errors.append(f"observation {observation.id}: unknown origin assertion")
                    if observation.delivery_tick < event.tick:
                        errors.append(f"observation {observation.id}: delivered before event occurred")
                    lower = observation.runtime_payload.casefold()
                    for term in forbidden:
                        if term.casefold() in lower:
                            errors.append(f"observation {observation.id}: forbidden runtime term {term}")
        if seen_ticks != sorted(seen_ticks):
            errors.append("events: ticks must be in non-decreasing order")
        orphaned = assertion_ids - referenced_assertions
        if orphaned:
            errors.append(f"assertions: orphaned assertions: {', '.join(sorted(orphaned))}")
        if self.fork.event_id not in event_ids:
            errors.append(f"fork: unknown event {self.fork.event_id}")
        for assertion_id in self.fork.source_assertion_ids:
            if assertion_id not in assertion_ids:
                errors.append(f"fork: unknown source assertion {assertion_id}")
        if self.fork.max_days != 14:
            errors.append("fork: V1 max_days must be 14")
        if errors:
            raise ScenarioValidationError(errors)
        return errors

    def forbidden_runtime_terms(self) -> set[str]:
        names = {actor.display_name for actor in self.actors}
        names.update(location.display_name for location in self.locations)
        names.update({"1644", "崇祯十七年", "北京陷落", "煤山"})
        return {name for name in names if name}

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.manifest.id,
            "title": self.manifest.title,
            "window": {"start": self.manifest.window_start, "end": self.manifest.window_end},
            "event_count": len(self.events),
            "assertion_count": len(self.assertions),
            "source_count": len(self.sources),
            "seats": [actor.seat for actor in self.actors],
            "fork": self.fork.model_dump(mode="json"),
        }


def _unique_ids(kind: str, values: list[str]) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for value in values:
        if value in seen:
            errors.append(f"{kind}: duplicate id {value}")
        seen.add(value)
    return errors


def validate_source_pack(root: Path) -> list[str]:
    pack = ScenarioPack.load(root)
    return [
        f"Source Pack valid: {len(pack.sources)} sources, {len(pack.assertions)} assertions, {len(pack.events)} events"
    ]


def validate_scenario(root: Path) -> list[str]:
    pack = ScenarioPack.load(root)
    return [
        f"Scenario valid: {len(pack.actors)} Seats, {len(pack.locations)} locations, {len(pack.routes)} routes, fork={pack.fork.id}"
    ]

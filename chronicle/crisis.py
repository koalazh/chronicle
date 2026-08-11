from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from .models import Assertion, HistoricalSource, Provenance, StrictModel


class CrisisValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class HistoricalPolicy(StrEnum):
    EXOGENOUS = "EXOGENOUS"
    CONDITIONAL_ANCHOR = "CONDITIONAL_ANCHOR"
    REFERENCE_ONLY = "REFERENCE_ONLY"


class HistoricalCompatibilityPreconditionKind(StrEnum):
    ENTITY_STATE = "ENTITY_STATE"
    ACTOR_POSITION = "ACTOR_POSITION"
    UNMODELED = "UNMODELED"


class CrisisSurfaceKind(StrEnum):
    SPATIAL = "SPATIAL"
    POLITICAL = "POLITICAL"


class CrisisEntityType(StrEnum):
    PERSON = "PERSON"
    CLAIMANT = "CLAIMANT"
    INSTITUTION = "INSTITUTION"
    FORCE = "FORCE"
    PLACE = "PLACE"
    ASSET = "ASSET"
    DOCUMENT = "DOCUMENT"


class OperationDurationKind(StrEnum):
    FIXED = "FIXED"
    ROUTE = "ROUTE"


class OperationKind(StrEnum):
    STATE_CHANGE = "STATE_CHANGE"
    MOVEMENT = "MOVEMENT"


class OperationVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class ObservationReliability(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PressureKind(StrEnum):
    EXOGENOUS = "EXOGENOUS"
    CONDITIONAL = "CONDITIONAL"


class PressureStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"


class AgreementTermType(StrEnum):
    PASSAGE = "passage"


class OfferAction(StrEnum):
    PROPOSE = "PROPOSE"
    COUNTER = "COUNTER"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    WITHDRAW = "WITHDRAW"


class OfferStatus(StrEnum):
    PROPOSED = "PROPOSED"
    COUNTERED = "COUNTERED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class AgreementStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    BREACHED = "BREACHED"
    TERMINATED = "TERMINATED"
    EXPIRED = "EXPIRED"


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
    asset_ids: list[str] = Field(default_factory=list)


class CrisisEntity(StrictModel):
    id: str
    type: CrisisEntityType
    display_name: str
    initial_state: str
    assertion_ids: list[str] = Field(default_factory=list)


class OperationTarget(StrictModel):
    id: str
    entity_types: list[CrisisEntityType]
    owned_by_actor: bool = False
    allowed_entity_ids: list[str] = Field(default_factory=list)


class OperationStateCondition(StrictModel):
    subject: str
    states: list[str]


class OperationStateEffect(StrictModel):
    subject: str
    state: str


class AgreementTerm(StrictModel):
    type: AgreementTermType
    subject: str
    value: str
    description: str


class CrisisOfferTermDefinition(AgreementTerm):
    party_ids: list[str]


class AgreementTermRequirement(StrictModel):
    type: AgreementTermType
    subject: str
    value: str
    party_ids: list[str]


class CrisisOperationDefinition(StrictModel):
    id: str
    display_name: str
    description: str
    actor_ids: list[str]
    targets: list[OperationTarget] = Field(default_factory=list)
    kind: OperationKind = OperationKind.STATE_CHANGE
    duration_kind: OperationDurationKind = OperationDurationKind.FIXED
    duration_days: int | None = Field(default=None, ge=1)
    movement_destination_target: str = ""
    required_assets: list[str] = Field(default_factory=list)
    preconditions: list[OperationStateCondition] = Field(default_factory=list)
    start_effects: list[OperationStateEffect] = Field(default_factory=list)
    completion_effects: list[OperationStateEffect] = Field(default_factory=list)
    agreement_requirements: list[AgreementTermRequirement] = Field(default_factory=list)
    agreement_fulfillments: list[AgreementTermRequirement] = Field(default_factory=list)
    agreement_breaches: list[AgreementTermRequirement] = Field(default_factory=list)
    visibility: OperationVisibility = OperationVisibility.PRIVATE
    interruptibility: bool = False
    conflicts: list[str] = Field(default_factory=list)


class InvestigationObservationDefinition(StrictModel):
    content: str
    source: str
    source_ids: list[str]
    reliability: ObservationReliability
    related_assertion_ids: list[str]


class CrisisInvestigationDefinition(StrictModel):
    id: str
    display_name: str
    description: str
    actor_ids: list[str]
    target_ids: list[str]
    method: str
    duration_days: int = Field(ge=1)
    required_assets: list[str] = Field(default_factory=list)
    visibility: OperationVisibility = OperationVisibility.PRIVATE
    observation: InvestigationObservationDefinition


class CrisisPressureDefinition(StrictModel):
    id: str
    kind: PressureKind
    title: str
    description: str
    trigger_tick: int = Field(ge=1)
    preconditions: list[OperationStateCondition] = Field(default_factory=list)
    effects: list[OperationStateEffect]
    visibility: OperationVisibility = OperationVisibility.PUBLIC
    visible_actor_ids: list[str] = Field(default_factory=list)
    provenance: Provenance
    assertion_ids: list[str]


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
    safety_horizon_days: int = Field(ge=7, le=45)
    facts: list[str]
    unresolved: list[str]
    in_transit: list[InTransitMessage]


class HistoricalCompatibilityPrecondition(StrictModel):
    id: str
    kind: HistoricalCompatibilityPreconditionKind
    description: str
    subject: str = ""
    satisfied_values: list[str] = Field(default_factory=list)
    contradicted_values: list[str] = Field(default_factory=list)


class HistoricalAnchor(StrictModel):
    id: str
    title: str
    tick: int
    policy: HistoricalPolicy
    assertion_ids: list[str]
    actor_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    compatibility_preconditions: list[HistoricalCompatibilityPrecondition] = Field(
        default_factory=list
    )


class SimulationBoundary(StrictModel):
    stop_before: str
    reason: str
    maximum_tick: int = Field(gt=0)


class ResolutionContractReference(StrictModel):
    id: str
    version: int = Field(ge=1)


class CrisisSurfaceDefinition(StrictModel):
    kind: CrisisSurfaceKind
    title: str
    description: str = ""


class CrisisDefinition(StrictModel):
    id: str
    version: int = Field(ge=1)
    title: str
    subtitle: str
    checkpoint: CrisisCheckpoint
    simulation_boundary: SimulationBoundary
    resolution_contract: ResolutionContractReference
    surface: CrisisSurfaceDefinition
    actors: list[CrisisActorDefinition]
    playable_actor_ids: list[str]
    corridor: list[CorridorLocation]
    routes: list[CrisisRoute]
    anchors: list[HistoricalAnchor]
    entities: list[CrisisEntity] = Field(default_factory=list)
    operations: list[CrisisOperationDefinition] = Field(default_factory=list)
    investigations: list[CrisisInvestigationDefinition] = Field(default_factory=list)
    offer_terms: list[CrisisOfferTermDefinition] = Field(default_factory=list)
    pressures: list[CrisisPressureDefinition] = Field(default_factory=list)


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


@dataclass(frozen=True)
class OperationRequest:
    definition: CrisisOperationDefinition
    target_ids: tuple[str, ...]
    target_map: dict[str, str]
    expected_complete_tick: int
    input_state: dict[str, str]


@dataclass(frozen=True)
class InvestigationRequest:
    definition: CrisisInvestigationDefinition
    target_id: str
    expected_result_tick: int


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

    @property
    def entity_by_id(self) -> dict[str, CrisisEntity]:
        return {entity.id: entity for entity in self.crisis.entities}

    @property
    def operation_by_id(self) -> dict[str, CrisisOperationDefinition]:
        return {operation.id: operation for operation in self.crisis.operations}

    @property
    def investigation_by_id(self) -> dict[str, CrisisInvestigationDefinition]:
        return {
            investigation.id: investigation for investigation in self.crisis.investigations
        }

    @property
    def pressure_by_id(self) -> dict[str, CrisisPressureDefinition]:
        return {pressure.id: pressure for pressure in self.crisis.pressures}

    @staticmethod
    def _agreement_term_key(
        term: AgreementTerm | CrisisOfferTermDefinition | AgreementTermRequirement | dict[str, Any],
    ) -> tuple[str, str, str]:
        if isinstance(term, dict):
            return (
                str(term.get("type", "")),
                str(term.get("subject", "")),
                str(term.get("value", "")),
            )
        return term.type.value, term.subject, term.value

    def offer_terms_request(
        self,
        issuer_id: str,
        recipient_id: str,
        terms: list[AgreementTerm],
    ) -> tuple[list[AgreementTerm] | None, str]:
        if issuer_id not in self.actor_by_id or recipient_id not in self.actor_by_id:
            return None, "invalid_offer_recipient"
        if issuer_id == recipient_id or not terms:
            return None, "invalid_offer_terms"
        term_keys = [self._agreement_term_key(term) for term in terms]
        if len(term_keys) != len(set(term_keys)) or any(not term.description.strip() for term in terms):
            return None, "invalid_offer_terms"
        parties = {issuer_id, recipient_id}
        for term in terms:
            if not any(
                self._agreement_term_key(definition) == self._agreement_term_key(term)
                and set(definition.party_ids) == parties
                for definition in self.crisis.offer_terms
            ):
                return None, "offer_term_unavailable"
        return terms, ""

    def offer_term_affordances(self, actor_id: str) -> list[dict[str, Any]]:
        entities = self.entity_by_id
        actors = self.actor_by_id
        affordances: list[dict[str, Any]] = []
        for definition in self.crisis.offer_terms:
            if actor_id not in definition.party_ids:
                continue
            recipient_id = next(
                (party_id for party_id in definition.party_ids if party_id != actor_id),
                "",
            )
            target = entities.get(definition.subject)
            recipient = actors.get(recipient_id)
            if target is None or recipient is None:
                continue
            affordances.append(
                {
                    "type": definition.type.value,
                    "subject": {
                        "id": target.id,
                        "type": target.type.value,
                        "display_name": target.display_name,
                    },
                    "value": definition.value,
                    "description": definition.description,
                    "recipient": {
                        "id": recipient.id,
                        "display_name": recipient.display_name,
                    },
                }
            )
        return affordances

    def active_agreement_ids(
        self,
        projection: dict[str, Any],
        requirement: AgreementTermRequirement,
    ) -> list[str]:
        return [
            str(agreement["id"])
            for agreement in projection.get("agreements", [])
            if agreement.get("status") == AgreementStatus.ACTIVE.value
            and set(agreement.get("parties", [])) == set(requirement.party_ids)
            and any(
                self._agreement_term_key(term) == self._agreement_term_key(requirement)
                for term in agreement.get("terms", [])
            )
        ]

    def route_days(self, start: str, end: str) -> int | None:
        queue: list[tuple[int, str]] = [(0, start)]
        best: dict[str, int] = {start: 0}
        edges: dict[str, list[tuple[str, int]]] = {}
        for route in self.crisis.routes:
            edges.setdefault(route.from_location, []).append((route.to_location, route.travel_days))
        while queue:
            distance, location = heapq.heappop(queue)
            if location == end:
                return distance
            if distance != best.get(location):
                continue
            for target, days in edges.get(location, []):
                candidate = distance + days
                if candidate < best.get(target, 10**9):
                    best[target] = candidate
                    heapq.heappush(queue, (candidate, target))
        return None

    @staticmethod
    def _operation_subject_entity_id(subject: str, target_map: dict[str, str]) -> str:
        return target_map.get(subject, subject)

    @staticmethod
    def _entity_state(projection: dict[str, Any], entity_id: str) -> str:
        entity = projection.get("entities", {}).get(entity_id, {})
        return str(entity.get("state", "")) if isinstance(entity, dict) else ""

    def operation_request(
        self,
        actor_id: str,
        definition_id: str,
        target_ids: list[str],
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[OperationRequest | None, str]:
        actor = self.actor_by_id.get(actor_id)
        definition = self.operation_by_id.get(definition_id)
        if actor is None or definition is None:
            return None, "unknown_operation"
        if actor_id not in definition.actor_ids:
            return None, "operation_authority_denied"
        if len(target_ids) != len(definition.targets) or any(
            not isinstance(target_id, str) or not target_id for target_id in target_ids
        ):
            return None, "invalid_operation_targets"
        if len(target_ids) != len(set(target_ids)):
            return None, "invalid_operation_targets"
        target_map = {
            target.id: target_id for target, target_id in zip(definition.targets, target_ids, strict=True)
        }
        entities = self.entity_by_id
        for target, target_id in zip(definition.targets, target_ids, strict=True):
            entity = entities.get(target_id)
            if entity is None or entity.type not in target.entity_types:
                return None, "invalid_operation_targets"
            if target.allowed_entity_ids and target_id not in target.allowed_entity_ids:
                return None, "invalid_operation_targets"
            if target.owned_by_actor and target_id not in actor.asset_ids:
                return None, "operation_target_not_owned"
        for subject in definition.required_assets:
            entity_id = self._operation_subject_entity_id(subject, target_map)
            if entity_id not in actor.asset_ids:
                return None, "required_asset_unavailable"
        for condition in definition.preconditions:
            entity_id = self._operation_subject_entity_id(condition.subject, target_map)
            if self._entity_state(projection, entity_id) not in condition.states:
                return None, "operation_precondition_unmet"
        if any(
            not self.active_agreement_ids(projection, requirement)
            for requirement in definition.agreement_requirements
        ):
            return None, "agreement_precondition_unmet"
        for active in projection.get("operations", []):
            if active.get("status") not in {"PLANNED", "IN_PROGRESS"}:
                continue
            active_definition = self.operation_by_id.get(str(active.get("definition_id", "")))
            if active_definition is None:
                continue
            if not set(target_ids).intersection(active.get("target_ids", [])):
                continue
            if (
                active_definition.id in definition.conflicts
                or definition.id in active_definition.conflicts
            ):
                return None, "operation_conflict"
        if definition.duration_kind == OperationDurationKind.FIXED:
            expected_complete_tick = tick + int(definition.duration_days or 0)
        else:
            destination_id = target_map.get(definition.movement_destination_target, "")
            travel_days = self.route_days(
                str(projection.get("positions", {}).get(actor_id, "")), destination_id
            )
            if travel_days is None or travel_days <= 0:
                return None, "no_route"
            expected_complete_tick = tick + travel_days
        if expected_complete_tick >= self.crisis.simulation_boundary.maximum_tick:
            return None, "crosses_simulation_boundary"
        input_state = {
            entity_id: self._entity_state(projection, entity_id)
            for entity_id in target_ids
        }
        return (
            OperationRequest(
                definition=definition,
                target_ids=tuple(target_ids),
                target_map=target_map,
                expected_complete_tick=expected_complete_tick,
                input_state=input_state,
            ),
            "",
        )

    def operation_affordances(
        self,
        actor_id: str,
        projection: dict[str, Any],
        tick: int,
    ) -> list[dict[str, Any]]:
        actor = self.actor_by_id[actor_id]
        entities = self.entity_by_id
        affordances: list[dict[str, Any]] = []
        for definition in self.crisis.operations:
            if actor_id not in definition.actor_ids:
                continue
            options_by_target: list[list[str]] = []
            for target in definition.targets:
                options = [
                    entity.id
                    for entity in sorted(entities.values(), key=lambda item: item.id)
                    if entity.type in target.entity_types
                    and (
                        not target.allowed_entity_ids
                        or entity.id in target.allowed_entity_ids
                    )
                    and (not target.owned_by_actor or entity.id in actor.asset_ids)
                ]
                options_by_target.append(options)
            valid_target_ids = [
                tuple(candidate)
                for candidate in product(*options_by_target)
                if self.operation_request(
                    actor_id, definition.id, list(candidate), projection, tick
                )[0]
                is not None
            ]
            if not valid_target_ids:
                continue
            affordances.append(
                {
                    "id": definition.id,
                    "display_name": definition.display_name,
                    "description": definition.description,
                    "kind": definition.kind.value,
                    "duration_kind": definition.duration_kind.value,
                    "duration_days": definition.duration_days,
                    "targets": [
                        {
                            "id": target.id,
                            "options": [
                                {
                                    "id": entity_id,
                                    "display_name": entities[entity_id].display_name,
                                    "state": self._entity_state(projection, entity_id),
                                }
                                for entity_id in sorted(
                                    {candidate[index] for candidate in valid_target_ids}
                                )
                            ],
                        }
                        for index, target in enumerate(definition.targets)
                    ],
                }
            )
        return affordances

    def investigation_request(
        self,
        actor_id: str,
        target_id: str,
        method: str,
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[InvestigationRequest | None, str]:
        actor = self.actor_by_id.get(actor_id)
        if actor is None:
            return None, "investigation_unavailable"
        if target_id not in self.entity_by_id:
            return None, "unknown_investigation_target"
        candidates = [
            definition
            for definition in self.crisis.investigations
            if actor_id in definition.actor_ids and target_id in definition.target_ids
        ]
        if not candidates:
            return None, "investigation_unavailable"
        if method:
            candidates = [definition for definition in candidates if definition.method == method]
            if not candidates:
                return None, "unsupported_investigation_method"
        elif len(candidates) > 1:
            return None, "investigation_method_required"
        if len(candidates) != 1:
            return None, "investigation_unavailable"
        definition = candidates[0]
        if any(asset_id not in actor.asset_ids for asset_id in definition.required_assets):
            return None, "investigation_asset_unavailable"
        if any(
            active.get("status") in {"PLANNED", "IN_PROGRESS"}
            and active.get("actor_id") == actor_id
            and active.get("definition_id") == definition.id
            and active.get("target_id") == target_id
            for active in projection.get("investigations", [])
        ):
            return None, "investigation_already_active"
        expected_result_tick = tick + definition.duration_days
        if expected_result_tick >= self.crisis.simulation_boundary.maximum_tick:
            return None, "crosses_simulation_boundary"
        return (
            InvestigationRequest(
                definition=definition,
                target_id=target_id,
                expected_result_tick=expected_result_tick,
            ),
            "",
        )

    def investigation_affordances(
        self,
        actor_id: str,
        projection: dict[str, Any],
        tick: int,
    ) -> list[dict[str, Any]]:
        entities = self.entity_by_id
        affordances: list[dict[str, Any]] = []
        for definition in self.crisis.investigations:
            if actor_id not in definition.actor_ids:
                continue
            for target_id in definition.target_ids:
                request, _ = self.investigation_request(
                    actor_id,
                    target_id,
                    definition.method,
                    projection,
                    tick,
                )
                if request is None:
                    continue
                target = entities[target_id]
                affordances.append(
                    {
                        "id": definition.id,
                        "display_name": definition.display_name,
                        "description": definition.description,
                        "target": {
                            "id": target.id,
                            "type": target.type.value,
                            "display_name": target.display_name,
                        },
                        "method": definition.method,
                        "duration_days": definition.duration_days,
                        "expected_result_tick": request.expected_result_tick,
                    }
                )
        return affordances

    @property
    def content_hash(self) -> str:
        payload = {
            "crisis": self.crisis.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in self.sources],
            "assertions": [assertion.model_dump(mode="json") for assertion in self.assertions],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def surface_projection(
        self,
        projection: dict[str, Any],
        *,
        visible_actor_ids: set[str] | None = None,
        include_messages: bool = False,
    ) -> dict[str, Any]:
        surface = self.crisis.surface
        if surface.kind != CrisisSurfaceKind.SPATIAL:
            raise CrisisValidationError([f"unsupported surface kind {surface.kind}"])
        movements = {
            movement["actor_id"]
            for movement in projection.get("movements", [])
            if movement.get("status") == "in_transit"
        }
        actor_ids = visible_actor_ids if visible_actor_ids is not None else set(self.actor_by_id)
        return {
            "kind": surface.kind.value,
            "title": surface.title,
            "description": surface.description,
            "locations": [
                location.model_dump(mode="json")
                for location in sorted(self.crisis.corridor, key=lambda item: item.order)
            ],
            "actors": [
                {
                    "id": actor.id,
                    "display_name": actor.display_name,
                    "location": projection.get("positions", {}).get(actor.id, ""),
                    "in_transit": actor.id in movements,
                }
                for actor in self.crisis.actors
                if actor.id in actor_ids
            ],
            "messages": list(projection.get("messages", [])) if include_messages else [],
        }

    def validate(self) -> None:
        errors: list[str] = []
        from .resolution import resolution_contract_registered

        contract = self.crisis.resolution_contract
        if not resolution_contract_registered(contract.id, contract.version):
            errors.append(
                f"resolution contract {contract.id}/v{contract.version} is not registered"
            )
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

        entity_ids = [entity.id for entity in self.crisis.entities]
        if len(entity_ids) != len(set(entity_ids)):
            errors.append("entities: ids must be unique")
        known_entities = set(entity_ids)
        for entity in self.crisis.entities:
            if not entity.initial_state:
                errors.append(f"entity {entity.id}: initial state is required")
            for assertion_id in entity.assertion_ids:
                if assertion_id not in known_assertions:
                    errors.append(f"entity {entity.id}: unknown assertion {assertion_id}")

        location_ids = [location.id for location in self.crisis.corridor]
        if len(location_ids) != len(set(location_ids)):
            errors.append("corridor: location ids must be unique")
        if self.crisis.surface.kind == CrisisSurfaceKind.SPATIAL and not location_ids:
            errors.append("surface: SPATIAL requires locations")
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
            unknown_assets = set(actor.asset_ids) - known_entities
            if unknown_assets:
                errors.append(
                    f"actor {actor.id}: unknown assets {', '.join(sorted(unknown_assets))}"
                )

        offer_term_keys: set[tuple[str, str, str, tuple[str, ...]]] = set()
        for term in self.crisis.offer_terms:
            if len(term.party_ids) != 2 or len(term.party_ids) != len(set(term.party_ids)):
                errors.append("offer term: party ids must name exactly two unique actors")
            unknown_parties = set(term.party_ids) - set(actor_ids)
            if unknown_parties:
                errors.append(
                    "offer term "
                    f"{term.type.value}/{term.subject}: unknown parties {', '.join(sorted(unknown_parties))}"
                )
            if term.subject not in known_entities:
                errors.append(f"offer term {term.type.value}: unknown subject {term.subject}")
            if not term.value or not term.description:
                errors.append(f"offer term {term.type.value}/{term.subject}: value and description are required")
            key = (*self._agreement_term_key(term), tuple(sorted(term.party_ids)))
            if key in offer_term_keys:
                errors.append("offer terms: type/subject/value/parties must be unique")
            offer_term_keys.add(key)
        for route in self.crisis.routes:
            if route.from_location not in known_locations or route.to_location not in known_locations:
                errors.append(f"route {route.id}: endpoint is not on the corridor")

        operation_ids = [operation.id for operation in self.crisis.operations]
        if len(operation_ids) != len(set(operation_ids)):
            errors.append("operations: ids must be unique")
        known_operations = set(operation_ids)
        for operation in self.crisis.operations:
            unknown_actors = set(operation.actor_ids) - set(actor_ids)
            if unknown_actors:
                errors.append(
                    f"operation {operation.id}: unknown actors {', '.join(sorted(unknown_actors))}"
                )
            target_ids = [target.id for target in operation.targets]
            if len(target_ids) != len(set(target_ids)) or any(not target_id for target_id in target_ids):
                errors.append(f"operation {operation.id}: target ids must be unique and nonempty")
            if any(not target.entity_types for target in operation.targets):
                errors.append(f"operation {operation.id}: target types are required")
            for target in operation.targets:
                if len(target.allowed_entity_ids) != len(set(target.allowed_entity_ids)):
                    errors.append(
                        f"operation {operation.id}: allowed target ids must be unique"
                    )
                unknown_allowed = set(target.allowed_entity_ids) - known_entities
                if unknown_allowed:
                    errors.append(
                        "operation "
                        f"{operation.id}: unknown allowed targets {', '.join(sorted(unknown_allowed))}"
                    )
            if operation.duration_kind == OperationDurationKind.FIXED and operation.duration_days is None:
                errors.append(f"operation {operation.id}: fixed duration requires duration_days")
            if operation.duration_kind == OperationDurationKind.ROUTE and operation.duration_days is not None:
                errors.append(f"operation {operation.id}: route duration cannot set duration_days")
            if operation.kind == OperationKind.MOVEMENT:
                destination = next(
                    (target for target in operation.targets if target.id == operation.movement_destination_target),
                    None,
                )
                if destination is None or CrisisEntityType.PLACE not in destination.entity_types:
                    errors.append(
                        f"operation {operation.id}: movement destination must be a PLACE target"
                    )
            elif operation.movement_destination_target:
                errors.append(f"operation {operation.id}: only MOVEMENT may set a destination target")
            for subject in operation.required_assets:
                if subject not in target_ids and subject not in known_entities:
                    errors.append(f"operation {operation.id}: unknown required asset {subject}")
            for condition in operation.preconditions:
                if condition.subject not in target_ids and condition.subject not in known_entities:
                    errors.append(f"operation {operation.id}: unknown precondition subject {condition.subject}")
                if not condition.states:
                    errors.append(f"operation {operation.id}: precondition states are required")
            for effect in [*operation.start_effects, *operation.completion_effects]:
                if effect.subject not in target_ids and effect.subject not in known_entities:
                    errors.append(f"operation {operation.id}: unknown effect subject {effect.subject}")
                if not effect.state:
                    errors.append(f"operation {operation.id}: effect state is required")
            unknown_conflicts = set(operation.conflicts) - known_operations
            if unknown_conflicts:
                errors.append(
                    f"operation {operation.id}: unknown conflicts {', '.join(sorted(unknown_conflicts))}"
                )
            for label, requirements in (
                ("agreement requirement", operation.agreement_requirements),
                ("agreement fulfillment", operation.agreement_fulfillments),
                ("agreement breach", operation.agreement_breaches),
            ):
                for requirement in requirements:
                    key = (*self._agreement_term_key(requirement), tuple(sorted(requirement.party_ids)))
                    if key not in offer_term_keys:
                        errors.append(
                            f"operation {operation.id}: unknown {label} "
                            f"{requirement.type.value}/{requirement.subject}"
                        )
                    if not set(operation.actor_ids).issubset(requirement.party_ids):
                        errors.append(
                            f"operation {operation.id}: {label} parties must include operation actors"
                        )

        investigation_ids = [investigation.id for investigation in self.crisis.investigations]
        if len(investigation_ids) != len(set(investigation_ids)):
            errors.append("investigations: ids must be unique")
        seen_investigation_capabilities: set[tuple[str, str, str]] = set()
        actors_by_id = self.actor_by_id
        for investigation in self.crisis.investigations:
            if not investigation.actor_ids or len(investigation.actor_ids) != len(
                set(investigation.actor_ids)
            ):
                errors.append(f"investigation {investigation.id}: actor ids must be unique and nonempty")
            unknown_actors = set(investigation.actor_ids) - set(actor_ids)
            if unknown_actors:
                errors.append(
                    "investigation "
                    f"{investigation.id}: unknown actors {', '.join(sorted(unknown_actors))}"
                )
            if not investigation.method:
                errors.append(f"investigation {investigation.id}: method is required")
            if not investigation.target_ids or len(investigation.target_ids) != len(
                set(investigation.target_ids)
            ):
                errors.append(f"investigation {investigation.id}: target ids must be unique and nonempty")
            unknown_targets = set(investigation.target_ids) - known_entities
            if unknown_targets:
                errors.append(
                    "investigation "
                    f"{investigation.id}: unknown targets {', '.join(sorted(unknown_targets))}"
                )
            for actor_id in investigation.actor_ids:
                actor = actors_by_id.get(actor_id)
                if actor is None:
                    continue
                missing_assets = set(investigation.required_assets) - set(
                    actor.asset_ids
                )
                if missing_assets:
                    errors.append(
                        "investigation "
                        f"{investigation.id}: {actor_id} lacks assets {', '.join(sorted(missing_assets))}"
                    )
            observation = investigation.observation
            if not observation.content or not observation.source:
                errors.append(f"investigation {investigation.id}: observation content and source are required")
            unknown_sources = set(observation.source_ids) - source_ids
            if not observation.source_ids or unknown_sources:
                errors.append(
                    "investigation "
                    f"{investigation.id}: unknown observation sources {', '.join(sorted(unknown_sources))}"
                )
            unknown_assertions = set(observation.related_assertion_ids) - known_assertions
            if not observation.related_assertion_ids or unknown_assertions:
                errors.append(
                    "investigation "
                    f"{investigation.id}: unknown related assertions {', '.join(sorted(unknown_assertions))}"
                )
            for actor_id in investigation.actor_ids:
                for target_id in investigation.target_ids:
                    capability = (actor_id, target_id, investigation.method)
                    if capability in seen_investigation_capabilities:
                        errors.append(
                            "investigations: actor/target/method capabilities must be unambiguous"
                        )
                    seen_investigation_capabilities.add(capability)

        pressure_ids = [pressure.id for pressure in self.crisis.pressures]
        if len(pressure_ids) != len(set(pressure_ids)):
            errors.append("pressures: ids must be unique")
        for pressure in self.crisis.pressures:
            if not pressure.title or not pressure.description:
                errors.append(f"pressure {pressure.id}: title and description are required")
            if pressure.trigger_tick >= self.crisis.simulation_boundary.maximum_tick:
                errors.append(f"pressure {pressure.id}: trigger must precede the simulation boundary")
            if pressure.kind == PressureKind.EXOGENOUS and pressure.preconditions:
                errors.append(f"pressure {pressure.id}: EXOGENOUS pressure cannot have preconditions")
            if pressure.kind == PressureKind.CONDITIONAL and not pressure.preconditions:
                errors.append(f"pressure {pressure.id}: CONDITIONAL pressure requires preconditions")
            if not pressure.effects:
                errors.append(f"pressure {pressure.id}: effects are required")
            if pressure.provenance == Provenance.BRANCH_DERIVED:
                errors.append(f"pressure {pressure.id}: provenance cannot be branch_derived")
            unknown_assertions = set(pressure.assertion_ids) - known_assertions
            if not pressure.assertion_ids or unknown_assertions:
                errors.append(
                    f"pressure {pressure.id}: unknown assertions "
                    + ", ".join(sorted(unknown_assertions))
                )
            if len(pressure.visible_actor_ids) != len(set(pressure.visible_actor_ids)):
                errors.append(f"pressure {pressure.id}: visible actor ids must be unique")
            unknown_visible = set(pressure.visible_actor_ids) - set(actor_ids)
            if unknown_visible:
                errors.append(
                    f"pressure {pressure.id}: unknown visible actors "
                    + ", ".join(sorted(unknown_visible))
                )
            if pressure.visibility == OperationVisibility.PUBLIC and pressure.visible_actor_ids:
                errors.append(f"pressure {pressure.id}: PUBLIC pressure cannot name visible actors")
            if pressure.visibility == OperationVisibility.PRIVATE and not pressure.visible_actor_ids:
                errors.append(f"pressure {pressure.id}: PRIVATE pressure requires visible actors")
            for condition in pressure.preconditions:
                if condition.subject not in known_entities:
                    errors.append(
                        f"pressure {pressure.id}: unknown precondition subject {condition.subject}"
                    )
                if not condition.states:
                    errors.append(f"pressure {pressure.id}: precondition states are required")
            for effect in pressure.effects:
                if effect.subject not in known_entities:
                    errors.append(f"pressure {pressure.id}: unknown effect subject {effect.subject}")
                if not effect.state:
                    errors.append(f"pressure {pressure.id}: effect state is required")

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
            precondition_ids = [item.id for item in anchor.compatibility_preconditions]
            if len(precondition_ids) != len(set(precondition_ids)):
                errors.append(f"anchor {anchor.id}: compatibility precondition ids must be unique")
            if anchor.compatibility_preconditions and anchor.policy != HistoricalPolicy.REFERENCE_ONLY:
                errors.append(
                    f"anchor {anchor.id}: compatibility contracts require REFERENCE_ONLY policy"
                )
            for precondition in anchor.compatibility_preconditions:
                if not precondition.description:
                    errors.append(
                        f"anchor {anchor.id}: compatibility precondition {precondition.id} needs a description"
                    )
                if precondition.kind == HistoricalCompatibilityPreconditionKind.ENTITY_STATE:
                    if precondition.subject not in known_entities:
                        errors.append(
                            f"anchor {anchor.id}: compatibility precondition {precondition.id} "
                            f"references unknown entity {precondition.subject}"
                        )
                elif precondition.kind == HistoricalCompatibilityPreconditionKind.ACTOR_POSITION:
                    if precondition.subject not in actor_ids:
                        errors.append(
                            f"anchor {anchor.id}: compatibility precondition {precondition.id} "
                            f"references unknown actor {precondition.subject}"
                        )
                    unknown_locations = (
                        set(precondition.satisfied_values)
                        | set(precondition.contradicted_values)
                    ) - known_locations
                    if unknown_locations:
                        errors.append(
                            f"anchor {anchor.id}: compatibility precondition {precondition.id} "
                            "references unknown locations "
                            + ", ".join(sorted(unknown_locations))
                        )
                elif precondition.kind == HistoricalCompatibilityPreconditionKind.UNMODELED:
                    if (
                        precondition.subject
                        or precondition.satisfied_values
                        or precondition.contradicted_values
                    ):
                        errors.append(
                            f"anchor {anchor.id}: unmodeled compatibility precondition "
                            f"{precondition.id} cannot declare world values"
                        )
                if precondition.kind != HistoricalCompatibilityPreconditionKind.UNMODELED:
                    if not precondition.satisfied_values:
                        errors.append(
                            f"anchor {anchor.id}: compatibility precondition {precondition.id} "
                            "needs satisfied values"
                        )
                    if set(precondition.satisfied_values) & set(precondition.contradicted_values):
                        errors.append(
                            f"anchor {anchor.id}: compatibility precondition {precondition.id} "
                            "has overlapping satisfied and contradicted values"
                        )
        actor_reference_assertion_ids = {
            assertion_id
            for anchor in self.crisis.anchors
            if anchor.actor_ids
            for assertion_id in anchor.assertion_ids
        }
        for pressure in self.crisis.pressures:
            injected_actor_history = set(pressure.assertion_ids) & actor_reference_assertion_ids
            if injected_actor_history:
                errors.append(
                    f"pressure {pressure.id}: cannot inject Decision Actor historical anchors "
                    + ", ".join(sorted(injected_actor_history))
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
            "version": self.crisis.version,
            "content_hash": self.content_hash,
            "resolution_contract": self.crisis.resolution_contract.model_dump(mode="json"),
            "surface_kind": self.crisis.surface.kind.value,
            "title": self.crisis.title,
            "actors": [actor.id for actor in self.crisis.actors],
            "playable_actor_ids": list(self.crisis.playable_actor_ids),
            "source_count": len(self.sources),
            "assertion_count": len(self.assertions),
            "entity_count": len(self.crisis.entities),
            "operation_count": len(self.crisis.operations),
            "investigation_count": len(self.crisis.investigations),
            "offer_term_count": len(self.crisis.offer_terms),
            "pressure_count": len(self.crisis.pressures),
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

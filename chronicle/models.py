from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrEnum):
    HISTORICAL = "historical"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    MODELED = "modeled"
    BRANCH_DERIVED = "branch_derived"


class EvidenceStatus(StrEnum):
    CORROBORATED = "corroborated"
    SINGLE_ATTESTED = "single_attested"
    DISPUTED = "disputed"
    APPROXIMATE = "approximate"


class BranchPolicy(StrEnum):
    EXOGENOUS = "exogenous"
    PRECONDITIONED = "preconditioned"
    CANON_ONLY = "canon_only"


class WakeType(StrEnum):
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    BRANCH_DECISION = "branch_decision"
    LAB = "lab"


class MarkerType(StrEnum):
    WORLD = "world"
    MESSAGE = "message"
    DECISION = "decision"
    MEMORY = "memory"
    FORK = "fork"


class ActionType(StrEnum):
    ISSUE_ORDER = "ISSUE_ORDER"
    SEND_MESSAGE = "SEND_MESSAGE"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    APPOINT_AUTHORITY = "APPOINT_AUTHORITY"
    PREPARE_MOVEMENT = "PREPARE_MOVEMENT"
    MOVE_PRINCIPAL = "MOVE_PRINCIPAL"
    REDEPLOY_FORCE = "REDEPLOY_FORCE"
    HOLD_POSITION = "HOLD_POSITION"
    NEGOTIATE = "NEGOTIATE"
    SET_DISCLOSURE = "SET_DISCLOSURE"
    WAIT = "WAIT"


ACTION_CAUSAL_ENVELOPE: dict[ActionType, str] = {
    ActionType.SEND_MESSAGE: "message_propagation",
    ActionType.ISSUE_ORDER: "orders",
    ActionType.REQUEST_INFORMATION: "information_request",
    ActionType.APPOINT_AUTHORITY: "authority",
    ActionType.PREPARE_MOVEMENT: "preparation",
    ActionType.MOVE_PRINCIPAL: "known_movement",
    ActionType.REDEPLOY_FORCE: "existing_force_redeployment",
    ActionType.SET_DISCLOSURE: "disclosure",
    ActionType.HOLD_POSITION: "modeled_seat_reaction",
    ActionType.NEGOTIATE: "modeled_seat_reaction",
    ActionType.WAIT: "modeled_seat_reaction",
}


class WorldlineKind(StrEnum):
    CANON = "CANON"
    BRANCH = "BRANCH"
    VOLUME = "VOLUME"


class CrisisInstanceStatus(StrEnum):
    DORMANT = "DORMANT"
    ACTIVE = "ACTIVE"
    RESOLUTION_PENDING = "RESOLUTION_PENDING"
    AFTERMATH = "AFTERMATH"
    SETTLED = "SETTLED"
    SUPPRESSED = "SUPPRESSED"


class WorldlineStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SEALED = "SEALED"


class Controller(StrEnum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"


class ActionValidation(StrEnum):
    ACCEPTED = "ACCEPTED"
    IMPOSSIBLE = "IMPOSSIBLE"
    UNSUPPORTED = "UNSUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"


class SourceCitation(StrictModel):
    source_id: str
    locator: str
    excerpt: str = ""
    url: str = ""


class HistoricalSource(StrictModel):
    id: str
    work: str
    locator: str
    url: str
    description: str = ""


class Assertion(StrictModel):
    id: str
    claim: str
    provenance: Provenance
    evidence_status: EvidenceStatus
    source_ids: list[str] = Field(default_factory=list)
    normalized_evidence: str = ""
    notes: str = ""


class RuntimeObservation(StrictModel):
    id: str
    origin_assertion_id: str
    delivery_tick: int
    channel: str
    source_alias: str
    reliability_hint: str
    runtime_payload: str


class WorldEffect(StrictModel):
    type: str
    target: str = ""
    value: Any = None
    provenance: Provenance = Provenance.HISTORICAL


class CanonEvent(StrictModel):
    id: str
    tick: int
    native_date: str
    title: str
    assertion_ids: list[str]
    world_effects: list[WorldEffect] = Field(default_factory=list)
    observations: dict[str, list[RuntimeObservation]] = Field(default_factory=dict)
    branch_policy: BranchPolicy
    tags: list[str] = Field(default_factory=list)
    marker: MarkerType = MarkerType.WORLD


class ActorDefinition(StrictModel):
    seat: str
    profile: str
    display_name: str
    runtime_alias: str
    authority: list[ActionType]
    initial_location: str
    description: str = ""


class Location(StrictModel):
    id: str
    display_name: str
    runtime_alias: str
    x: float
    y: float
    kind: str = "place"


class Route(StrictModel):
    id: str
    from_location: str
    to_location: str
    travel_days: int
    status: str = "open"


class ScenarioManifest(StrictModel):
    id: str
    title: str
    subtitle: str
    window_start: str
    window_end: str
    start_tick: int
    end_tick: int
    tick_unit: str = "day"


class WakePolicy(StrictModel):
    """Entry-local rule for which durable deliveries justify an Agent wake."""

    messages: bool = True
    observation_channels: list[str] = Field(default_factory=list)


class ForkDefinition(StrictModel):
    id: str
    event_id: str
    title: str
    premise: str
    display_name: str
    runtime_premise: str
    source_assertion_ids: list[str]
    max_days: int = 14
    playable_seats: list[str] = Field(default_factory=lambda: ["A"])
    actions: list[ActionType] = Field(default_factory=lambda: [ActionType.WAIT])
    confirmation_required: list[ActionType] = Field(default_factory=list)
    maximum_horizon: int = 14
    causal_envelope: list[str] = Field(default_factory=list)
    wake_policy: WakePolicy = Field(default_factory=WakePolicy)
    seat_brief: str = ""

    @property
    def horizon(self) -> int:
        return self.maximum_horizon or self.max_days


EntryDefinition = ForkDefinition


class BeliefUpdate(StrictModel):
    belief_key: str
    direction: str
    confidence: float = Field(ge=0, le=1)
    statement: str = ""


class Intention(StrictModel):
    action: ActionType
    target: str = ""
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ActorWakeResponse(StrictModel):
    assessment: str
    belief_updates: list[BeliefUpdate] = Field(default_factory=list)
    intentions: list[Intention] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    memory_action: str = "NO_CHANGE"
    memory_text: str = ""


class BranchAction(StrictModel):
    type: ActionType
    target: str = ""
    recipient: str = ""
    payload: str = ""
    priority: str = "normal"


class SeatContextView(StrictModel):
    """The only state contract allowed to cross into a Seat-side consumer."""

    worldline_id: str
    entry_id: str
    seat: str
    tick: int
    known_world: dict[str, Any] = Field(default_factory=dict)
    what_reached_you: list[dict[str, Any]] = Field(default_factory=list)
    what_you_carry: dict[str, Any] = Field(default_factory=dict)
    authority: list[ActionType] = Field(default_factory=list)
    known_uncertainty: list[str] = Field(default_factory=list)
    visible_entities: list[str] = Field(default_factory=list)
    visible_assertion_ids: list[str] = Field(default_factory=list)


class InteractionResult(StrictModel):
    kind: str
    answer: str = ""
    interpreted_actions: list[BranchAction] = Field(default_factory=list)
    status: ActionValidation | None = None
    requires_confirmation: bool = False
    confirmation_id: str = ""
    result: dict[str, Any] | None = None

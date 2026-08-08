from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrEnum):
    HISTORICAL = "historical"
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
    WAIT = "WAIT"


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


class ForkDefinition(StrictModel):
    id: str
    event_id: str
    title: str
    premise: str
    display_name: str
    runtime_premise: str
    source_assertion_ids: list[str]
    max_days: int = 14


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

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrEnum):
    HISTORICAL = "historical"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    MODELED = "modeled"
    VOLUME_DERIVED = "volume_derived"


class EvidenceStatus(StrEnum):
    CORROBORATED = "corroborated"
    SINGLE_ATTESTED = "single_attested"
    DISPUTED = "disputed"
    APPROXIMATE = "approximate"


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


class WorldlineKind(StrEnum):
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

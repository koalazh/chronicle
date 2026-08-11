from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol


class ResolutionContractError(ValueError):
    """A curated Resolution Contract cannot evaluate the supplied World Truth."""


class ResolutionGateStatus(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"


class ResolutionKind(StrEnum):
    DIRECT_CONFLICT = "DIRECT_CONFLICT"
    NEGOTIATED_SETTLEMENT = "NEGOTIATED_SETTLEMENT"
    WITHDRAWAL = "WITHDRAWAL"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class ResolutionReadiness:
    status: ResolutionGateStatus
    candidate_kind: ResolutionKind | None
    reasons: tuple[str, ...]
    facts: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == ResolutionGateStatus.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "candidate_kind": self.candidate_kind.value if self.candidate_kind else "",
            "reasons": list(self.reasons),
            "facts": list(self.facts),
        }


@dataclass(frozen=True)
class ResolutionEntityEffect:
    entity_id: str
    state: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "description": self.description,
        }


@dataclass(frozen=True)
class ResolutionAgreementEffect:
    agreement_id: str
    status: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "agreement_id": self.agreement_id,
            "status": self.status,
            "description": self.description,
        }


@dataclass(frozen=True)
class ResolutionResult:
    contract_id: str
    contract_version: int
    kind: ResolutionKind
    variant: str
    ambiguity_used: bool
    factors: tuple[str, ...]
    entity_effects: tuple[ResolutionEntityEffect, ...]
    agreement_effects: tuple[ResolutionAgreementEffect, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "kind": self.kind.value,
            "variant": self.variant,
            "ambiguity_used": self.ambiguity_used,
            "factors": list(self.factors),
            "entity_effects": [effect.to_dict() for effect in self.entity_effects],
            "agreement_effects": [effect.to_dict() for effect in self.agreement_effects],
        }


class CrisisResolutionContract(Protocol):
    id: str
    version: int

    def evaluate_gate(self, world: Mapping[str, Any]) -> ResolutionReadiness: ...

    def resolve(self, world: Mapping[str, Any], seed: str) -> ResolutionResult: ...

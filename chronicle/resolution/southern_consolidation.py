from __future__ import annotations

from typing import Any, Mapping

from .base import (
    ResolutionContractError,
    ResolutionEntityEffect,
    ResolutionGateStatus,
    ResolutionKind,
    ResolutionReadiness,
    ResolutionResult,
)


class SouthernConsolidationResolutionContract:
    """Small qualitative resolver for the post-Nanjing Jiangbei Knot."""

    id = "southern-consolidation-v1"
    version = 1

    @staticmethod
    def _state(world: Mapping[str, Any], entity_id: str) -> str:
        entities = world.get("entities", {})
        entity = entities.get(entity_id, {}) if isinstance(entities, Mapping) else {}
        return str(entity.get("state", "")) if isinstance(entity, Mapping) else ""

    def evaluate_gate(self, world: Mapping[str, Any]) -> ResolutionReadiness:
        mandate = self._state(world, "jiangbei-mandate")
        command = self._state(world, "jiangbei-command")
        facts = (f"jiangbei-mandate={mandate}", f"jiangbei-command={command}")
        if mandate == "ISSUED" and command == "COORDINATING":
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.RECOGNIZED_SETTLEMENT,
                reasons=("江北协调已经进入公开文书与可执行协调状态。",),
                facts=facts,
            )
        if command == "CONTESTED":
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.DEFERRED,
                reasons=("江北秩序的公开安排已经进入争议，暂不能形成稳定协调。",),
                facts=facts,
            )
        return ResolutionReadiness(
            status=ResolutionGateStatus.NOT_READY,
            candidate_kind=None,
            reasons=("南京中心与江北网络的协调仍可通过后续公开行动改变。",),
            facts=facts,
        )

    def resolve(self, world: Mapping[str, Any], seed: str) -> ResolutionResult:
        readiness = self.evaluate_gate(world)
        if not readiness.ready or readiness.candidate_kind is None:
            raise ResolutionContractError("江北整饬危局尚未进入可结算节点")
        if readiness.candidate_kind == ResolutionKind.RECOGNIZED_SETTLEMENT:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.RECOGNIZED_SETTLEMENT,
                variant="JIANGBEI_COORDINATION",
                ambiguity_used=False,
                summary="南京中心与江北军政网络已经通过独立行动形成可执行协调。",
                immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
                factors=readiness.facts,
                entity_effects=(
                    ResolutionEntityEffect(
                        "jiangbei-command", "COORDINATING", "江北军政网络进入可执行协调状态。"
                    ),
                    ResolutionEntityEffect(
                        "jiangbei-mandate", "ISSUED", "江北公开协调文书已经形成。"
                    ),
                ),
                agreement_effects=(),
            )
        return ResolutionResult(
            contract_id=self.id,
            contract_version=self.version,
            kind=ResolutionKind.DEFERRED,
            variant="JIANGBEI_CONTESTED",
            ambiguity_used=False,
            summary="江北秩序已经成为现实问题，但公开安排尚未稳定汇合。",
            immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
            factors=readiness.facts,
            entity_effects=(
                ResolutionEntityEffect("jiangbei-command", "CONTESTED", "公开协调转为争议。"),
            ),
            agreement_effects=(),
        )

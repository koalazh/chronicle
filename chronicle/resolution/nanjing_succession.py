from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .base import (
    ResolutionContractError,
    ResolutionEntityEffect,
    ResolutionGateStatus,
    ResolutionKind,
    ResolutionReadiness,
    ResolutionResult,
)


@dataclass(frozen=True)
class _NanjingFacts:
    court_state: str
    recognition_state: str
    fu_state: str
    lu_state: str
    military_backing_state: str
    fu_endorsement_ids: tuple[str, ...]
    lu_endorsement_ids: tuple[str, ...]


class NanjingSuccessionResolutionContract:
    """Curated deterministic resolver for the 南都继统 crisis.

    Only Projection world facts enter this contract. It does not inspect
    private plans, Beliefs, prose, historical anchors, or an LLM response.
    """

    id = "nanjing-succession-v1"
    version = 1

    def evaluate_gate(self, world: Mapping[str, Any]) -> ResolutionReadiness:
        facts = self._facts(world)
        if self._is_contested(facts):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.CONTESTED_SUCCESSION,
                reasons=("两位候选都已进入南京程序，并已有互不相容的公开支持安排。",),
                facts=self._gate_facts(facts),
            )
        if self._is_recognized(facts, "FU"):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.RECOGNIZED_SETTLEMENT,
                reasons=("福王已在南京完成有支持约束的制度承认。",),
                facts=self._gate_facts(facts),
            )
        if self._is_recognized(facts, "LU"):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.RECOGNIZED_SETTLEMENT,
                reasons=("潞王已在南京完成有支持约束的制度承认。",),
                facts=self._gate_facts(facts),
            )
        if self._is_fragmented(facts):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.FRAGMENTED_SETTLEMENT,
                reasons=("两位候选都已进入程序空间，但没有形成可以执行的单一承认。",),
                facts=self._gate_facts(facts),
            )
        if facts.recognition_state == "DEFERRED":
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.DEFERRED,
                reasons=("南京程序已明确记录为延期，当前没有可执行的继统承认。",),
                facts=self._gate_facts(facts),
            )
        return ResolutionReadiness(
            status=ResolutionGateStatus.NOT_READY,
            candidate_kind=None,
            reasons=("候选、支持与制度程序仍能通过后续世界行动形成不同组合。",),
            facts=self._gate_facts(facts),
        )

    def resolve(self, world: Mapping[str, Any], seed: str) -> ResolutionResult:
        readiness = self.evaluate_gate(world)
        if not readiness.ready or readiness.candidate_kind is None:
            raise ResolutionContractError("南都继统危局尚未进入可结算节点")
        facts = self._facts(world)
        if readiness.candidate_kind == ResolutionKind.RECOGNIZED_SETTLEMENT:
            return self._recognized_result(facts)
        if readiness.candidate_kind == ResolutionKind.CONTESTED_SUCCESSION:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.CONTESTED_SUCCESSION,
                variant="DUAL_CLAIMANT_REALITY",
                ambiguity_used=False,
                summary="南京已经同时形成两套难以互相吸收的候选与支持现实，继统问题转为公开争议。",
                immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
                factors=(
                    "福王与潞王都已进入南京的程序空间。",
                    "两位候选各自已有仍有效或已经履行的公开支持安排。",
                    "南京中枢尚未形成可以排除另一候选的单一制度承认。",
                ),
                entity_effects=(
                    ResolutionEntityEffect(
                        "nanjing-political-center",
                        "CONTESTED",
                        "南京政治中心已经在当前世界形成公开争议状态。",
                    ),
                    ResolutionEntityEffect(
                        "nanjing-recognition",
                        "CONTESTED",
                        "相互不相容的候选安排使制度承认转为公开争议。",
                    ),
                    ResolutionEntityEffect(
                        "nanjing-court",
                        "CONTESTED",
                        "中枢程序已不能作为单一承认的入口。",
                    ),
                ),
                agreement_effects=(),
            )
        if readiness.candidate_kind == ResolutionKind.FRAGMENTED_SETTLEMENT:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.FRAGMENTED_SETTLEMENT,
                variant="DUAL_ENTRY_WITHOUT_RECOGNITION",
                ambiguity_used=False,
                summary="候选都已进入南京程序空间，但程序与可见支持没有汇合为可执行的继统现实。",
                immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
                factors=(
                    "福王与潞王都已进入南京的程序空间。",
                    "南京中枢仍处于议决状态。",
                    "没有足以完成单一制度承认的支持安排。",
                ),
                entity_effects=(
                    ResolutionEntityEffect(
                        "nanjing-political-center",
                        "FRAGMENTED",
                        "南京政治中心没有在当前世界汇合为单一承认。",
                    ),
                    ResolutionEntityEffect(
                        "nanjing-recognition",
                        "FRAGMENTED",
                        "候选进入与制度程序脱节，未能形成单一承认。",
                    ),
                    ResolutionEntityEffect(
                        "nanjing-court",
                        "FRAGMENTED",
                        "中枢程序没有汇合为可执行的继统结论。",
                    ),
                ),
                agreement_effects=(),
            )
        return ResolutionResult(
            contract_id=self.id,
            contract_version=self.version,
            kind=ResolutionKind.DEFERRED,
            variant="PROCEDURE_DEFERRED",
            ambiguity_used=False,
            summary="南京的继统程序已经被明确延期，当前尚未形成可执行的局部承认。",
            immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
            factors=(
                "制度承认已被记录为延期。",
                "当前世界中没有候选完成可执行的制度承认。",
            ),
            entity_effects=(
                ResolutionEntityEffect(
                    "nanjing-political-center",
                    "DEFERRED",
                    "南京政治中心的形成在当前世界被明确延期。",
                ),
                ResolutionEntityEffect(
                    "nanjing-recognition",
                    "DEFERRED",
                    "继统程序暂未形成可执行的局部承认。",
                ),
                ResolutionEntityEffect(
                    "nanjing-court",
                    "DEFERRED",
                    "中枢程序暂时没有形成可结算的继统结果。",
                ),
            ),
            agreement_effects=(),
        )

    def _recognized_result(self, facts: _NanjingFacts) -> ResolutionResult:
        fu_recognized = facts.recognition_state == "FU_RECOGNIZED"
        winner_id = "fu-prince" if fu_recognized else "lu-prince"
        loser_id = "lu-prince" if fu_recognized else "fu-prince"
        winner_name = "福王" if fu_recognized else "潞王"
        factors = [
            f"{winner_name}已经进入南京的程序空间。",
            f"南京制度承认已明确为{winner_name}。",
            f"支持{winner_name}的公开安排已经生效或完成。",
        ]
        if fu_recognized and facts.military_backing_state == "FU_BACKED":
            factors.append("江北方向的可见军政支持已经以福王一方的安排出现。")
        return ResolutionResult(
            contract_id=self.id,
            contract_version=self.version,
            kind=ResolutionKind.RECOGNIZED_SETTLEMENT,
            variant="FU_RECOGNIZED" if fu_recognized else "LU_RECOGNIZED",
            ambiguity_used=False,
            summary=f"南京已经形成以{winner_name}为中心的可执行制度承认，继统危局在这一局部范围内得到结算。",
            immediate_actor_ids=("shi-kefa", "ma-shiying", "han-zanzhou"),
            factors=tuple(factors),
            entity_effects=(
                ResolutionEntityEffect(
                    "nanjing-political-center",
                    facts.recognition_state,
                    "南京政治中心的当前承认状态已经成为世界事实。",
                ),
                ResolutionEntityEffect(
                    "nanjing-recognition",
                    facts.recognition_state,
                    "已经形成的制度承认成为危局结算后的世界事实。",
                ),
                ResolutionEntityEffect(
                    winner_id,
                    "IN_NANJING",
                    f"{winner_name}继续处于已完成承认的南京程序空间。",
                ),
                ResolutionEntityEffect(
                    loser_id,
                    "NOT_SELECTED",
                    "当前局部制度承认未选择另一位候选。",
                ),
                ResolutionEntityEffect(
                    "nanjing-court",
                    "RECOGNIZED",
                    "中枢程序已经形成可执行的局部结论。",
                ),
            ),
            agreement_effects=(),
        )

    @staticmethod
    def _is_recognized(facts: _NanjingFacts, claimant: str) -> bool:
        if claimant == "FU":
            return (
                facts.recognition_state == "FU_RECOGNIZED"
                and facts.fu_state == "IN_NANJING"
                and bool(facts.fu_endorsement_ids)
            )
        return (
            facts.recognition_state == "LU_RECOGNIZED"
            and facts.lu_state == "IN_NANJING"
            and bool(facts.lu_endorsement_ids)
        )

    @staticmethod
    def _is_contested(facts: _NanjingFacts) -> bool:
        return (
            facts.fu_state == "IN_NANJING"
            and facts.lu_state == "IN_NANJING"
            and bool(facts.fu_endorsement_ids)
            and bool(facts.lu_endorsement_ids)
            and facts.recognition_state in {"DELIBERATING", "URGENT", "CONTESTED"}
        )

    @staticmethod
    def _is_fragmented(facts: _NanjingFacts) -> bool:
        return (
            facts.fu_state == "IN_NANJING"
            and facts.lu_state == "IN_NANJING"
            and not facts.fu_endorsement_ids
            and not facts.lu_endorsement_ids
            and facts.court_state == "DELIBERATING"
            and facts.recognition_state in {"DELIBERATING", "URGENT"}
        )

    def _facts(self, world: Mapping[str, Any]) -> _NanjingFacts:
        return _NanjingFacts(
            court_state=self._entity_state(world, "nanjing-court"),
            recognition_state=self._entity_state(world, "nanjing-recognition"),
            fu_state=self._entity_state(world, "fu-prince"),
            lu_state=self._entity_state(world, "lu-prince"),
            military_backing_state=self._entity_state(world, "jiangbei-military-backing"),
            fu_endorsement_ids=self._endorsement_agreement_ids(world, "fu-prince"),
            lu_endorsement_ids=self._endorsement_agreement_ids(world, "lu-prince"),
        )

    @staticmethod
    def _entity_state(world: Mapping[str, Any], entity_id: str) -> str:
        entities = world.get("entities", {})
        entity = entities.get(entity_id, {}) if isinstance(entities, Mapping) else {}
        return str(entity.get("state", "")) if isinstance(entity, Mapping) else ""

    @staticmethod
    def _endorsement_agreement_ids(world: Mapping[str, Any], claimant_id: str) -> tuple[str, ...]:
        agreements = world.get("agreements", [])
        if not isinstance(agreements, list):
            return ()
        agreement_ids = []
        for agreement in agreements:
            if not isinstance(agreement, Mapping):
                continue
            if agreement.get("status") not in {"ACTIVE", "FULFILLED"}:
                continue
            terms = agreement.get("terms", [])
            if not isinstance(terms, list) or not any(
                isinstance(term, Mapping)
                and term.get("type") == "endorsement"
                and term.get("subject") == claimant_id
                and term.get("value") == "public_support"
                for term in terms
            ):
                continue
            agreement_ids.append(str(agreement.get("id", "")))
        return tuple(sorted(item for item in agreement_ids if item))

    @staticmethod
    def _gate_facts(facts: _NanjingFacts) -> tuple[str, ...]:
        values = [
            f"南京制度承认状态：{facts.recognition_state or 'UNKNOWN'}。",
            f"福王状态：{facts.fu_state or 'UNKNOWN'}。",
            f"潞王状态：{facts.lu_state or 'UNKNOWN'}。",
            f"南京程序状态：{facts.court_state or 'UNKNOWN'}。",
        ]
        if facts.military_backing_state:
            values.append(f"江北可见军政支持：{facts.military_backing_state}。")
        if facts.fu_endorsement_ids:
            values.append("福王已有有效或已履行的公开支持安排。")
        if facts.lu_endorsement_ids:
            values.append("潞王已有有效或已履行的公开支持安排。")
        return tuple(values)

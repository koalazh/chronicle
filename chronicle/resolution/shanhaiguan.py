from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from .base import (
    ResolutionAgreementEffect,
    ResolutionContractError,
    ResolutionEntityEffect,
    ResolutionGateStatus,
    ResolutionKind,
    ResolutionReadiness,
    ResolutionResult,
)

_FORCE_WEIGHT = {
    "DISPERSED": 0,
    "FORMING": 0,
    "READY": 1,
    "MOVING": 1,
    "COMMITTED": 2,
    "DEGRADED": 0,
    "WITHDRAWN": 0,
}
_PRESENT_FORCE_STATES = frozenset({"READY", "MOVING", "COMMITTED"})
_PASSAGE_STATUSES = frozenset({"ACTIVE", "FULFILLED"})


@dataclass(frozen=True)
class _ShanhaiFacts:
    pass_state: str
    transit_window: str
    qing_force_state: str
    shun_force_state: str
    wu_force_state: str
    qing_at_pass: bool
    shun_at_pass: bool
    wu_at_pass: bool
    passage_access_agreement_ids: tuple[str, ...]
    active_passage_agreement_ids: tuple[str, ...]
    breached_passage_agreement_ids: tuple[str, ...]
    qing_investigations: int
    shun_investigations: int

    @property
    def has_passage_access(self) -> bool:
        return bool(self.passage_access_agreement_ids) and self.pass_state != "CLOSED"


class ShanhaiGuanResolutionContract:
    """Curated qualitative resolver for the 山海关 crisis.

    The resolver observes Projection truth only. It does not inspect historical
    anchors, Actor prose, private Beliefs, or an LLM response.
    """

    id = "shanhaiguan-v1"
    version = 1

    def evaluate_gate(self, world: Mapping[str, Any]) -> ResolutionReadiness:
        facts = self._facts(world)
        if facts.qing_at_pass and (
            facts.shun_at_pass
            or (
                facts.wu_at_pass
                and (facts.pass_state == "CLOSED" or facts.breached_passage_agreement_ids)
            )
        ):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.DIRECT_CONFLICT,
                reasons=("主要兵力已经在山海关形成无法再由通信化解的直接接触。",),
                facts=self._gate_facts(facts),
            )
        if facts.qing_at_pass and facts.has_passage_access and not facts.shun_at_pass:
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.NEGOTIATED_SETTLEMENT,
                reasons=("通行安排已被实际兑现，并形成了可结算的关口秩序。",),
                facts=self._gate_facts(facts),
            )
        if (
            facts.pass_state == "CLOSED"
            and facts.qing_force_state == "WITHDRAWN"
            and not facts.qing_at_pass
        ):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.WITHDRAWAL,
                reasons=("关口已关闭，关外主力也已经退出这一接触空间。",),
                facts=self._gate_facts(facts),
            )
        if (
            facts.pass_state == "CLOSED"
            and not facts.qing_at_pass
            and not facts.shun_at_pass
        ):
            return ResolutionReadiness(
                status=ResolutionGateStatus.READY,
                candidate_kind=ResolutionKind.DEFERRED,
                reasons=("关口控制已经形成，但主要力量尚未形成可裁定的直接接触。",),
                facts=self._gate_facts(facts),
            )
        reasons = ["当前仍可通过普通通信、行动完成或新的世界信息改变局势。"]
        if not facts.qing_at_pass:
            reasons.append("清军尚未以可结算的兵力进入山海关。")
        if not facts.shun_at_pass and facts.pass_state != "CLOSED" and not facts.has_passage_access:
            reasons.append("关口通行与控制尚未形成稳定安排。")
        return ResolutionReadiness(
            status=ResolutionGateStatus.NOT_READY,
            candidate_kind=None,
            reasons=tuple(reasons),
            facts=self._gate_facts(facts),
        )

    def resolve(self, world: Mapping[str, Any], seed: str) -> ResolutionResult:
        readiness = self.evaluate_gate(world)
        if not readiness.ready or readiness.candidate_kind is None:
            raise ResolutionContractError("山海关危局尚未进入可结算节点")
        facts = self._facts(world)
        if readiness.candidate_kind == ResolutionKind.DIRECT_CONFLICT:
            return self._resolve_direct_conflict(facts, seed)
        if readiness.candidate_kind == ResolutionKind.NEGOTIATED_SETTLEMENT:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.NEGOTIATED_SETTLEMENT,
                variant="PASSAGE_IMPLEMENTED",
                ambiguity_used=False,
                factors=(
                    "清军已在关口现实抵达。",
                    "吴三桂与多尔衮之间的通行安排仍然有效。",
                    "大顺东向兵力尚未进入同一直接接触空间。",
                ),
                entity_effects=(
                    ResolutionEntityEffect(
                        "shanhai-pass",
                        "OPEN",
                        "通行安排被现实兑现，山海关通道维持开放。",
                    ),
                    ResolutionEntityEffect(
                        "qing-expedition-force",
                        "COMMITTED",
                        "清军已将主力投入既成的关口安排。",
                    ),
                ),
                agreement_effects=tuple(
                    ResolutionAgreementEffect(
                        agreement_id,
                        "FULFILLED",
                        "通行条件已被实际履行。",
                    )
                    for agreement_id in facts.active_passage_agreement_ids
                ),
            )
        if readiness.candidate_kind == ResolutionKind.WITHDRAWAL:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.WITHDRAWAL,
                variant="QING_WITHDRAWS",
                ambiguity_used=False,
                factors=(
                    "山海关通道已经关闭。",
                    "清军主力已经退出关口接触空间。",
                    "没有第二支主要力量与其形成直接冲突。",
                ),
                entity_effects=(
                    ResolutionEntityEffect(
                        "shanhai-pass",
                        "CLOSED",
                        "关口保持关闭，关外主力未能以此进入。",
                    ),
                    ResolutionEntityEffect(
                        "qing-expedition-force",
                        "WITHDRAWN",
                        "清军主力退出这一局部危局。",
                    ),
                ),
                agreement_effects=(),
            )
        return ResolutionResult(
            contract_id=self.id,
            contract_version=self.version,
            kind=ResolutionKind.DEFERRED,
            variant="PASS_CLOSED_DEFERRED",
            ambiguity_used=False,
            factors=(
                "山海关控制已形成关闭状态。",
                "清军尚未以主力进入关口。",
                "大顺东向兵力尚未与关口形成可裁定的直接接触。",
            ),
            entity_effects=(
                ResolutionEntityEffect(
                    "shanhai-pass",
                    "CLOSED",
                    "关口关闭形成了新的、但仍可能在后续改变的局部现实。",
                ),
            ),
            agreement_effects=(),
        )

    def _resolve_direct_conflict(self, facts: _ShanhaiFacts, seed: str) -> ResolutionResult:
        qing_weight = _FORCE_WEIGHT.get(facts.qing_force_state, 0)
        shun_weight = _FORCE_WEIGHT.get(facts.shun_force_state, 0)
        factors = [
            "清军与大顺东向兵力都已进入山海关的直接接触空间。",
            "双方可投入兵力的整备与投入状态已经成为现实差异。",
        ]
        if facts.has_passage_access:
            qing_weight += 1
            factors.append("通行安排仍有效，使清军的接近与协同得到现实支撑。")
        elif facts.breached_passage_agreement_ids:
            factors.append("既有通行安排已经被违背，关口协同不再可靠。")
        if facts.pass_state == "CLOSED":
            shun_weight += 1
            factors.append("关口已经关闭，守方保有直接的控制条件。")
        if facts.qing_investigations:
            qing_weight += 1
            factors.append("清军已完成可用的关口调查，准备不再完全依赖传闻。")
        if facts.shun_investigations:
            shun_weight += 1
            factors.append("大顺方面已完成可用的关口调查，准备不再完全依赖传闻。")
        if facts.transit_window == "CLOSING":
            factors.append("京东通行窗口已经收紧，迟到的增援难以改变这次接触。")

        ambiguity_used = abs(qing_weight - shun_weight) <= 1
        if ambiguity_used:
            qing_advances = self._seed_selects_qing(seed)
            factors.append("已建模条件仍落在可接受的歧义带内，因此使用本局固定 seed 选择其中一种结果。")
        else:
            qing_advances = qing_weight > shun_weight

        if qing_advances:
            return ResolutionResult(
                contract_id=self.id,
                contract_version=self.version,
                kind=ResolutionKind.DIRECT_CONFLICT,
                variant="QING_ADVANCE",
                ambiguity_used=ambiguity_used,
                factors=tuple(factors),
                entity_effects=(
                    ResolutionEntityEffect(
                        "shanhai-pass",
                        "QING_CONTROL",
                        "直接冲突后，清军取得山海关通道的局部控制。",
                    ),
                    ResolutionEntityEffect(
                        "qing-expedition-force",
                        "COMMITTED",
                        "清军主力维持在已经取得的接触空间。",
                    ),
                    ResolutionEntityEffect(
                        "shun-eastern-force",
                        "DEGRADED",
                        "大顺东向兵力在这次直接冲突后失去原有投入状态。",
                    ),
                ),
                agreement_effects=(),
            )
        return ResolutionResult(
            contract_id=self.id,
            contract_version=self.version,
            kind=ResolutionKind.DIRECT_CONFLICT,
            variant="SHUN_HOLDS",
            ambiguity_used=ambiguity_used,
            factors=tuple(factors),
            entity_effects=(
                ResolutionEntityEffect(
                    "shanhai-pass",
                    "CLOSED",
                    "直接冲突后，关口仍未向关外主力开放。",
                ),
                ResolutionEntityEffect(
                    "shun-eastern-force",
                    "COMMITTED",
                    "大顺东向兵力维持在关口的现实投入。",
                ),
                ResolutionEntityEffect(
                    "qing-expedition-force",
                    "DEGRADED",
                    "清军主力在这次直接冲突后失去原有投入状态。",
                ),
            ),
            agreement_effects=(),
        )

    def _facts(self, world: Mapping[str, Any]) -> _ShanhaiFacts:
        positions = world.get("positions", {})
        qing_force_state = self._entity_state(world, "qing-expedition-force")
        shun_force_state = self._entity_state(world, "shun-eastern-force")
        wu_force_state = self._entity_state(world, "wu-field-force")
        passage_agreements = self._passage_agreements(world)
        return _ShanhaiFacts(
            pass_state=self._entity_state(world, "shanhai-pass"),
            transit_window=self._entity_state(world, "eastern-transit-window"),
            qing_force_state=qing_force_state,
            shun_force_state=shun_force_state,
            wu_force_state=wu_force_state,
            qing_at_pass=(
                positions.get("dorgon") == "shanhaiguan"
                and qing_force_state in _PRESENT_FORCE_STATES
            ),
            shun_at_pass=(
                positions.get("li-zicheng") == "shanhaiguan"
                and shun_force_state in _PRESENT_FORCE_STATES
            ),
            wu_at_pass=(
                positions.get("wu-sangui") == "shanhaiguan"
                and wu_force_state in _PRESENT_FORCE_STATES
            ),
            passage_access_agreement_ids=tuple(
                item["id"] for item in passage_agreements if item["status"] in _PASSAGE_STATUSES
            ),
            active_passage_agreement_ids=tuple(
                item["id"] for item in passage_agreements if item["status"] == "ACTIVE"
            ),
            breached_passage_agreement_ids=tuple(
                item["id"] for item in passage_agreements if item["status"] == "BREACHED"
            ),
            qing_investigations=self._completed_investigation_count(world, "dorgon"),
            shun_investigations=self._completed_investigation_count(world, "li-zicheng"),
        )

    @staticmethod
    def _entity_state(world: Mapping[str, Any], entity_id: str) -> str:
        entities = world.get("entities", {})
        entity = entities.get(entity_id, {}) if isinstance(entities, Mapping) else {}
        return str(entity.get("state", "")) if isinstance(entity, Mapping) else ""

    @staticmethod
    def _passage_agreements(world: Mapping[str, Any]) -> list[dict[str, str]]:
        agreements = world.get("agreements", [])
        if not isinstance(agreements, list):
            return []
        matching: list[dict[str, str]] = []
        for agreement in agreements:
            if not isinstance(agreement, Mapping):
                continue
            if set(agreement.get("parties", [])) != {"wu-sangui", "dorgon"}:
                continue
            terms = agreement.get("terms", [])
            if not isinstance(terms, list) or not any(
                isinstance(term, Mapping)
                and term.get("type") == "passage"
                and term.get("subject") == "shanhai-pass"
                and term.get("value") == "permitted"
                for term in terms
            ):
                continue
            matching.append(
                {
                    "id": str(agreement.get("id", "")),
                    "status": str(agreement.get("status", "")),
                }
            )
        return sorted(matching, key=lambda item: item["id"])

    @staticmethod
    def _completed_investigation_count(world: Mapping[str, Any], actor_id: str) -> int:
        investigations = world.get("investigations", [])
        if not isinstance(investigations, list):
            return 0
        return sum(
            1
            for investigation in investigations
            if isinstance(investigation, Mapping)
            and investigation.get("actor_id") == actor_id
            and investigation.get("status") == "COMPLETED"
        )

    @staticmethod
    def _gate_facts(facts: _ShanhaiFacts) -> tuple[str, ...]:
        result = [
            f"山海关通道状态：{facts.pass_state or 'UNKNOWN'}。",
            f"清军主力状态：{facts.qing_force_state or 'UNKNOWN'}。",
            f"大顺东向兵力状态：{facts.shun_force_state or 'UNKNOWN'}。",
        ]
        if facts.passage_access_agreement_ids:
            result.append("吴三桂与多尔衮之间存在有效的通行安排。")
        if facts.breached_passage_agreement_ids:
            result.append("吴三桂与多尔衮之间的通行安排已被违背。")
        return tuple(result)

    def _seed_selects_qing(self, seed: str) -> bool:
        digest = hashlib.sha256(f"{self.id}:{self.version}:{seed}".encode()).digest()
        return bool(digest[0] & 1)

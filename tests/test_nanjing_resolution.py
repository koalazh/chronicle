from __future__ import annotations

import copy
import json

import pytest

from chronicle.crisis_runtime import CrisisRunEngine, RunMode
from chronicle.resolution import get_resolution_contract
from chronicle.resolution.base import ResolutionContractError, ResolutionGateStatus, ResolutionKind


def _world(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]
    projection = copy.deepcopy(engine.db.worldline_snapshot(run_id)["projection"])
    engine.seal(run_id, reason="nanjing-resolution-fixture")
    return projection


def _endorsement_agreement(world, claimant_id, parties, *, status="FULFILLED"):
    world["agreements"].append(
        {
            "id": f"agreement-{claimant_id}",
            "parties": list(parties),
            "terms": [
                {
                    "type": "endorsement",
                    "subject": claimant_id,
                    "value": "public_support",
                    "description": "形成可被对方依赖的公开支持安排。",
                }
            ],
            "status": status,
        }
    )


def _fu_recognized_world(app_config):
    world = _world(app_config)
    world["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    world["entities"]["nanjing-recognition"]["state"] = "FU_RECOGNIZED"
    world["entities"]["fu-prince"]["state"] = "IN_NANJING"
    world["entities"]["jiangbei-military-backing"]["state"] = "FU_BACKED"
    _endorsement_agreement(world, "fu-prince", ("ma-shiying", "han-zanzhou"))
    return world


def _lu_recognized_world(app_config):
    world = _world(app_config)
    world["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    world["entities"]["nanjing-recognition"]["state"] = "LU_RECOGNIZED"
    world["entities"]["lu-prince"]["state"] = "IN_NANJING"
    _endorsement_agreement(world, "lu-prince", ("shi-kefa", "han-zanzhou"))
    return world


def test_nanjing_resolver_handles_historical_like_fu_convergence_without_history_tiebreak(
    app_config,
):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    world = _fu_recognized_world(app_config)

    readiness = resolver.evaluate_gate(world)
    result = resolver.resolve(world, "historical-like-seed")

    assert readiness.status == ResolutionGateStatus.READY
    assert readiness.candidate_kind == ResolutionKind.RECOGNIZED_SETTLEMENT
    assert result.kind == ResolutionKind.RECOGNIZED_SETTLEMENT
    assert result.variant == "FU_RECOGNIZED"
    assert result.ambiguity_used is False
    assert all("历史" not in factor for factor in result.factors)
    assert {effect.entity_id for effect in result.entity_effects} == {
        "nanjing-recognition",
        "fu-prince",
        "lu-prince",
        "nanjing-court",
    }


def test_nanjing_resolver_can_recognize_the_alternative_claimant(app_config):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    world = _lu_recognized_world(app_config)

    result = resolver.resolve(world, "lu-recognition-seed")

    assert result.kind == ResolutionKind.RECOGNIZED_SETTLEMENT
    assert result.variant == "LU_RECOGNIZED"
    assert result.entity_effects[2].entity_id == "fu-prince"
    assert result.entity_effects[2].state == "NOT_SELECTED"


def test_nanjing_resolver_distinguishes_contested_and_fragmented_realities(app_config):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    contested = _world(app_config)
    contested["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    contested["entities"]["nanjing-recognition"]["state"] = "DELIBERATING"
    contested["entities"]["fu-prince"]["state"] = "IN_NANJING"
    contested["entities"]["lu-prince"]["state"] = "IN_NANJING"
    _endorsement_agreement(contested, "fu-prince", ("ma-shiying", "han-zanzhou"))
    _endorsement_agreement(contested, "lu-prince", ("shi-kefa", "han-zanzhou"))

    fragmented = copy.deepcopy(contested)
    fragmented["agreements"] = []

    contested_result = resolver.resolve(contested, "contested-seed")
    fragmented_result = resolver.resolve(fragmented, "fragmented-seed")

    assert contested_result.kind == ResolutionKind.CONTESTED_SUCCESSION
    assert contested_result.variant == "DUAL_CLAIMANT_REALITY"
    assert fragmented_result.kind == ResolutionKind.FRAGMENTED_SETTLEMENT
    assert fragmented_result.variant == "DUAL_ENTRY_WITHOUT_RECOGNITION"


def test_nanjing_resolver_allows_an_explicit_deferred_procedure(app_config):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    world = _world(app_config)
    world["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    world["entities"]["nanjing-recognition"]["state"] = "DEFERRED"

    result = resolver.resolve(world, "deferred-seed")

    assert result.kind == ResolutionKind.DEFERRED
    assert result.variant == "PROCEDURE_DEFERRED"


def test_nanjing_resolver_remains_unready_without_a_settling_world_predicate(app_config):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    world = _world(app_config)

    readiness = resolver.evaluate_gate(world)

    assert readiness.status == ResolutionGateStatus.NOT_READY
    assert readiness.candidate_kind is None
    with pytest.raises(ResolutionContractError, match="尚未进入可结算节点"):
        resolver.resolve(world, "not-ready-seed")


def test_nanjing_resolver_is_byte_stable_and_does_not_mutate_world(app_config):
    resolver = get_resolution_contract("nanjing-succession-v1", 1)
    world = _fu_recognized_world(app_config)
    before = copy.deepcopy(world)

    first = resolver.resolve(world, "first-seed")
    repeated = resolver.resolve(copy.deepcopy(world), "different-seed")

    assert world == before
    assert json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True) == json.dumps(
        repeated.to_dict(), ensure_ascii=False, sort_keys=True
    )

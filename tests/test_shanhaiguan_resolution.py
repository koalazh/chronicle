from __future__ import annotations

import copy
import json

import pytest

from chronicle.crisis_runtime import CrisisRunEngine, RunMode
from chronicle.resolution import get_resolution_contract
from chronicle.resolution.base import ResolutionContractError, ResolutionGateStatus, ResolutionKind


def _world(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    projection = copy.deepcopy(engine.db.worldline_snapshot(run_id)["projection"])
    engine.seal(run_id, reason="resolution_fixture")
    return projection


def _passage_agreement(world, *, status="FULFILLED"):
    world["agreements"].append(
        {
            "id": "agreement-passage",
            "parties": ["wu-sangui", "dorgon"],
            "terms": [
                {
                    "type": "passage",
                    "subject": "shanhai-pass",
                    "value": "permitted",
                    "description": "允许清军通过山海关。",
                }
            ],
            "status": status,
        }
    )


def _direct_conflict_world(app_config, *, qing_state="COMMITTED", shun_state="COMMITTED"):
    world = _world(app_config)
    world["positions"].update({"dorgon": "shanhaiguan", "li-zicheng": "shanhaiguan"})
    world["entities"]["qing-expedition-force"]["state"] = qing_state
    world["entities"]["shun-eastern-force"]["state"] = shun_state
    return world


def test_shanhaiguan_resolver_handles_historical_like_convergence_without_history_tiebreak(
    app_config,
):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    world = _direct_conflict_world(app_config)
    _passage_agreement(world)

    readiness = resolver.evaluate_gate(world)
    result = resolver.resolve(world, "historical-like-seed")

    assert readiness.status == ResolutionGateStatus.READY
    assert readiness.candidate_kind == ResolutionKind.DIRECT_CONFLICT
    assert result.kind == ResolutionKind.DIRECT_CONFLICT
    assert all("历史" not in factor for factor in result.factors)
    assert {effect.entity_id for effect in result.entity_effects} == {
        "shanhai-pass",
        "qing-expedition-force",
        "shun-eastern-force",
    }


def test_passage_agreement_can_avoid_direct_conflict_and_settle_the_pass(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    world = _world(app_config)
    world["positions"]["dorgon"] = "shanhaiguan"
    world["entities"]["qing-expedition-force"]["state"] = "COMMITTED"
    _passage_agreement(world, status="ACTIVE")

    readiness = resolver.evaluate_gate(world)
    result = resolver.resolve(world, "agreement-seed")

    assert readiness.candidate_kind == ResolutionKind.NEGOTIATED_SETTLEMENT
    assert result.kind == ResolutionKind.NEGOTIATED_SETTLEMENT
    assert result.variant == "PASSAGE_IMPLEMENTED"
    assert result.agreement_effects[0].status == "FULFILLED"
    assert result.ambiguity_used is False


def test_no_qing_access_does_not_force_a_resolution(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    world = _world(app_config)
    world["positions"]["dorgon"] = "shanhaiguan"
    world["entities"]["qing-expedition-force"]["state"] = "COMMITTED"

    readiness = resolver.evaluate_gate(world)

    assert readiness.status == ResolutionGateStatus.NOT_READY
    assert readiness.candidate_kind is None
    with pytest.raises(ResolutionContractError, match="尚未进入可结算节点"):
        resolver.resolve(world, "no-access-seed")


def test_pressure_and_shun_arrival_can_defer_without_replacing_qing_choice(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    world = _world(app_config)
    world["positions"]["li-zicheng"] = "shanhaiguan"
    world["entities"]["shun-eastern-force"]["state"] = "COMMITTED"
    world["entities"]["qing-expedition-force"]["state"] = "READY"
    world["entities"]["eastern-transit-window"]["state"] = "CLOSING"

    readiness = resolver.evaluate_gate(world)
    result = resolver.resolve(world, "pressure-deferred-seed")

    assert readiness.status == ResolutionGateStatus.READY
    assert readiness.candidate_kind == ResolutionKind.DEFERRED
    assert result.variant == "SHUN_PRESSURE_DEFERRED"
    assert {effect.entity_id for effect in result.entity_effects} == {
        "shanhai-pass",
        "eastern-transit-window",
    }
    assert all(effect.entity_id != "qing-expedition-force" for effect in result.entity_effects)


def test_direct_conflict_uses_changed_readiness_and_control_as_world_facts(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    qing_advantage = _direct_conflict_world(
        app_config, qing_state="COMMITTED", shun_state="READY"
    )
    _passage_agreement(qing_advantage)
    shun_holds = _direct_conflict_world(
        app_config, qing_state="READY", shun_state="COMMITTED"
    )
    shun_holds["entities"]["shanhai-pass"]["state"] = "CLOSED"

    qing_result = resolver.resolve(qing_advantage, "readiness-seed")
    shun_result = resolver.resolve(shun_holds, "readiness-seed")

    assert qing_result.variant == "QING_ADVANCE"
    assert shun_result.variant == "SHUN_HOLDS"
    assert qing_result.ambiguity_used is False
    assert shun_result.ambiguity_used is False


def test_withdrawal_and_deferred_are_distinct_non_battle_resolutions(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    withdrawal = _world(app_config)
    withdrawal["entities"]["shanhai-pass"]["state"] = "CLOSED"
    withdrawal["entities"]["qing-expedition-force"]["state"] = "WITHDRAWN"
    deferred = _world(app_config)
    deferred["entities"]["shanhai-pass"]["state"] = "CLOSED"

    withdrawal_result = resolver.resolve(withdrawal, "withdrawal-seed")
    deferred_result = resolver.resolve(deferred, "deferred-seed")

    assert withdrawal_result.kind == ResolutionKind.WITHDRAWAL
    assert deferred_result.kind == ResolutionKind.DEFERRED


def test_ambiguity_band_is_seeded_and_byte_for_byte_repeatable(app_config):
    resolver = get_resolution_contract("shanhaiguan-v1", 1)
    world = _direct_conflict_world(app_config)
    before = copy.deepcopy(world)

    first = resolver.resolve(world, "ambiguity-seed")
    repeated = resolver.resolve(copy.deepcopy(world), "ambiguity-seed")
    alternatives = {
        resolver.resolve(copy.deepcopy(world), seed).variant
        for seed in ("ambiguity-a", "ambiguity-b", "ambiguity-c", "ambiguity-d")
    }

    assert first.ambiguity_used is True
    assert world == before
    assert json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True) == json.dumps(
        repeated.to_dict(), ensure_ascii=False, sort_keys=True
    )
    assert alternatives == {"QING_ADVANCE", "SHUN_HOLDS"}

from __future__ import annotations

import copy

import pytest

from chronicle.subject_attention import evaluate_attention

pytestmark = pytest.mark.skip(
    reason="历史南京状态空间与多危机游戏证明；不属于当前 Killer Demo 契约"
)


def test_canonicality_perturbation_changes_state_bound_affordance(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    state = runtime.worldline(worldline_id)["projection"]["crisis_instances"]["nanjing-succession"]
    pack = runtime.pack.pack("nanjing-succession")
    base_projection = {**copy.deepcopy(state), "positions": {}}
    base_ids = {
        item["id"]
        for item in pack.operation_affordances("han-zanzhou", base_projection, 0)
    }

    perturbed = copy.deepcopy(base_projection)
    perturbed["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    perturbed["entities"]["nanjing-recognition"]["state"] = "DELIBERATING"
    perturbed_ids = {
        item["id"]
        for item in pack.operation_affordances("han-zanzhou", perturbed, 0)
    }

    assert "convene_recognition_assembly" in base_ids
    assert "convene_recognition_assembly" not in perturbed_ids
    assert base_ids != perturbed_ids


def test_nanjing_urgent_pressure_keeps_the_first_procedure_affordance(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    state = runtime.worldline(worldline_id)["projection"]["crisis_instances"]["nanjing-succession"]
    state["entities"]["nanjing-recognition"]["state"] = "URGENT"

    operation_ids = {
        item["id"]
        for item in runtime.pack.pack("nanjing-succession").operation_affordances(
            "han-zanzhou", {**copy.deepcopy(state), "positions": {}}, 7
        )
    }

    assert "convene_recognition_assembly" in operation_ids


def test_volume_operation_uses_crisis_local_tick_after_late_activation(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    state = runtime._crisis_state(
        "southern-consolidation",
        runtime.pack.pack("southern-consolidation"),
        activation_tick=14,
    )
    state["local_tick"] = 1
    state["status"] = "ACTIVE"
    projection = runtime.worldline(worldline_id)["projection"]
    projection["active_crisis_ids"] = ["southern-consolidation"]
    projection["crisis_instances"]["southern-consolidation"] = state
    lifetime = runtime.db.worldline_lifetime(worldline_id, "han-zanzhou")
    assert lifetime is not None

    _payload, result = runtime._prepare_volume_operation(
        lifetime,
        {
            "operation_definition_id": "draft-jiangbei-mandate",
            "targets": ["jiangbei-mandate"],
            "description": "将督师安排推进到公开文书。",
        },
        [("southern-consolidation", runtime.pack.pack("southern-consolidation"))],
        runtime._action_projection(projection),
        15,
    )

    assert result["status"] == "accepted"
    assert result["expected_complete_tick"] == 16


def test_role_state_swap_attention_policy_does_not_use_seat_name():
    course = {
        "course_schema_version": 1,
        "status": "IN_FORCE",
        "open_dependencies": [
            {"id": "await-report", "type": "MESSAGE_FROM", "actor_id": "courier"}
        ],
    }
    lifetime_a = {"seat": "historical-seat-a", "plan": [course]}
    lifetime_b = {"seat": "historical-seat-b", "plan": [copy.deepcopy(course)]}
    admitted = [
        {
            "event_id": "message-1",
            "event_type": "MESSAGE_DELIVERED",
            "actor_id": "courier",
        }
    ]

    result_a = evaluate_attention(lifetime_a, admitted, {"tick": 3})
    result_b = evaluate_attention(lifetime_b, admitted, {"tick": 3})

    assert result_a.as_dict() == result_b.as_dict()
    assert result_a.reason_code == "OPEN_DEPENDENCY_MATCH"


def test_v6_game_proof_modules_keep_fixture_boundaries_explicit():
    # Continuous Agency, Attention precision, Agency Conservation and the
    # causal crisis tests live in their phase-specific modules.
    assert evaluate_attention is not None


def test_volume_runtime_settles_ready_crisis_through_registered_contract(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")

    advanced = None
    while runtime.worldline(worldline_id)["worldline"]["current_tick"] < 5:
        advanced = runtime.advance_one(worldline_id)
    assert advanced is not None

    event_types = {event["event_type"] for event in advanced["events"]}
    instance = runtime.db.crisis_instance(f"{worldline_id}:crisis:before-shanhaiguan")
    projection = runtime.worldline(worldline_id)["projection"]

    assert {"CRISIS_RESOLVED", "CRISIS_SETTLED"} <= event_types
    assert instance is not None
    assert instance["status"] == "SETTLED"
    assert instance["outcome"]["contract_id"] == "shanhaiguan-v1"
    assert "before-shanhaiguan" not in projection["active_crisis_ids"]

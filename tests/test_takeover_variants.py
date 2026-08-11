from __future__ import annotations

from dataclasses import replace

import pytest

from chronicle.crisis_runtime import CrisisRunEngine, RunMode
from chronicle.decision import DecisionOperation, InterpretedDecision

_TAKEOVER_CASES = {
    "li-zicheng": {
        "asset_id": "shun-eastern-force",
        "role_marker": "大顺政权",
        "knowledge_marker": "吴襄及家属",
        "after_prepare": {"move_force"},
        "followup": DecisionOperation(
            tool="operate",
            arguments={
                "operation_definition_id": "move_force",
                "targets": ["shun-eastern-force", "yongping"],
                "description": "向永平调动东向兵力。",
            },
        ),
        "result_wake": "OPERATION_RESULT",
        "result_kind": "position",
    },
    "wu-sangui": {
        "asset_id": "wu-field-force",
        "role_marker": "前明关宁军主将",
        "knowledge_marker": "首封求助信已经发出",
        "after_prepare": {"move_force", "secure-shanhai-pass"},
        "followup": DecisionOperation(
            tool="operate",
            arguments={
                "operation_definition_id": "secure-shanhai-pass",
                "targets": ["wu-field-force", "shanhai-pass"],
                "description": "封闭山海关通道。",
            },
        ),
        "result_wake": "OPERATION_RESULT",
        "result_kind": "pass",
    },
    "dorgon": {
        "asset_id": "qing-expedition-force",
        "role_marker": "清朝摄政王",
        "knowledge_marker": "奉命大将军印",
        "after_prepare": set(),
        "followup": DecisionOperation(
            tool="investigate",
            arguments={
                "question": "查问山海关近况。",
                "target": "shanhai-pass",
                "method": "courier_report",
            },
        ),
        "result_wake": "INVESTIGATION_RESULT",
        "result_kind": "observation",
    },
}


class _SingleOperationInterpreter:
    source = "fixture"

    def __init__(self, summary: str, operation: DecisionOperation):
        self.summary = summary
        self.operation = operation

    def interpret(self, text: str, perspective: dict) -> InterpretedDecision:
        return InterpretedDecision(
            summary=self.summary,
            operations=[self.operation],
        )


def _advance_until(
    engine: CrisisRunEngine,
    run_id: str,
    actor_id: str,
    wake_type: str,
) -> dict:
    for _ in range(8):
        advancement = engine.advance_to_attention(run_id)
        attention = advancement["attention"]
        assert attention is not None
        assert attention["mode"] == "TAKEOVER"
        assert attention["actor_id"] == actor_id
        if any(reason["wake_type"] == wake_type for reason in attention["reasons"]):
            return advancement
        engine.submit_human_decision(run_id, "")
    raise AssertionError(f"{actor_id} did not receive {wake_type}")


@pytest.mark.parametrize("actor_id", _TAKEOVER_CASES)
def test_each_shanhaiguan_takeover_has_a_distinct_world_path(
    app_config, tmp_path, actor_id
):
    case = _TAKEOVER_CASES[actor_id]
    config = replace(
        app_config,
        database_path=tmp_path / f"{actor_id}.db",
        runtime_dir=tmp_path / f"{actor_id}-runtime",
        hermes_home=tmp_path / f"{actor_id}-hermes-home",
    )
    engine = CrisisRunEngine(config)
    created = engine.create(RunMode.TAKEOVER, human_actor_id=actor_id)
    run_id = created["run"]["id"]

    assert engine.advance_to_attention(run_id)["attention"] == {
        "mode": "TAKEOVER",
        "actor_id": actor_id,
        "tick": 0,
        "reasons": [{"wake_type": "INITIAL_DECISION", "trigger_event_id": ""}],
    }
    assert created["run"]["controller_map"] == {
        candidate: "HUMAN" if candidate == actor_id else "AGENT"
        for candidate in _TAKEOVER_CASES
    }
    lifetimes = engine.db.worldline_lifetimes(run_id)
    assert engine.db.worldline_lifetime(run_id, actor_id)["profile_name"] == ""
    assert {
        lifetime["seat"]
        for lifetime in lifetimes
        if lifetime["profile_name"]
    } == set(_TAKEOVER_CASES) - {actor_id}
    assert {binding["role"] for binding in engine.db.agent_bindings(run_id)} == (
        set(_TAKEOVER_CASES) - {actor_id}
    )

    initial = engine.product_perspective(run_id, actor_id)
    assert case["role_marker"] in initial["role_charter"]["who"]
    assert case["knowledge_marker"] in "\n".join(initial["knowledge"])
    assert {asset["id"] for asset in initial["own_assets"]} >= {case["asset_id"]}
    assert {operation["id"] for operation in initial["available_operations"]} == {
        "prepare_force"
    }

    prepare = DecisionOperation(
        tool="operate",
        arguments={
            "operation_definition_id": "prepare_force",
            "targets": [case["asset_id"]],
            "description": "先整备自己的可用兵力。",
        },
    )
    engine.submit_human_decision(
        run_id,
        "先整备兵力。",
        interpreter=_SingleOperationInterpreter("整备自有兵力。", prepare),
    )
    _advance_until(engine, run_id, actor_id, "OPERATION_RESULT")

    projection = engine.db.worldline_snapshot(run_id)["projection"]
    completed = next(
        event
        for event in engine.db.worldline_events(run_id)
        if event["event_type"] == "OPERATION_COMPLETED"
        and event["seat_id"] == actor_id
        and event["payload"]["operation"]["definition_id"] == "prepare_force"
    )
    assert completed["payload"]["visibility"] == [actor_id]
    assert projection["entities"][case["asset_id"]]["state"] == "READY"
    prepared = engine.product_perspective(run_id, actor_id)
    assert {operation["id"] for operation in prepared["available_operations"]} == case[
        "after_prepare"
    ]

    engine.submit_human_decision(
        run_id,
        "继续执行下一步。",
        interpreter=_SingleOperationInterpreter("执行角色特有的下一步。", case["followup"]),
    )
    _advance_until(engine, run_id, actor_id, case["result_wake"])

    projection = engine.db.worldline_snapshot(run_id)["projection"]
    if case["result_kind"] == "position":
        assert projection["positions"][actor_id] == "yongping"
        assert projection["entities"][case["asset_id"]]["state"] == "COMMITTED"
    elif case["result_kind"] == "pass":
        assert projection["entities"]["shanhai-pass"]["state"] == "CLOSED"
    else:
        observation = next(
            event
            for event in engine.db.worldline_events(run_id)
            if event["event_type"] == "OBSERVATION_OBTAINED"
            and event["seat_id"] == actor_id
        )
        assert observation["payload"]["visibility"] == [actor_id]
        assert any(
            item.get("kind") == "observation"
            for item in engine.db.worldline_lifetime(run_id, actor_id)["knowledge"]
            if isinstance(item, dict)
        )

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from chronicle.crisis_runtime import CrisisRunConflict, CrisisRunEngine, RunMode
from chronicle.decision import (
    DecisionOperation,
    FixtureDecisionInterpreter,
    InterpretedDecision,
    ModelDecisionInterpreter,
)


def test_model_decision_interpreter_returns_multiple_semantic_operations(
    app_config, monkeypatch
):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="private-provider-key",
        llm_model="decision-model",
    )
    request: dict[str, object] = {}
    output = {
        "summary": "先通信，再安排复查。",
        "operations": [
            {
                "tool": "communicate",
                "arguments": {"recipient": "dorgon", "content": "请说明出兵条件。"},
            },
            {
                "tool": "schedule_followup",
                "arguments": {"after_days": 2, "purpose": "比较回信与实际动向"},
            },
        ],
    }

    def fake_post(url, **kwargs):
        request.update({"url": url, **kwargs})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]
            },
        )

    monkeypatch.setattr("chronicle.decision.httpx.post", fake_post)
    result = ModelDecisionInterpreter(configured).interpret(
        "先问关外的条件，两日后重估。",
        {"actor_id": "wu-sangui", "knowledge": []},
    )

    assert [operation.tool for operation in result.operations] == [
        "communicate",
        "schedule_followup",
    ]
    assert request["url"] == "https://provider.example/v1/chat/completions"
    assert request["trust_env"] is False
    assert "private-provider-key" not in json.dumps(request["json"], ensure_ascii=False)


def test_takeover_human_multi_action_and_silence_use_the_shared_world_service(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    decision = engine.submit_human_decision(
        run_id,
        "向关外说明条件，并在两日后重新比较。",
        interpreter=FixtureDecisionInterpreter(),
    )
    silence = engine.submit_human_decision(run_id, "")
    result = engine.run_until_idle(run_id)

    assert decision["silence"] is False
    assert [operation["status"] for operation in decision["operations"]] == [
        "COMMITTED",
        "COMMITTED",
        "COMMITTED",
    ]
    assert silence["silence"] is True
    assert any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        and event["seat_id"] == "wu-sangui"
        for event in result["events"]
    )
    assert any(event["event_type"] == "HUMAN_INTERRUPTION_READY" for event in result["events"])
    decision_event = next(
        event for event in result["events"] if event["event_type"] == "HUMAN_DECISION_APPLIED"
    )
    decision_index = result["events"].index(decision_event)
    human_effects = [
        event
        for event in result["events"][decision_index + 1 :]
        if event["seat_id"] == "wu-sangui"
        and event["event_type"] in {"PLAN_UPDATED", "MESSAGE_DISPATCHED", "COMMITMENT_SCHEDULED"}
    ]
    assert human_effects[0]["causal_parent_ids"] == [decision_event["id"]]
    assert all(
        current["causal_parent_ids"] == [previous["id"]]
        for previous, current in zip(human_effects, human_effects[1:], strict=False)
    )
    lifetime = engine.db.worldline_lifetime(run_id, "wu-sangui")
    assert lifetime["plan"][0]["objective"].startswith("向关外")
    assert any(commitment["status"] == "DUE" for commitment in lifetime["commitments"])


def test_repeated_human_decision_same_tick_is_a_controlled_conflict(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    engine.submit_human_decision(
        run_id,
        "向关外说明条件，并在两日后重新比较。",
        interpreter=FixtureDecisionInterpreter(),
    )

    with pytest.raises(CrisisRunConflict, match="当前模拟日已经提交过决定"):
        engine.submit_human_decision(
            run_id,
            "再次提交同一模拟日的决定。",
            interpreter=FixtureDecisionInterpreter(),
        )

    decisions = [
        wake
        for wake in engine.db.crisis_wakes(run_id, tick=0)
        if wake["actor_id"] == "wu-sangui" and wake["wake_type"] == "DECISION"
    ]
    assert len(decisions) == 1


def test_human_desk_persists_known_state_outbox_decisions_and_resolves_due_matters(
    app_config,
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    initial = engine.product_perspective(run_id, "wu-sangui")
    assert initial["known_situation"]
    assert any(message["recipient"] == "dorgon" for message in initial["outgoing_messages"])

    engine.submit_human_decision(
        run_id,
        "向关外说明条件，并在两日后重新比较。",
        interpreter=FixtureDecisionInterpreter(),
    )
    engine.run_until_idle(run_id)
    due = engine.product_perspective(run_id, "wu-sangui")
    assert any(commitment["status"] == "DUE" for commitment in due["commitments"])
    assert due["decisions"][-1]["summary"]

    silence = engine.submit_human_decision(run_id, "")
    resolved = engine.product_perspective(run_id, "wu-sangui")

    assert any(commitment["status"] == "FULFILLED" for commitment in resolved["commitments"])
    assert resolved["decisions"][-1]["summary"] == "暂不追加命令，继续观察。"
    assert any(event["event_type"] == "COMMITMENT_FULFILLED" for event in silence["events"])


def test_invalid_later_human_operation_leaves_no_partial_world_commit(app_config):
    class InvalidInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            return InterpretedDecision(
                summary="含一个非法越权参数。",
                operations=[
                    DecisionOperation(
                        tool="communicate",
                        arguments={"recipient": "dorgon", "content": "合法的第一项"},
                    ),
                    DecisionOperation(
                        tool="act",
                        arguments={
                            "action": "hold",
                            "description": "非法携带身份",
                            "actor_id": "li-zicheng",
                        },
                    ),
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]
    before = engine.db.worldline_snapshot(run_id)["projection"]

    with pytest.raises(Exception, match="safely applied"):
        engine.submit_human_decision(
            run_id,
            "尝试越权",
            interpreter=InvalidInterpreter(),
        )

    after = engine.db.worldline_snapshot(run_id)["projection"]
    assert after == before
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "human"
        for event in engine.db.worldline_events(run_id)
    )

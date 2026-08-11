from __future__ import annotations

import inspect
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
                "tool": "schedule_revisit",
                "arguments": {"after_days": 2, "reason": "比较回信与实际动向"},
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
        "schedule_revisit",
    ]
    assert request["url"] == "https://provider.example/v1/chat/completions"
    assert request["trust_env"] is False
    assert "private-provider-key" not in json.dumps(request["json"], ensure_ascii=False)


def test_model_decision_interpreter_includes_canonical_recipient_catalog(
    app_config, monkeypatch
):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="private-provider-key",
        llm_model="decision-model",
    )
    request: dict[str, object] = {}

    def fake_post(url, **kwargs):
        request.update({"url": url, **kwargs})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"summary": "已登记。", "operations": []},
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("chronicle.decision.httpx.post", fake_post)
    ModelDecisionInterpreter(
        configured,
        recipient_catalog=(
            {"id": "li-zicheng", "display_name": "李自成"},
            {"id": "dorgon", "display_name": "多尔衮"},
        ),
    ).interpret("分别致信两方。", {"actor_id": "wu-sangui"})

    system_prompt = request["json"]["messages"][0]["content"]
    assert "li-zicheng" in system_prompt
    assert "dorgon" in system_prompt
    assert "不得使用显示名或别名" in system_prompt


def test_fixture_decision_interpreter_creates_an_offer_only_for_explicit_passage_language():
    result = FixtureDecisionInterpreter().interpret(
        "愿按约定条件允许清军通行。",
        {
            "available_offer_terms": [
                {
                    "type": "passage",
                    "subject": {"id": "shanhai-pass", "display_name": "山海关通道"},
                    "value": "permitted",
                    "description": "允许清军按约定条件通过山海关通道。",
                    "recipient": {"id": "dorgon", "display_name": "多尔衮"},
                }
            ]
        },
    )

    offer = next(operation for operation in result.operations if operation.tool == "manage_offer")
    assert offer.arguments["action"] == "PROPOSE"
    assert offer.arguments["recipient"] == "dorgon"
    assert offer.arguments["terms"][0]["subject"] == "shanhai-pass"


def test_fixture_decision_interpreter_uses_the_perspective_manifest_not_historical_ids():
    source = inspect.getsource(FixtureDecisionInterpreter)
    assert all(
        actor_id not in source
        for actor_id in (
            "li-zicheng",
            "wu-sangui",
            "dorgon",
            "shi-kefa",
            "ma-shiying",
            "han-zanzhou",
        )
    )

    result = FixtureDecisionInterpreter().interpret(
        "请致信说明条件，并在两日后重新判断。",
        {
            "contactable_actors": [
                {"id": "actor-b"},
                {"id": "actor-a"},
            ]
        },
    )

    assert [operation.tool for operation in result.operations] == [
        "update_plan",
        "communicate",
        "schedule_revisit",
    ]
    assert result.operations[1].arguments["recipient"] == "actor-a"


def test_takeover_human_multi_action_and_silence_use_the_shared_world_service(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    decision = engine.submit_human_decision(
        run_id,
        "向关外说明条件，并在两日后重新比较。",
        interpreter=FixtureDecisionInterpreter(),
    )
    result = engine.run_until_idle(run_id)

    assert decision["silence"] is False
    assert [operation["status"] for operation in decision["operations"]] == [
        "COMMITTED",
        "COMMITTED",
        "COMMITTED",
    ]
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
        and event["event_type"] in {"PLAN_UPDATED", "MESSAGE_DISPATCHED", "REVISIT_SCHEDULED"}
    ]
    assert human_effects[0]["causal_parent_ids"] == [decision_event["id"]]
    assert all(
        current["causal_parent_ids"] == [previous["id"]]
        for previous, current in zip(human_effects, human_effects[1:], strict=False)
    )
    lifetime = engine.db.worldline_lifetime(run_id, "wu-sangui")
    assert lifetime["plan"][0]["objective"].startswith("向关外")
    assert any(
        revisit["actor_id"] == "wu-sangui"
        and revisit["reason"] == "两日后重新判断已知条件"
        and revisit["status"] == "DUE"
        for revisit in lifetime["revisits"]
    )
    revisit_id = next(revisit["id"] for revisit in lifetime["revisits"])
    silence = engine.submit_human_decision(run_id, "")
    assert silence["silence"] is True
    events = engine.db.worldline_events(run_id)
    scheduled = next(
        event
        for event in events
        if event["event_type"] == "REVISIT_SCHEDULED"
        and event["payload"]["revisit"]["id"] == revisit_id
    )
    due = next(
        event
        for event in events
        if event["event_type"] == "REVISIT_DUE"
        and event["payload"]["revisit_id"] == revisit_id
    )
    fulfilled = next(
        event
        for event in events
        if event["event_type"] == "REVISIT_FULFILLED"
        and event["payload"]["revisit_id"] == revisit_id
    )
    silence_event = next(event for event in events if event["event_type"] == "HUMAN_SILENCE")
    assert due["causal_parent_ids"] == [scheduled["id"]]
    assert fulfilled["causal_parent_ids"] == [due["id"], silence_event["id"]]


def test_product_perspective_keeps_human_operation_outcomes(app_config):
    class PartialInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            return InterpretedDecision(
                summary="分别致信两方。",
                operations=[
                    DecisionOperation(
                        tool="communicate",
                        arguments={"recipient": "dorgon", "content": "给多尔衮的信"},
                    ),
                    DecisionOperation(
                        tool="communicate",
                        arguments={"recipient": "duoergun", "content": "给别名收件人的信"},
                    ),
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]
    engine.submit_human_decision(run_id, "分别致信两方。", interpreter=PartialInterpreter())

    decision = engine.product_perspective(run_id, "wu-sangui")["decisions"][-1]
    assert decision["summary"] == "分别致信两方。"
    assert decision["operation_results"] == [
        {
            "tool": "communicate",
            "status": "COMMITTED",
            "recipient": "多尔衮",
            "arrival_tick": 2,
        },
        {
            "tool": "communicate",
            "status": "REJECTED",
            "recipient": "未识别收件人",
            "reason": "收件人无法识别",
        },
    ]


def test_human_decision_conflicts_expose_machine_state(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]
    snapshot = engine.db.worldline_snapshot(run_id)

    running = engine.db.create_crisis_wake(
        {
            "worldline_id": run_id,
            "actor_id": "wu-sangui",
            "wake_type": "DECISION",
            "tick": 0,
            "status": "RUNNING",
            "source": "human",
            "frozen_perspective": snapshot["projection"],
        }
    )
    with pytest.raises(CrisisRunConflict) as running_error:
        engine.submit_human_decision(run_id, "仍在处理的重复提交")
    assert running_error.value.code == "decision_in_progress"
    assert running_error.value.state == "RUNNING"
    assert running_error.value.tick == 0

    engine.db.update_crisis_wake(running["id"], status="FAILED")
    with pytest.raises(CrisisRunConflict) as failed_error:
        engine.submit_human_decision(run_id, "失败后的重复提交")
    assert failed_error.value.code == "decision_failed"
    assert failed_error.value.state == "FAILED"
    assert engine.run_summary(run_id)["human_decision"]["state"] == "FAILED"


def test_human_silence_is_the_same_single_decision_slot(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    assert engine.run_summary(run_id)["can_continue"] is True
    silence = engine.submit_human_decision(run_id, "")

    assert silence["silence"] is True
    assert engine.run_summary(run_id)["human_decision"] == {
        "state": "COMMITTED",
        "kind": "silence",
        "tick": 0,
    }
    with pytest.raises(CrisisRunConflict) as duplicate:
        engine.submit_human_decision(run_id, "同一日不应再写第二笔")
    assert duplicate.value.code == "decision_already_exists"


def test_run_summary_marks_sealed_run_as_not_continuable(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    assert engine.run_summary(run_id)["can_continue"] is True
    engine.seal(run_id)
    assert engine.run_summary(run_id)["can_continue"] is False


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
    assert any(revisit["status"] == "DUE" for revisit in due["revisits"])
    assert CrisisRunEngine(app_config).product_perspective(run_id, "wu-sangui")[
        "current_revisits"
    ] == due["revisits"]
    assert due["decisions"][-1]["summary"]

    silence = engine.submit_human_decision(run_id, "")
    resolved = engine.product_perspective(run_id, "wu-sangui")

    assert any(revisit["status"] == "FULFILLED" for revisit in resolved["revisits"])
    assert resolved["decisions"][-1]["summary"] == "暂不追加命令，继续观察。"
    assert any(event["event_type"] == "REVISIT_FULFILLED" for event in silence["events"])


def test_human_operation_persists_then_changes_a_later_available_action(app_config):
    class PrepareInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            assert {item["id"] for item in perspective["available_operations"]} == {
                "prepare_force"
            }
            return InterpretedDecision(
                summary="先整备关宁所部。",
                operations=[
                    DecisionOperation(
                        tool="operate",
                        arguments={
                            "operation_definition_id": "prepare_force",
                            "targets": ["wu-field-force"],
                            "description": "开始整备关宁所部。",
                        },
                    )
                ],
            )

    class MoveInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            assert perspective["active_operations"] == []
            assert {item["id"] for item in perspective["available_operations"]} == {
                "move_force",
                "secure-shanhai-pass",
            }
            return InterpretedDecision(
                summary="向永平调动所部。",
                operations=[
                    DecisionOperation(
                        tool="operate",
                        arguments={
                            "operation_definition_id": "move_force",
                            "targets": ["wu-field-force", "yongping"],
                            "description": "向永平调动已整备所部。",
                        },
                    )
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    started = engine.submit_human_decision(run_id, "先整备兵力", interpreter=PrepareInterpreter())
    assert started["operations"][0]["status"] == "COMMITTED"
    restarted = CrisisRunEngine(app_config)
    assert restarted.product_perspective(run_id, "wu-sangui")["active_operations"][0][
        "status"
    ] == "IN_PROGRESS"

    while (
        restarted.db.worldline_snapshot(run_id)["projection"]["operations"][0]["status"]
        != "COMPLETED"
    ):
        assert restarted.advance_one(run_id) is True
    resumed = restarted.product_perspective(run_id, "wu-sangui")

    assert resumed["own_assets"][0]["id"] == "wu-field-force"
    assert resumed["own_assets"][0]["state"] == "READY"
    assert {item["id"] for item in resumed["available_operations"]} == {
        "move_force",
        "secure-shanhai-pass",
    }
    moved = restarted.submit_human_decision(run_id, "向永平调动", interpreter=MoveInterpreter())
    assert moved["operations"][0]["status"] == "COMMITTED"


def test_human_investigation_survives_restart_until_a_sourced_observation(app_config):
    class InvestigationInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            assert perspective["available_investigations"] == [
                {
                    "id": "shanhai-pass-report",
                    "display_name": "查问山海关近况",
                    "description": "派出沿线使者核实关口控制与可见兵力态势；不能探知尚未公开的私下条件。",
                    "target": {
                        "id": "shanhai-pass",
                        "type": "ASSET",
                        "display_name": "山海关通道",
                    },
                    "method": "courier_report",
                    "duration_days": 2,
                    "expected_result_tick": 2,
                }
            ]
            return InterpretedDecision(
                summary="先核实关口可见态势。",
                operations=[
                    DecisionOperation(
                        tool="investigate",
                        arguments={
                            "question": "山海关是否已有可核验的公开通行安排？",
                            "target": "shanhai-pass",
                            "method": "courier_report",
                        },
                    )
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    started = engine.submit_human_decision(
        run_id,
        "先查问山海关近况。",
        interpreter=InvestigationInterpreter(),
    )
    operation = started["operations"][0]
    assert operation["tool_name"] == "investigate"
    assert operation["status"] == "COMMITTED"
    assert operation["payload"]["target"] == "shanhai-pass"
    assert operation["result"]["expected_result_tick"] == 2

    restarted = CrisisRunEngine(app_config)
    in_progress = restarted.product_perspective(run_id, "wu-sangui")
    assert in_progress["active_investigations"][0]["status"] == "IN_PROGRESS"
    assert in_progress["active_investigations"][0]["expected_result_tick"] == 2
    assert not any(
        isinstance(item, dict) and item.get("investigation_id")
        for item in in_progress["knowledge"]
    )

    result = restarted.run_until_idle(run_id)
    recovered = CrisisRunEngine(app_config).product_perspective(run_id, "wu-sangui")
    observation = next(
        item
        for item in recovered["knowledge"]
        if isinstance(item, dict) and item.get("investigation_id")
    )

    assert recovered["active_investigations"] == []
    assert observation["source"] == "沿线来人与关口往来文书的交叉转述"
    assert observation["source_ids"] == ["qing-shilu-shizu-4", "mingji-beilue-20"]
    assert observation["reliability"] == "MEDIUM"
    assert observation["related_assertions"] == ["c002", "c012"]
    assert any(
        item.get("source") == observation["source"] and item.get("reliability") == "MEDIUM"
        for item in recovered["known_situation"]
    )
    assert any(
        wake["actor_id"] == "wu-sangui"
        and wake["wake_type"] == "INVESTIGATION_RESULT"
        and wake["status"] == "COMPLETED"
        for wake in result["wakes"]
    )


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
                        tool="operate",
                        arguments={
                            "operation_definition_id": "prepare_force",
                            "targets": ["wu-field-force"],
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

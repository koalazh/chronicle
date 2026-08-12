from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.db import content_hash
from chronicle.decision import (
    DecisionOperation,
    InterpretedDecision,
    guard_human_interpretation,
)
from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntimeConflict


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / suffix,
        hermes_home=app_config.hermes_home / suffix,
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert wu is not None and dorgon is not None
    host.worldline_runtime.inhabit(worldline_id, wu["id"])
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:wake:dorgon:phase8",
            "worldline_id": worldline_id,
            "actor_id": dorgon["id"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "phase8-test",
            "trigger_event_id": f"{worldline_id}:trigger:dorgon:phase8",
        }
    )
    return runtime, worldline_id, wu, dorgon


def test_lifetime_context_is_bounded_and_actor_scoped(app_config):
    runtime, worldline_id, wu, _dorgon = _runtime(app_config, "context")
    knowledge = [
        {"message_id": f"old-{index}", "content": f"old knowledge {index}"} for index in range(20)
    ]
    beliefs = {
        f"belief-{index}": {
            "assessment": f"assessment {index}",
            "confidence": "medium",
            "updated_tick": 0,
            "evidence_event_ids": [],
        }
        for index in range(12)
    }
    memory_text = "\n".join(f"memory line {index}" for index in range(12))
    runtime.db.update_worldline_lifetime(
        worldline_id,
        wu["seat"],
        knowledge_json=json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
        belief_json=json.dumps(beliefs, ensure_ascii=False, sort_keys=True),
        memory_text=memory_text,
        memory_hash=content_hash(memory_text),
    )

    frozen = runtime.freeze_pending_moment(worldline_id)
    context = frozen["pending_moment"]
    wake = runtime.db.crisis_wake(context["wake_ids"][0])
    assert wake is not None
    perspective = wake["frozen_perspective"]
    bounded = perspective["context"]

    assert "world" not in perspective
    assert bounded["position"]["id"] == "shanhaiguan"
    assert bounded["resources"]["pass_control"] == "contested-but-held"
    assert bounded["active_crisis_context"][0]["crisis_id"] == "before-shanhaiguan"
    assert len(bounded["beliefs"]) <= 8
    assert len(bounded["recent_knowledge"]) <= 6
    assert len(bounded["subjective_memory"]["selected_lines"]) <= 6
    assert all(item["message_id"].startswith("old-") for item in bounded["recent_knowledge"])


def test_human_interpretation_does_not_infer_reason_or_belief():
    decision = InterpretedDecision(
        summary="已决定。",
        operations=[
            DecisionOperation(
                tool="update_plan",
                arguments={
                    "objective": "执行",
                    "steps": ["执行"],
                    "rationale": "因为他值得信任",
                    "belief_updates": [
                        {
                            "subject": "peer:dorgon",
                            "assessment": "对方可信",
                            "confidence": "high",
                        }
                    ],
                },
            )
        ],
    )

    guarded = guard_human_interpretation("直接执行", decision)

    assert guarded.operations[0].arguments["rationale"] == ""
    assert guarded.operations[0].arguments["rationale_source"] == "unstated"
    assert guarded.operations[0].arguments["belief_updates"] == []
    assert guarded.operations[0].arguments["belief_source"] == "unstated"


def test_evidence_backed_expectation_requires_human_provenance(app_config):
    runtime, worldline_id, wu, dorgon = _runtime(app_config, "belief")
    frozen = runtime.freeze_pending_moment(worldline_id)
    wu_wake_id = next(
        wake_id
        for wake_id in frozen["pending_moment"]["wake_ids"]
        if runtime.db.crisis_wake(wake_id)["actor_id"] in {wu["id"], wu["seat"]}
    )
    trigger_event_id = runtime.db.crisis_wake(wu_wake_id)["trigger_event_id"]

    with pytest.raises(VolumeRuntimeConflict, match="Human rationale"):
        runtime.stage_intent(
            worldline_id,
            wu["id"],
            {
                "type": "update_plan",
                "objective": "判断是否回应",
                "steps": ["等待更多证据"],
                "rationale": "因为对方值得信任",
                "belief_updates": [],
            },
            source="human",
        )

    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "判断是否回应",
            "steps": ["等待更多证据"],
            "rationale": "",
            "rationale_source": "unstated",
            "belief_source": "explicit",
            "belief_updates": [
                {
                    "subject": "peer:dorgon",
                    "assessment": "对方的承诺仍需通过后续行动验证。",
                    "confidence": "medium",
                    "evidence_event_ids": [trigger_event_id],
                }
            ],
        },
        source="human",
    )
    runtime.stage_intent(
        worldline_id,
        dorgon["id"],
        {"type": "wait"},
        source="agent",
    )
    runtime.commit_pending_moment(worldline_id)

    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None
    expectation = lifetime["beliefs"]["peer:dorgon"]
    assert expectation["updated_tick"] == 1
    assert expectation["evidence_event_ids"] == [trigger_event_id]
    assert lifetime["plan"][0]["rationale"] == ""


def test_later_action_trace_reuses_expectation_and_selective_memory(app_config):
    runtime, worldline_id, wu, dorgon = _runtime(app_config, "trace")
    memory_text = "旧判断：短期承诺必须等待行动验证。\n不相关：远方天气。"
    runtime.db.update_worldline_lifetime(
        worldline_id,
        wu["seat"],
        memory_text=memory_text,
        memory_hash=content_hash(memory_text),
    )
    first = runtime.freeze_pending_moment(worldline_id)
    wu_wake = next(
        runtime.db.crisis_wake(wake_id)
        for wake_id in first["pending_moment"]["wake_ids"]
        if runtime.db.crisis_wake(wake_id)["actor_id"] in {wu["id"], wu["seat"]}
    )
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "等待行动验证",
            "steps": ["保留核验选项"],
            "rationale": "",
            "rationale_source": "unstated",
            "belief_source": "explicit",
            "belief_updates": [
                {
                    "subject": "peer:dorgon",
                    "assessment": "短期承诺仍需行动验证。",
                    "confidence": "medium",
                    "evidence_event_ids": [wu_wake["trigger_event_id"]],
                }
            ],
        },
        source="human",
    )
    runtime.stage_intent(worldline_id, dorgon["id"], {"type": "wait"}, source="agent")
    runtime.commit_pending_moment(worldline_id)

    second_wake = runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:wake:wu:follow-up",
            "worldline_id": worldline_id,
            "actor_id": wu["id"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "WAITING_HUMAN",
            "source": "phase8-test",
            "trigger_event_id": f"{worldline_id}:follow-up-trigger",
        }
    )
    runtime.freeze_pending_moment(worldline_id)
    staged = runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "message",
            "recipient": "dorgon",
            "content": "请以行动证明承诺。",
            "delivery_tick": 3,
            "belief_keys": ["peer:dorgon"],
        },
        source="human",
    )
    runtime.commit_pending_moment(worldline_id)
    message_event = next(
        event
        for event in reversed(runtime.db.worldline_events(worldline_id))
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "logical_moment"
    )
    trace = runtime.causal_trace(worldline_id, message_event["id"])
    context = runtime.lifetime_context(worldline_id, wu["id"], wake_id=second_wake["id"])

    assert staged["operation"]["payload"]["intent"]["belief_keys"] == ["peer:dorgon"]
    assert trace["controller"] == "human"
    assert trace["current_expectation"]["payload"]["belief_key"] == "peer:dorgon"
    assert trace["evidence_event_ids"]
    assert trace["earlier_episode"]
    assert "短期承诺必须等待行动验证" in context["subjective_memory"]["text"]

    assert (
        TestClient(create_app(runtime.host.config))
        .get(f"/api/dev/worldlines/{worldline_id}/why/{message_event['id']}")
        .status_code
        == 404
    )
    dev_client = TestClient(create_app(replace(runtime.host.config, dev=True)))
    response = dev_client.get(f"/api/dev/worldlines/{worldline_id}/why/{message_event['id']}")
    assert response.status_code == 200
    assert response.json()["controller"] == "human"


def test_memory_ablation_paired_fixture_changes_bounded_future_action(app_config):
    with_memory, with_worldline, with_wu, with_dorgon = _runtime(
        app_config, "memory-ablation-with"
    )
    without_memory, without_worldline, without_wu, without_dorgon = _runtime(
        app_config, "memory-ablation-without"
    )
    relevant_line = "上一轮：多尔衮的承诺必须等实际行动验证。"
    for runtime, worldline_id, wu in (
        (with_memory, with_worldline, with_wu),
        (without_memory, without_worldline, without_wu),
    ):
        memory_text = f"{relevant_line}\n不相关：远方天气。" if runtime is with_memory else "不相关：远方天气。"
        runtime.db.update_worldline_lifetime(
            worldline_id,
            wu["seat"],
            memory_text=memory_text,
            memory_hash=content_hash(memory_text),
        )

    perspectives = []
    for runtime, worldline_id, wu in (
        (with_memory, with_worldline, with_wu),
        (without_memory, without_worldline, without_wu),
    ):
        runtime.freeze_pending_moment(worldline_id)
        wake = next(
            runtime.db.crisis_wake(wake_id)
            for wake_id in runtime.worldline(worldline_id)["projection"]["pending_moment"]["wake_ids"]
            if runtime.db.crisis_wake(wake_id)["actor_id"] in {wu["id"], wu["seat"]}
        )
        perspectives.append(wake["frozen_perspective"])

    assert relevant_line in perspectives[0]["context"]["subjective_memory"]["text"]
    assert relevant_line not in perspectives[1]["context"]["subjective_memory"]["text"]

    def ablated_policy(perspective: dict[str, object]) -> dict[str, object]:
        memory = str(perspective["context"]["subjective_memory"]["text"])
        if relevant_line in memory:
            return {
                "type": "message",
                "recipient": "dorgon",
                "content": "请以行动证明承诺。",
                "delivery_tick": 3,
            }
        return {
            "type": "update_plan",
            "objective": "重新核验承诺",
            "steps": ["等待新的可见行动"],
            "rationale": "",
            "rationale_source": "unstated",
        }

    with_memory.stage_intent(
        with_worldline,
        with_wu["id"],
        ablated_policy(perspectives[0]),
        source="human",
    )
    with_memory.stage_intent(
        with_worldline, with_dorgon["id"], {"type": "wait"}, source="agent"
    )
    without_memory.stage_intent(
        without_worldline,
        without_wu["id"],
        ablated_policy(perspectives[1]),
        source="human",
    )
    without_memory.stage_intent(
        without_worldline, without_dorgon["id"], {"type": "wait"}, source="agent"
    )
    with_memory.commit_pending_moment(with_worldline)
    without_memory.commit_pending_moment(without_worldline)

    def wu_intent(runtime, worldline_id):
        return next(
            event["payload"]["intent"]
            for event in runtime.db.worldline_events(worldline_id)
            if event["event_type"] == "INTENT_COMMITTED" and event["seat_id"] == "wu-sangui"
        )

    with_intent = wu_intent(with_memory, with_worldline)
    without_intent = wu_intent(without_memory, without_worldline)
    assert with_intent["type"] == "message"
    assert without_intent["type"] == "update_plan"
    assert copy.deepcopy(with_intent) != copy.deepcopy(without_intent)


def test_single_agent_impostor_cannot_merge_private_lifetime_context(app_config):
    runtime, worldline_id, wu, dorgon = _runtime(app_config, "impostor-boundary")
    wu_memory = "吴三桂私下记录：关口承诺必须等行动验证。"
    dorgon_memory = "多尔衮私下记录：西征路线不能让关内来信决定。"
    runtime.db.update_worldline_lifetime(
        worldline_id,
        wu["seat"],
        memory_text=wu_memory,
        memory_hash=content_hash(wu_memory),
    )
    runtime.db.update_worldline_lifetime(
        worldline_id,
        dorgon["seat"],
        memory_text=dorgon_memory,
        memory_hash=content_hash(dorgon_memory),
    )

    frozen = runtime.freeze_pending_moment(worldline_id)
    perspectives = {
        str(runtime.db.crisis_wake(wake_id)["actor_id"]): runtime.db.crisis_wake(wake_id)[
            "frozen_perspective"
        ]
        for wake_id in frozen["pending_moment"]["wake_ids"]
    }

    wu_perspective = next(
        perspective
        for actor_id, perspective in perspectives.items()
        if actor_id in {wu["id"], wu["seat"]}
    )
    dorgon_perspective = next(
        perspective
        for actor_id, perspective in perspectives.items()
        if actor_id in {dorgon["id"], dorgon["seat"]}
    )
    wu_context = wu_perspective["context"]
    dorgon_context = dorgon_perspective["context"]
    assert wu_memory in wu_context["subjective_memory"]["text"]
    assert dorgon_memory not in wu_context["subjective_memory"]["text"]
    assert dorgon_memory in dorgon_context["subjective_memory"]["text"]
    assert wu_memory not in dorgon_context["subjective_memory"]["text"]

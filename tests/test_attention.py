from __future__ import annotations

import json

from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
from chronicle.decision import DecisionOperation, InterpretedDecision


class PlanOnlyDriver:
    source = "fixture"

    def run_wake(self, actor_id, wake, perspective, world):
        if wake["wake_type"] == "ORIENT":
            world.update_plan(
                f"维持{actor_id}的当前判断",
                ["等待新的世界变化"],
                rationale="这项私有计划用于验证 Watch 不会把 Plan churn 当作产品停点。",
                idempotency_key=f"{wake['id']}:plan",
            )
        return ActorTurnResult("保持当前判断。")


def test_takeover_attention_requires_the_initial_human_decision(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER, human_actor_id="li-zicheng")["run"]["id"]

    advancement = engine.advance_to_attention(run_id)

    assert advancement == {
        "advanced": False,
        "attention": {
            "mode": "TAKEOVER",
            "actor_id": "li-zicheng",
            "tick": 0,
            "reasons": [{"wake_type": "INITIAL_DECISION", "trigger_event_id": ""}],
        },
        "moments": 0,
        "from_tick": 0,
        "to_tick": 0,
    }
    assert engine.db.worldline(run_id)["current_tick"] == 0


def test_takeover_attention_skips_agent_private_work_until_a_human_message(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER, human_actor_id="wu-sangui")["run"]["id"]
    engine.submit_human_decision(run_id, "")

    advancement = engine.advance_to_attention(run_id)
    events = engine.db.worldline_events(run_id)
    human_interruptions = [
        event
        for event in events
        if event["event_type"] == "HUMAN_INTERRUPTION_READY"
        and event["seat_id"] == "wu-sangui"
    ]

    assert advancement["advanced"] is True
    assert advancement["moments"] >= 3
    assert advancement["from_tick"] == 0
    assert advancement["to_tick"] == 1
    assert len(human_interruptions) == 1
    assert advancement["attention"] == {
        "mode": "TAKEOVER",
        "actor_id": "wu-sangui",
        "tick": 1,
        "reasons": [
            {
                "wake_type": "MESSAGE",
                "trigger_event_id": human_interruptions[0]["payload"]["trigger_event_id"],
            }
        ],
    }
    assert any(
        event["event_type"] == "PLAN_UPDATED" and event["seat_id"] == "dorgon"
        for event in events
    )
    assert "保持西进行动自由并核验关内局势" not in json.dumps(
        engine.actor_perspective(run_id, "wu-sangui"), ensure_ascii=False
    )


def test_takeover_attention_reports_a_completed_human_operation(app_config):
    class PrepareInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            return InterpretedDecision(
                summary="先整备大顺东向兵力。",
                operations=[
                    DecisionOperation(
                        tool="operate",
                        arguments={
                            "operation_definition_id": "prepare_force",
                            "targets": ["shun-eastern-force"],
                            "description": "开始整备东向兵力。",
                        },
                    )
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER, human_actor_id="li-zicheng")["run"]["id"]
    engine.submit_human_decision(run_id, "先整备兵力", interpreter=PrepareInterpreter())

    advancement = engine.advance_to_attention(run_id)
    operation = engine.db.worldline_snapshot(run_id)["projection"]["operations"][0]

    assert advancement["advanced"] is True
    assert advancement["to_tick"] == 2
    assert advancement["attention"]["actor_id"] == "li-zicheng"
    assert {reason["wake_type"] for reason in advancement["attention"]["reasons"]} == {
        "OPERATION_RESULT"
    }
    assert operation["status"] == "COMPLETED"


def test_watch_attention_ignores_private_plan_churn_until_visible_pressure(app_config):
    engine = CrisisRunEngine(app_config, actor_driver=PlanOnlyDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    advancement = engine.advance_to_attention(run_id)
    events = engine.db.worldline_events(run_id)

    assert advancement["advanced"] is True
    assert advancement["moments"] > 1
    assert advancement["from_tick"] == 0
    assert advancement["to_tick"] == 5
    assert advancement["attention"]["mode"] == "WATCH"
    assert advancement["attention"]["event_type"] == "PRESSURE_APPLIED"
    assert any(event["event_type"] == "PLAN_UPDATED" for event in events)
    assert not any(event["event_type"] == "HUMAN_INTERRUPTION_READY" for event in events)

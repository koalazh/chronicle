from __future__ import annotations

from dataclasses import replace

from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
from chronicle.decision import DecisionOperation, InterpretedDecision


def _passage_terms(perspective: dict) -> list[dict[str, str]]:
    term = next(
        item
        for item in perspective["available_offer_terms"]
        if item["type"] == "passage" and item["subject"]["id"] == "shanhai-pass"
    )
    return [
        {
            "type": term["type"],
            "subject": term["subject"]["id"],
            "value": term["value"],
            "description": term["description"],
        }
    ]


class _NegotiatedSettlementDriver:
    source = "fixture"

    def run_wake(self, actor_id, wake, perspective, world):
        if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
            world.operate(
                "prepare_force",
                ["qing-expedition-force"],
                "先整备西征主力。",
                idempotency_key="prepare-qing",
            )
        elif actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
            world.schedule_revisit(
                after_days=2,
                reason="待关外军力完成整备后重看通行条件。",
                idempotency_key="offer-after-preparation",
            )
        elif actor_id == "wu-sangui" and wake["wake_type"] == "REVISIT_DUE":
            world.manage_offer(
                "PROPOSE",
                recipient="dorgon",
                terms=_passage_terms(perspective),
                message="若共同处置东部局势，可按约定条件通过山海关。",
                idempotency_key="propose-passage",
            )
        elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
            world.manage_offer(
                "ACCEPT",
                offer_id=perspective["trigger"]["offer_id"],
                idempotency_key="accept-passage",
            )
        elif actor_id == "dorgon" and wake["wake_type"] == "AGREEMENT_CHANGE":
            if "enter-shanhai-pass" in {
                item["id"] for item in perspective["available_operations"]
            }:
                world.operate(
                    "enter-shanhai-pass",
                    ["qing-expedition-force", "shanhaiguan"],
                    "依照已生效的通行约定进入山海关。",
                    idempotency_key="enter-with-passage",
                )
        elif wake["wake_type"] == "RESOLUTION_RESULT":
            world.update_plan(
                "依据已经形成的局部结果安排后续处置",
                ["核验已兑现的现实", "收束不再可行的行动"],
                rationale="危局结果已经进入私有视野，之后只能根据它继续判断。",
                idempotency_key=f"{wake['id']}:aftermath",
            )
        return ActorTurnResult("保持有限行动。")


class _SilentDriver:
    source = "fixture"

    def run_wake(self, actor_id, wake, perspective, world):
        return ActorTurnResult("保持观察，不向世界追加主体行动。")


def test_resolution_flows_through_aftermath_before_a_negotiated_settlement(app_config):
    engine = CrisisRunEngine(app_config, actor_driver=_NegotiatedSettlementDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    result = engine.run_until_idle(run_id)
    run = engine.run_summary(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    events = result["events"]

    gate = next(event for event in events if event["event_type"] == "RESOLUTION_GATE_REACHED")
    resolved = next(event for event in events if event["event_type"] == "RESOLUTION_APPLIED")
    dispatched = next(event for event in events if event["event_type"] == "RESOLUTION_REPORT_DISPATCHED")
    report = next(event for event in events if event["event_type"] == "RESOLUTION_REPORT_DELIVERED")
    settlement = next(event for event in events if event["event_type"] == "CRISIS_SETTLED")

    assert run["status"] == "SEALED"
    assert run["crisis_phase"] == "SETTLED"
    assert run["settlement_reason"] == "resolution_stabilized"
    assert run["outcome_json"]["settlement_type"] == "RESOLVED"
    assert run["outcome_json"]["resolution_variant"] == "PASSAGE_IMPLEMENTED"
    assert projection["resolution"]["status"] == "APPLIED"
    assert projection["settlement"]["status"] == "SETTLED"
    assert projection["entities"]["shanhai-pass"]["state"] == "OPEN"
    assert projection["agreements"][0]["status"] == "FULFILLED"
    assert gate["id"] in resolved["causal_parent_ids"]
    assert resolved["id"] in dispatched["causal_parent_ids"]
    assert dispatched["id"] in report["causal_parent_ids"]
    assert resolved["id"] in settlement["causal_parent_ids"]
    assert report["seat_id"] == "li-zicheng"
    assert int(report["tick"]) > int(resolved["tick"])
    assert "li-zicheng" not in resolved["payload"]["visibility"]
    assert all(
        any(
            isinstance(item, dict) and item.get("kind") == "resolution"
            for item in engine.db.worldline_lifetime(run_id, actor_id)["knowledge"]
        )
        for actor_id in ("li-zicheng", "wu-sangui", "dorgon")
    )
    assert {
        wake["actor_id"]
        for wake in result["wakes"]
        if wake["wake_type"] == "RESOLUTION_RESULT" and wake["status"] == "COMPLETED"
    } == {"li-zicheng", "wu-sangui", "dorgon"}
    assert any(
        event["event_type"] == "PLAN_UPDATED"
        and event["seat_id"] == "li-zicheng"
        and int(event["tick"]) >= int(report["tick"])
        for event in events
    )
    assert all(binding["status"] == "REVOKED" for binding in engine.db.agent_bindings(run_id))
    assert CrisisRunEngine(app_config).world_view(run_id)["resolution"]["status"] == "APPLIED"


class _OperationInterpreter:
    source = "fixture"

    def __init__(self, definition_id: str, targets: list[str], description: str):
        self.definition_id = definition_id
        self.targets = targets
        self.description = description

    def interpret(self, text, perspective):
        return InterpretedDecision(
            summary=self.description,
            operations=[
                DecisionOperation(
                    tool="operate",
                    arguments={
                        "operation_definition_id": self.definition_id,
                        "targets": self.targets,
                        "description": self.description,
                    },
                )
            ],
        )


def test_takeover_gets_a_final_gate_and_an_aftermath_attention_before_settlement(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER, human_actor_id="wu-sangui")["run"]["id"]

    engine.submit_human_decision(
        run_id,
        "先整备关宁所部。",
        interpreter=_OperationInterpreter(
            "prepare_force", ["wu-field-force"], "先整备关宁所部。"
        ),
    )
    first = engine.advance_to_attention(run_id)
    assert first["attention"]["tick"] == 1
    engine.submit_human_decision(run_id, "")

    prepared = engine.advance_to_attention(run_id)
    assert prepared["attention"]["tick"] == 2
    engine.submit_human_decision(
        run_id,
        "封闭山海关通道。",
        interpreter=_OperationInterpreter(
            "secure-shanhai-pass",
            ["wu-field-force", "shanhai-pass"],
            "封闭山海关通道。",
        ),
    )

    gate = engine.advance_to_attention(run_id)
    assert gate["attention"]["tick"] == 3
    assert CrisisRunEngine(app_config).run_summary(run_id)["crisis_phase"] == "RESOLUTION_PENDING"
    assert "RESOLUTION_GATE" in {
        reason["wake_type"] for reason in gate["attention"]["reasons"]
    }
    engine.submit_human_decision(run_id, "")

    aftermath = engine.advance_to_attention(run_id)
    assert aftermath["attention"]["actor_id"] == "wu-sangui"
    assert {
        reason["wake_type"] for reason in aftermath["attention"]["reasons"]
    } == {"RESOLUTION_RESULT"}
    engine.submit_human_decision(run_id, "")

    settlement = engine.advance_to_attention(run_id)
    for _ in range(4):
        if settlement["attention"] and settlement["attention"]["mode"] == "SETTLEMENT":
            break
        assert settlement["attention"]["mode"] == "TAKEOVER"
        engine.submit_human_decision(run_id, "")
        settlement = engine.advance_to_attention(run_id)
    assert settlement["attention"] == {
        "mode": "SETTLEMENT",
        "tick": settlement["to_tick"],
        "event_type": "CRISIS_SETTLED",
    }
    run = engine.run_summary(run_id)
    assert run["status"] == "SEALED"
    assert run["crisis_phase"] == "SETTLED"
    assert run["outcome_json"]["settlement_type"] == "DEFERRED"


def test_safety_horizon_seals_a_deferred_outcome_instead_of_failing(app_config):
    base = CrisisRunEngine(app_config).pack
    maximum_tick = base.crisis.simulation_boundary.maximum_tick
    checkpoint = base.crisis.checkpoint.model_copy(
        update={
            "in_transit": [
                message.model_copy(update={"delivery_tick": maximum_tick})
                for message in base.crisis.checkpoint.in_transit
            ]
        }
    )
    pack = replace(
        base,
        crisis=base.crisis.model_copy(
            update={"checkpoint": checkpoint, "pressures": []}
        ),
    )
    pack.validate()
    engine = CrisisRunEngine(app_config, pack=pack, actor_driver=_SilentDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    result = engine.run_until_idle(run_id)
    run = engine.run_summary(run_id)

    assert run["status"] == "SEALED"
    assert run["crisis_phase"] == "SETTLED"
    assert run["current_tick"] == maximum_tick
    assert run["settlement_reason"] == "safety_horizon"
    assert run["outcome_json"]["settlement_type"] == "SAFETY_HORIZON"
    assert run["outcome_json"]["resolution_variant"] == "SAFETY_HORIZON"
    assert engine.world_view(run_id)["settlement"]["reason"] == "safety_horizon"
    assert [
        event["event_type"] for event in result["events"][-3:]
    ] == ["SAFETY_HORIZON_REACHED", "CRISIS_SETTLED", "RUN_SEALED"]

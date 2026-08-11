from __future__ import annotations

import copy
from dataclasses import replace

from chronicle.crisis import (
    CrisisPack,
    CrisisPressureDefinition,
    OperationStateCondition,
    OperationStateEffect,
    OperationVisibility,
    PressureKind,
)
from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
from chronicle.models import Provenance


class SilentDriver:
    source = "fixture"

    def run_wake(self, actor_id, wake, perspective, world):
        return ActorTurnResult("保持观察，不向世界追加主体行动。")


def _conditional_pack(base: CrisisPack, *, wu_force_ready: bool) -> CrisisPack:
    entities = [
        entity.model_copy(update={"initial_state": "READY"})
        if entity.id == "wu-field-force" and wu_force_ready
        else entity
        for entity in base.crisis.entities
    ]
    pressure = CrisisPressureDefinition(
        id="private-readiness-pressure",
        kind=PressureKind.CONDITIONAL,
        title="关口外的临时集结",
        description="只有关宁所部已完成整备时，关口附近的非决策主体才会形成新的公开压力。",
        trigger_tick=1,
        preconditions=[OperationStateCondition(subject="wu-field-force", states=["READY"])],
        effects=[OperationStateEffect(subject="shanhai-pass", state="OPEN")],
        visibility=OperationVisibility.PRIVATE,
        visible_actor_ids=["wu-sangui"],
        provenance=Provenance.MODELED,
        assertion_ids=["c013"],
    )
    pack = replace(
        base,
        crisis=base.crisis.model_copy(
            update={"entities": entities, "pressures": [pressure]}
        ),
    )
    pack.validate()
    return pack


def test_exogenous_pressure_changes_world_without_an_actor_message(app_config):
    engine = CrisisRunEngine(app_config, actor_driver=SilentDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    result = engine.run_until_idle(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    pressure = projection["pressures"][0]
    scheduled = next(event for event in result["events"] if event["event_type"] == "PRESSURE_SCHEDULED")
    applied = next(event for event in result["events"] if event["event_type"] == "PRESSURE_APPLIED")

    assert pressure["status"] == "APPLIED"
    assert pressure["applied_event_id"] == applied["id"]
    assert projection["entities"]["eastern-transit-window"]["state"] == "CLOSING"
    assert applied["causal_parent_ids"] == [scheduled["id"]]
    assert applied["provenance"] == "scenario_assumption"
    assert applied["seat_id"] is None
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED" and int(event["tick"]) > 0
        for event in result["events"]
    )
    assert {wake["actor_id"] for wake in result["wakes"] if wake["wake_type"] == "PRESSURE"} == {
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    }
    assert all(
        any(
            isinstance(item, dict)
            and item.get("kind") == "pressure"
            and item.get("pressure_id") == "eastern-transit-window-narrows"
            for item in engine.db.worldline_lifetime(run_id, actor_id)["knowledge"]
        )
        for actor_id in ("li-zicheng", "wu-sangui", "dorgon")
    )
    assert engine.world_view(run_id)["pressures"] == [pressure]
    restarted = CrisisRunEngine(app_config)
    assert restarted.world_view(run_id)["pressures"][0]["status"] == "APPLIED"
    assert restarted.actor_perspective(run_id, "dorgon")["visible_pressures"][0]["id"] == (
        "eastern-transit-window-narrows"
    )

    before = copy.deepcopy(projection)
    before["entities"]["eastern-transit-window"]["state"] = "OPEN"
    before["entities"]["shun-eastern-force"]["state"] = "READY"
    request, code = engine.pack.operation_request(
        "li-zicheng",
        "move_force",
        ["shun-eastern-force", "yongping"],
        before,
        4,
    )
    assert request is not None and code == ""
    request, code = engine.pack.operation_request(
        "li-zicheng",
        "move_force",
        ["shun-eastern-force", "yongping"],
        projection,
        5,
    )
    assert request is None and code == "operation_precondition_unmet"

    engine.seal(run_id, "test")
    replay_item = next(
        item
        for item in engine.replay(run_id)["items"]
        if item["id"] == applied["id"]
    )
    assert replay_item["title"] == "外部压力进入危局"
    assert "通行窗口" in replay_item["detail"]


def test_conditional_pressure_skips_when_its_world_precondition_is_not_met(app_config):
    base = CrisisRunEngine(app_config).pack
    engine = CrisisRunEngine(
        app_config,
        pack=_conditional_pack(base, wu_force_ready=False),
        actor_driver=SilentDriver(),
    )
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    result = engine.run_until_idle(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]

    assert projection["pressures"][0]["status"] == "SKIPPED"
    assert projection["entities"]["shanhai-pass"]["state"] == "CONTESTED"
    assert any(event["event_type"] == "PRESSURE_SKIPPED" for event in result["events"])
    assert not any(wake["wake_type"] == "PRESSURE" for wake in result["wakes"])


def test_private_conditional_pressure_only_reaches_its_legal_observer(app_config):
    base = CrisisRunEngine(app_config).pack
    engine = CrisisRunEngine(
        app_config,
        pack=_conditional_pack(base, wu_force_ready=True),
        actor_driver=SilentDriver(),
    )
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    result = engine.run_until_idle(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    applied = next(event for event in result["events"] if event["event_type"] == "PRESSURE_APPLIED")

    assert projection["pressures"][0]["status"] == "APPLIED"
    assert projection["entities"]["shanhai-pass"]["state"] == "OPEN"
    assert applied["payload"]["visibility"] == ["wu-sangui"]
    assert [
        wake["actor_id"] for wake in result["wakes"] if wake["wake_type"] == "PRESSURE"
    ] == ["wu-sangui"]
    assert engine.actor_perspective(run_id, "wu-sangui")["visible_pressures"][0]["id"] == (
        "private-readiness-pressure"
    )
    assert engine.actor_perspective(run_id, "li-zicheng")["visible_pressures"] == []
    assert engine.actor_perspective(run_id, "dorgon")["visible_pressures"] == []

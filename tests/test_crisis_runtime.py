from __future__ import annotations

import inspect
import threading
from dataclasses import replace

import pytest

from chronicle.crisis_runtime import (
    ActorTurnResult,
    CrisisRunConflict,
    CrisisRunEngine,
    CrisisRunError,
    HermesActorDriver,
    RunMode,
)
from chronicle.db import content_hash
from chronicle.hermes import HermesRuntimeError
from chronicle.world import WorldAccessError, token_hash, world_tool_signatures


def test_watch_fixture_lives_without_forced_revisits_or_reflections(app_config):
    engine = CrisisRunEngine(app_config)
    created = engine.create(RunMode.WATCH)
    run_id = created["run"]["id"]

    result = engine.run_until_idle(run_id)
    events = result["events"]
    wakes = result["wakes"]

    orient = [wake for wake in wakes if wake["wake_type"] == "ORIENT"]
    assert len(orient) == 3
    assert {wake["actor_id"] for wake in orient} == {"li-zicheng", "wu-sangui", "dorgon"}
    assert all(wake["status"] == "COMPLETED" and wake["source"] == "fixture" for wake in wakes)
    assert len({wake["hermes_session_id"] for wake in wakes}) == len(wakes)
    assert result["run"]["current_tick"] == 5
    assert not any(event["event_type"] == "REVISIT_SCHEDULED" for event in events)
    assert not any(wake["wake_type"] == "REVISIT_DUE" for wake in wakes)
    assert not any(wake["wake_type"] == "REFLECTION" for wake in wakes)
    assert any(event["event_type"] == "MESSAGE_DELIVERED" for event in events)
    assert any(
        event["event_type"] == "ACTOR_WAKE_COMPLETED"
        and event["payload"]["repetition_count"] >= 1
        for event in events
    )

    dorgon_plans = [
        event
        for event in events
        if event["event_type"] == "PLAN_UPDATED" and event["seat_id"] == "dorgon"
    ]
    assert len(dorgon_plans) >= 2
    wu_plans = [
        event
        for event in events
        if event["event_type"] == "PLAN_UPDATED" and event["seat_id"] == "wu-sangui"
    ]
    assert len(wu_plans) >= 3
    li_view = engine.actor_perspective(run_id, "li-zicheng")
    assert "关外回信改变了可选项" not in str(li_view)
    assert not any(str(item).startswith("c00") for item in li_view["knowledge"])
    assert li_view["plan"]
    assert all(
        lifetime["revisits"] == [] for lifetime in engine.db.worldline_lifetimes(run_id)
    )
    assert engine.db.worldline_lifetime(run_id, "dorgon")["beliefs"]["shanhai-request"]
    assert engine.db.agent_bindings(run_id)
    assert all(
        engine.db.memory_versions(f"{run_id}:{actor_id}")[0]["mutation_kind"] == "genesis"
        for actor_id in ("li-zicheng", "wu-sangui", "dorgon")
    )


def test_takeover_uses_same_engine_but_only_agent_actors_orient(app_config):
    engine = CrisisRunEngine(app_config)
    created = engine.create(RunMode.TAKEOVER)
    run_id = created["run"]["id"]
    controllers = created["run"]["controller_map"]

    assert controllers == {
        "li-zicheng": "AGENT",
        "wu-sangui": "HUMAN",
        "dorgon": "AGENT",
    }
    orient = engine.db.crisis_wakes(run_id, status="QUEUED", tick=0)
    assert {wake["actor_id"] for wake in orient} == {"li-zicheng", "dorgon"}
    assert engine.db.worldline_lifetime(run_id, "wu-sangui")["profile_name"] == ""
    with pytest.raises(CrisisRunConflict):
        engine.create(RunMode.WATCH)


@pytest.mark.parametrize("human_actor_id", ["li-zicheng", "wu-sangui", "dorgon"])
def test_takeover_can_select_any_playable_actor(app_config, human_actor_id):
    engine = CrisisRunEngine(app_config)
    created = engine.create(RunMode.TAKEOVER, human_actor_id=human_actor_id)
    run_id = created["run"]["id"]

    assert engine.run_summary(run_id)["human_actor"] == human_actor_id
    assert created["run"]["controller_map"][human_actor_id] == "HUMAN"
    assert engine.db.worldline_lifetime(run_id, human_actor_id)["profile_name"] == ""
    assert {
        wake["actor_id"]
        for wake in engine.db.crisis_wakes(run_id, status="QUEUED", tick=0)
    } == {"li-zicheng", "wu-sangui", "dorgon"} - {human_actor_id}

    result = engine.submit_human_decision(run_id, "")

    assert result["silence"] is True
    assert all(event["seat_id"] == human_actor_id for event in result["events"])


def test_takeover_rejects_an_actor_outside_the_playable_cast(app_config):
    engine = CrisisRunEngine(app_config)

    with pytest.raises(CrisisRunError, match="not playable"):
        engine.create(RunMode.TAKEOVER, human_actor_id="not-an-actor")

    with pytest.raises(CrisisRunError, match="WATCH Runs cannot"):
        engine.create(RunMode.WATCH, human_actor_id="li-zicheng")


def test_private_perspective_exposes_a_grounded_affordance_manifest(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    perspective = engine.actor_perspective(run_id, "wu-sangui")

    assert {item["id"] for item in perspective["contactable_actors"]} == {
        "li-zicheng",
        "dorgon",
    }
    assert {item["id"] for item in perspective["known_entities"]} == {
        "shanhaiguan",
        "wu-field-force",
        "shanhai-pass",
    }
    assert {item["id"] for item in perspective["own_assets"]} == {
        "wu-field-force",
        "shanhai-pass",
    }
    assert {item["id"] for item in perspective["available_operations"]} == {"prepare_force"}
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
    assert perspective["active_operations"] == []
    assert perspective["active_investigations"] == []
    assert perspective["active_offers"] == []
    assert perspective["active_agreements"] == []
    assert perspective["visible_pressures"] == []
    assert perspective["current_revisits"] == []
    assert perspective["meaningful_world_constraints"]
    assert "commitments" not in perspective


def test_human_controller_path_has_no_historical_actor_id():
    human_controller_source = "\n".join(
        inspect.getsource(method)
        for method in (
            CrisisRunEngine.create,
            CrisisRunEngine.human_decision_state,
            CrisisRunEngine.submit_human_decision,
            CrisisRunEngine._commit_human_wake,
            CrisisRunEngine._resolve_human_revisits,
            CrisisRunEngine._human_decision_operation_results,
            CrisisRunEngine._human_actor_id,
        )
    )

    assert "wu-sangui" not in human_controller_source


def test_reaffirmed_plan_stays_private_and_does_not_schedule_reflection(app_config):
    class ReaffirmingDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "li-zicheng" and wake["wake_type"] in {"ORIENT", "MESSAGE"}:
                world.update_plan(
                    "守住东部选择。" if wake["wake_type"] == "MESSAGE" else "守住东部选择",
                    ["等待来使回音"],
                    rationale="文字不同，但当前方向没有改变。",
                    reconsider_when=["收到可验证来信"],
                    idempotency_key=f"{wake['id']}:same-plan",
                )
            return ActorTurnResult("保持当前判断。")

    engine = CrisisRunEngine(app_config, actor_driver=ReaffirmingDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    assert engine.advance_one(run_id) is True
    engine._queue_wake(run_id, "li-zicheng", "MESSAGE", 1)
    engine.run_until_idle(run_id)

    events = engine.db.worldline_events(run_id)
    plans = [
        event
        for event in events
        if event["seat_id"] == "li-zicheng" and event["event_type"] == "PLAN_UPDATED"
    ]
    reaffirmed = [
        event
        for event in events
        if event["seat_id"] == "li-zicheng" and event["event_type"] == "PLAN_REAFFIRMED"
    ]
    assert len(plans) == 1
    assert len(reaffirmed) == 1
    assert not any(wake["wake_type"] == "REFLECTION" for wake in engine.db.crisis_wakes(run_id))
    engine.seal(run_id, "test")
    assert reaffirmed[0]["id"] not in {item["id"] for item in engine.replay(run_id)["items"]}


def test_same_tick_revisit_is_visible_to_every_frozen_actor_perspective(app_config):
    class RevisitAwareDriver:
        source = "fixture"

        def __init__(self):
            self.statuses = {}

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id != "li-zicheng":
                return ActorTurnResult("保持当前判断。")
            if wake["wake_type"] == "ORIENT":
                world.schedule_revisit(
                    1,
                    "明日复查",
                    idempotency_key=f"{wake['id']}:revisit",
                )
            else:
                self.statuses[wake["wake_type"]] = perspective["current_revisits"][0]["status"]
            return ActorTurnResult("保持当前判断。")

    driver = RevisitAwareDriver()
    engine = CrisisRunEngine(app_config, actor_driver=driver)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    assert engine.advance_one(run_id) is True
    engine._queue_wake(run_id, "li-zicheng", "MESSAGE", 1)
    engine.run_until_idle(run_id)

    assert driver.statuses["MESSAGE"] == "DUE"
    assert driver.statuses["REVISIT_DUE"] == "DUE"


def test_live_orient_without_world_operation_fails_closed(app_config):
    class SilentHermesDriver:
        source = "hermes"

        def run_wake(self, actor_id, wake, perspective, world):
            return ActorTurnResult(summary="没有调用世界工具。", session_id=f"session-{actor_id}")

    engine = CrisisRunEngine(app_config, actor_driver=SilentHermesDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    with pytest.raises(CrisisRunError, match="actor wake failed"):
        engine.advance_one(run_id)


def test_live_run_persists_bootstrap_identity_before_materializing_profiles(
    app_config, tmp_path, monkeypatch
):
    calls: list[tuple[str, set[str]]] = []

    def fake_materialize(_config, run_id, actors, **_identity):
        actor_ids = {actor["id"] for actor in actors}
        calls.append((run_id, actor_ids))
        return {
            actor_id: {
                "profile": f"chronicle-{run_id[-8:]}-{actor_id}",
                "profile_key": f"profile-key-{actor_id}",
                "world_token": f"world-token-{actor_id}-{run_id}",
                "ownership_marker": f"owned-{actor_id}-{run_id}",
            }
            for actor_id in actor_ids
        }

    monkeypatch.setattr("chronicle.hermes.materialize_crisis_profiles", fake_materialize)
    watch_config = replace(app_config, database_path=tmp_path / "watch.db")
    watch = CrisisRunEngine(watch_config).create(RunMode.WATCH, runtime_mode="live")
    takeover_config = replace(app_config, database_path=tmp_path / "takeover.db")
    takeover = CrisisRunEngine(takeover_config).create(RunMode.TAKEOVER, runtime_mode="live")

    assert calls == []
    assert watch["run"]["runtime_mode"] == "live"
    assert watch["run"]["runtime_phase"] == "BOOTSTRAPPING"
    assert takeover["run"]["controller_map"]["wu-sangui"] == "HUMAN"
    assert CrisisRunEngine(watch_config).db.agent_bindings(watch["run"]["id"]) == []
    assert CrisisRunEngine(takeover_config).db.crisis_wakes(takeover["run"]["id"]) == []


def test_world_tools_bind_identity_outside_tool_arguments_and_recover_in_one_wake(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    li_wake = next(
        wake
        for wake in engine.db.crisis_wakes(run_id, status="QUEUED")
        if wake["actor_id"] == "li-zicheng"
    )
    engine.db.update_crisis_wake(li_wake["id"], status="RUNNING")
    token = "bound-li-token"
    binding = next(
        item for item in engine.db.agent_bindings(run_id) if item["role"] == "li-zicheng"
    )
    with engine.db.transaction() as connection:
        connection.execute(
            "UPDATE worldline_agent_bindings SET token_hash = ? WHERE id = ?",
            (token_hash(token), binding["id"]),
        )

    world = engine.world.session_for_token(li_wake["id"], token)
    rejected = world.schedule_revisit(
        0,
        "现在立刻再次唤醒",
        idempotency_key="invalid-revisit",
    )
    recovered = world.schedule_revisit(
        2,
        "两日后复查",
        idempotency_key="valid-revisit",
    )
    first = world.communicate(
        "wu-sangui",
        "请说明关口条件。",
        idempotency_key="same-message",
    )
    repeated = world.communicate(
        "wu-sangui",
        "这段不同内容不会覆盖首个幂等提交。",
        idempotency_key="same-message",
    )

    assert rejected == {"status": "rejected", "code": "invalid_revisit"}
    assert recovered["status"] == "accepted" and recovered["due_tick"] == 2
    assert first == repeated
    assert len(engine.db.crisis_wake_operations(li_wake["id"])) == 3
    other_wake = next(
        wake
        for wake in engine.db.crisis_wakes(run_id, status="QUEUED")
        if wake["actor_id"] == "dorgon"
    )
    with pytest.raises(WorldAccessError):
        engine.world.session_for_token(other_wake["id"], token)

    for signature in world_tool_signatures().values():
        assert not {"actor_id", "profile", "run_id"}.intersection(signature.parameters)
    assert "actor_id" not in inspect.signature(type(world).communicate).parameters

    for index in range(3, 8):
        assert world.update_plan(
            f"计划 {index}",
            ["保持边界"],
            idempotency_key=f"plan-{index}",
        )["status"] == "accepted"
    assert world.update_plan(
        "超出预算的计划",
        ["不应进入暂存区"],
        idempotency_key="ninth-operation",
    ) == {"status": "rejected", "code": "wake_tool_budget_exhausted"}
    assert len(engine.db.crisis_wake_operations(li_wake["id"])) == 8


def test_communication_never_creates_a_recursive_same_tick_wake(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "li-zicheng"
    )
    engine.world.route_days = lambda _start, _end: 0
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")

    result = engine.world.fixture_session(wake["id"], "li-zicheng").communicate(
        "wu-sangui",
        "同地也必须进入下一个逻辑时刻。",
        idempotency_key="same-place-message",
    )

    assert result["arrival_tick"] == 1


def test_operate_requires_a_currently_available_crisis_operation(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "wu-sangui"
    )
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")
    world = engine.world.fixture_session(wake["id"], "wu-sangui")

    rejected = world.operate(
        "prepare_force",
        ["nonexistent-artillery"],
        "动用不存在的重炮。",
        idempotency_key="bad-resource",
    )
    unavailable = world.operate(
        "move_force",
        ["wu-field-force", "yongping"],
        "在整备前就向永平行军。",
        idempotency_key="move-before-ready",
    )
    accepted = world.operate(
        "prepare_force",
        ["wu-field-force"],
        "整备关宁所部。",
        idempotency_key="prepare-force",
    )
    conflicting = world.operate(
        "prepare_force",
        ["wu-field-force"],
        "同一时刻重复整备同一支兵力。",
        idempotency_key="duplicate-prepare-force",
    )

    assert rejected == {"status": "rejected", "code": "invalid_operation_targets"}
    assert unavailable == {"status": "rejected", "code": "operation_precondition_unmet"}
    assert accepted["status"] == "accepted" and accepted["expected_complete_tick"] == 2
    assert conflicting == {"status": "rejected", "code": "operation_conflict"}


def test_investigate_requires_a_currently_available_crisis_capability(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "dorgon"
    )
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")
    world = engine.world.fixture_session(wake["id"], "dorgon")

    invalid_question = world.investigate(
        "",
        "shanhai-pass",
        method="courier_report",
        idempotency_key="empty-question",
    )
    unknown_target = world.investigate(
        "关口现在由谁守持？",
        "unknown-pass",
        method="courier_report",
        idempotency_key="unknown-target",
    )
    accepted = world.investigate(
        "关口现在由谁守持？",
        "shanhai-pass",
        method="courier_report",
        idempotency_key="pass-report",
    )
    duplicate = world.investigate(
        "再派一名使者确认。",
        "shanhai-pass",
        method="courier_report",
        idempotency_key="duplicate-report",
    )

    assert invalid_question == {"status": "rejected", "code": "invalid_question"}
    assert unknown_target == {"status": "rejected", "code": "unknown_investigation_target"}
    assert accepted["status"] == "accepted"
    assert accepted["definition_id"] == "shanhai-pass-report"
    assert accepted["expected_result_tick"] == 2
    assert duplicate == {"status": "rejected", "code": "investigation_already_active"}
    assert engine.db.worldline_snapshot(run_id)["projection"]["investigations"] == []


def test_investigation_yields_a_delayed_private_sourced_observation(app_config):
    investigation_ids: list[str] = []

    class InvestigationDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                assert perspective["available_investigations"][0]["target"]["id"] == "shanhai-pass"
                started = world.investigate(
                    "山海关现在由谁守持，是否已有公开通行安排？",
                    "shanhai-pass",
                    method="courier_report",
                    idempotency_key="pass-report",
                )
                investigation_ids.append(str(started["investigation_id"]))
            elif actor_id == "dorgon" and wake["wake_type"] == "INVESTIGATION_RESULT":
                observation = next(
                    item
                    for item in perspective["knowledge"]
                    if isinstance(item, dict)
                    and item.get("investigation_id") == investigation_ids[0]
                )
                assert observation["reliability"] == "MEDIUM"
                world.update_plan(
                    "暂不把关口开放视为既成事实。",
                    ["等待可验证的公开安排", "保留既有行军准备"],
                    belief_updates=[
                        {
                            "subject": "shanhai-pass-report",
                            "assessment": "关口公开安排尚未得到证实。",
                            "confidence": "medium",
                        }
                    ],
                    idempotency_key="reassess-pass-report",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=InvestigationDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]

    assert engine.advance_one(run_id) is True
    started_projection = engine.db.worldline_snapshot(run_id)["projection"]
    investigation = started_projection["investigations"][0]
    assert investigation["status"] == "IN_PROGRESS"
    assert investigation["started_tick"] == 0
    assert investigation["expected_result_tick"] == 2
    assert "observation" not in investigation
    active_view = engine.actor_perspective(run_id, "dorgon")
    assert active_view["active_investigations"][0]["id"] == investigation["id"]
    assert "shanhai-pass" in {item["id"] for item in active_view["known_entities"]}
    assert "尚无可核验的公开安排" not in str(active_view["knowledge"])

    result = engine.run_until_idle(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    completed = projection["investigations"][0]
    observation = completed["observation"]

    assert completed["status"] == "COMPLETED"
    assert observation["investigation_id"] == investigation["id"]
    assert observation["content"] == (
        "山海关仍由吴三桂一方守持；关口是否会为关外军队开放，"
        "尚无可核验的公开安排。来报只能说明可见态势，不能确认双方私下条件。"
    )
    assert observation["source"] == "沿线来人与关口往来文书的交叉转述"
    assert observation["source_ids"] == ["qing-shilu-shizu-4", "mingji-beilue-20"]
    assert observation["reliability"] == "MEDIUM"
    assert observation["obtained_tick"] == 2
    assert observation["related_assertions"] == ["c002", "c012"]
    assert observation["id"] and observation["event_id"]
    started = next(
        event
        for event in result["events"]
        if event["event_type"] == "INVESTIGATION_STARTED"
        and event["payload"]["investigation"]["id"] == investigation["id"]
    )
    completed_event = next(
        event
        for event in result["events"]
        if event["event_type"] == "INVESTIGATION_COMPLETED"
        and event["payload"]["investigation"]["id"] == investigation["id"]
    )
    observed = next(
        event
        for event in result["events"]
        if event["event_type"] == "OBSERVATION_OBTAINED"
        and event["payload"]["observation"]["id"] == observation["id"]
    )
    assert completed_event["causal_parent_ids"] == [started["id"]]
    assert observed["causal_parent_ids"] == [completed_event["id"]]
    investigation_wakes = [
        wake for wake in result["wakes"] if wake["wake_type"] == "INVESTIGATION_RESULT"
    ]
    assert [(wake["actor_id"], wake["tick"], wake["trigger_event_id"]) for wake in investigation_wakes] == [
        ("dorgon", 2, observed["id"])
    ]

    dorgon_view = engine.actor_perspective(run_id, "dorgon")
    private_observation = next(
        item
        for item in dorgon_view["knowledge"]
        if isinstance(item, dict) and item.get("investigation_id") == investigation["id"]
    )
    assert private_observation["source"] == observation["source"]
    assert private_observation["reliability"] == "MEDIUM"
    assert dorgon_view["beliefs"]["shanhai-pass-report"]["assessment"] == "关口公开安排尚未得到证实。"
    li_view = engine.actor_perspective(run_id, "li-zicheng")
    assert observation["content"] not in str(li_view["knowledge"])
    assert observation["event_id"] not in {
        item.get("event_id") for item in li_view["knowledge"] if isinstance(item, dict)
    }


def test_operation_completion_changes_asset_state_then_enables_movement(app_config):
    class MoveDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            from chronicle.crisis_runtime import ActorTurnResult

            if actor_id != "wu-sangui":
                return ActorTurnResult("保持有限行动。")
            if wake["wake_type"] == "ORIENT":
                world.operate(
                    "prepare_force",
                    ["wu-field-force"],
                    "先整备关宁所部。",
                    idempotency_key="prepare-wu",
                )
            elif wake["wake_type"] == "OPERATION_RESULT" and any(
                item["id"] == "move_force" for item in perspective["available_operations"]
            ):
                world.operate(
                    "move_force",
                    ["wu-field-force", "yongping"],
                    "向永平方向继续行军。",
                    idempotency_key="move-wu",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=MoveDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)

    snapshot = engine.db.worldline_snapshot(run_id)["projection"]
    assert snapshot["positions"]["wu-sangui"] == "yongping"
    operations = snapshot["operations"]
    assert [operation["status"] for operation in operations] == ["COMPLETED", "COMPLETED"]
    assert operations[0]["input_state"] == {"wu-field-force": "FORMING"}
    assert operations[0]["result_state"] == {"wu-field-force": "READY"}
    assert operations[1]["input_state"] == {
        "wu-field-force": "READY",
        "yongping": "OPEN",
    }
    assert operations[1]["result_state"] == {"wu-field-force": "COMMITTED"}
    assert snapshot["entities"]["wu-field-force"]["state"] == "COMMITTED"

    prepare_started = next(
        event
        for event in result["events"]
        if event["event_type"] == "OPERATION_STARTED"
        and event["payload"]["operation"]["id"] == operations[0]["id"]
    )
    prepare_completed = next(
        event
        for event in result["events"]
        if event["event_type"] == "OPERATION_COMPLETED"
        and event["payload"]["operation"]["id"] == operations[0]["id"]
    )
    prepare_completion_state = next(
        event
        for event in result["events"]
        if event["event_type"] == "ENTITY_STATE_CHANGED"
        and event["payload"]["operation_id"] == operations[0]["id"]
        and event["payload"]["phase"] == "completion"
    )
    assert prepare_completed["causal_parent_ids"] == [prepare_started["id"]]
    assert prepare_completion_state["causal_parent_ids"] == [prepare_completed["id"]]
    move_started = next(
        event
        for event in result["events"]
        if event["event_type"] == "OPERATION_STARTED"
        and event["payload"]["operation"]["id"] == operations[1]["id"]
    )
    move_start_state = next(
        event
        for event in result["events"]
        if event["event_type"] == "ENTITY_STATE_CHANGED"
        and event["payload"]["operation_id"] == operations[1]["id"]
        and event["payload"]["phase"] == "start"
    )
    assert move_start_state["causal_parent_ids"] == [move_started["id"]]

    operation_wakes = [wake for wake in result["wakes"] if wake["wake_type"] == "OPERATION_RESULT"]
    assert {(wake["actor_id"], wake["tick"]) for wake in operation_wakes} == {
        ("wu-sangui", 2),
        ("wu-sangui", 4),
    }
    li_view = engine.actor_perspective(run_id, "li-zicheng")
    assert "wu-field-force" not in {item["id"] for item in li_view["known_entities"]}
    assert prepare_completed["id"] not in {
        item.get("event_id") for item in li_view["knowledge"] if isinstance(item, dict)
    }

    engine.seal(run_id, "operation-replay-test")
    replay_titles = {item["title"] for item in engine.replay(run_id)["items"]}
    assert {"一项行动已经开始", "一项行动已经完成", "一项关键资产状态已经改变"} <= replay_titles


def test_same_moment_runs_different_actors_concurrently_from_frozen_perspectives(
    app_config,
):
    barrier = threading.Barrier(3)
    lock = threading.Lock()
    orient_perspectives: dict[str, dict] = {}

    class ConcurrentDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if wake["wake_type"] == "ORIENT":
                with lock:
                    orient_perspectives[actor_id] = perspective
                barrier.wait(timeout=2)
            return ActorTurnResult("本次不行动。")

    engine = CrisisRunEngine(app_config, actor_driver=ConcurrentDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)

    assert set(orient_perspectives) == {"li-zicheng", "wu-sangui", "dorgon"}
    assert all(view["tick"] == 0 and view["plan"] == [] for view in orient_perspectives.values())
    assert sum(event["event_type"] == "WAKE_NOOP" for event in result["events"]) >= 3


def test_hermes_actor_driver_uses_bound_profile_and_fresh_session(
    app_config, monkeypatch
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "li-zicheng"
    )
    calls: list[tuple] = []

    class FakeClient:
        def __init__(self, config):
            calls.append(("client", config))

        def create_fresh_session(self, profile, key, wake_id):
            calls.append(("session", profile, key, wake_id))
            return "session-fresh"

        def chat(self, profile, key, messages, session_id, actor_key):
            calls.append(("chat", profile, key, session_id, actor_key, messages))
            return "已完成本次判断。", "session-returned"

    monkeypatch.setattr("chronicle.hermes.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda config, profile: "secret")
    monkeypatch.setattr(
        "chronicle.hermes.read_profile_memory",
        lambda config, profile: ("", engine.db.worldline_lifetime(run_id, "li-zicheng")["memory_hash"]),
    )
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")

    result = HermesActorDriver(app_config, engine.db).run_wake(
        "li-zicheng",
        wake,
        {"tick": 0, "trigger": {}},
        engine.world.fixture_session(wake["id"], "li-zicheng"),
    )

    assert result.summary == "已完成本次判断。"
    assert result.session_id == "session-returned"
    assert result.memory_changed is False
    assert ("session", "fixture://li-zicheng", "secret", wake["id"]) in calls
    assert any(call[0] == "chat" and call[3] == "session-fresh" for call in calls)


def test_ordinary_live_wake_rolls_back_and_audits_memory_mutation(
    app_config, monkeypatch
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "li-zicheng"
    )
    profile = "chronicle-memory-guard"
    memory_path = app_config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("", encoding="utf-8")
    engine.db.update_worldline_lifetime(run_id, "li-zicheng", profile_name=profile)

    class MutatingClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "session-memory-guard"

        def chat(self, _profile, _key, _messages, _session_id, _actor_key):
            memory_path.write_text("不应由普通 Wake 留下", encoding="utf-8")
            return "完成。", "session-memory-guard"

    monkeypatch.setattr("chronicle.hermes.HermesClient", MutatingClient)
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda _config, _profile: "secret")
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")

    with pytest.raises(HermesRuntimeError, match="durable Memory mutation"):
        HermesActorDriver(app_config, engine.db).run_wake(
            "li-zicheng",
            wake,
            {"tick": 0, "trigger": {}},
            engine.world.fixture_session(wake["id"], "li-zicheng"),
        )

    assert memory_path.read_text(encoding="utf-8") == ""
    violation = engine.db.protocol_violations(f"{run_id}:li-zicheng")[0]
    assert violation["action"] == "rollback"
    assert violation["memory_hash_before"] == content_hash("")


def test_failed_reflection_rolls_native_memory_back_before_audit_commit(
    app_config, monkeypatch
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = engine._queue_wake(run_id, "li-zicheng", "REFLECTION", 1)
    profile = "chronicle-reflection-rollback"
    memory_path = app_config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("before", encoding="utf-8")
    engine.db.update_worldline_lifetime(
        run_id,
        "li-zicheng",
        profile_name=profile,
        memory_text="before",
        memory_hash=content_hash("before"),
    )

    class FailingReflectionClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "session-reflection-failure"

        def chat(self, _profile, _key, _messages, _session_id, _actor_key):
            memory_path.write_text("after-but-unaudited", encoding="utf-8")
            raise RuntimeError("provider failed after memory tool call")

    monkeypatch.setattr("chronicle.hermes.HermesClient", FailingReflectionClient)
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda _config, _profile: "secret")
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")

    with pytest.raises(HermesRuntimeError, match="live Hermes Wake failed"):
        HermesActorDriver(app_config, engine.db).run_wake(
            "li-zicheng",
            wake,
            {"tick": 1, "trigger": {}},
            engine.world.fixture_session(wake["id"], "li-zicheng"),
        )

    assert memory_path.read_text(encoding="utf-8") == "before"
    assert engine.db.worldline_lifetime(run_id, "li-zicheng")["memory_text"] == "before"
    violation = engine.db.protocol_violations(f"{run_id}:li-zicheng")[-1]
    assert violation["wake_type"] == "REFLECTION"
    assert violation["action"] == "rollback"


def test_same_actor_batch_carries_staged_reflection_hash_to_the_next_wake(
    app_config, monkeypatch
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    profile = "chronicle-batched-reflection"
    memory_path = app_config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("before", encoding="utf-8")
    engine.db.update_worldline_lifetime(
        run_id,
        "dorgon",
        profile_name=profile,
        memory_text="before",
        memory_hash=content_hash("before"),
    )
    reflection = engine.db.create_crisis_wake(
        {
            "id": "wake-batch-a-reflection",
            "worldline_id": run_id,
            "actor_id": "dorgon",
            "wake_type": "REFLECTION",
            "tick": 1,
            "source": "hermes",
        }
    )
    ordinary = engine.db.create_crisis_wake(
        {
            "id": "wake-batch-b-observation",
            "worldline_id": run_id,
            "actor_id": "dorgon",
            "wake_type": "OBSERVATION",
            "tick": 1,
            "source": "hermes",
        }
    )
    calls = 0

    class BatchedClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, wake_id):
            return f"session-{wake_id}"

        def chat(self, _profile, _key, _messages, session_id, _actor_key):
            nonlocal calls
            calls += 1
            if calls == 1:
                memory_path.write_text("reflected", encoding="utf-8")
            return "完成。", session_id

    monkeypatch.setattr("chronicle.hermes.HermesClient", BatchedClient)
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda _config, _profile: "secret")
    engine.actor_driver = HermesActorDriver(app_config, engine.db)
    frozen = {
        reflection["id"]: {"tick": 1, "trigger": {}},
        ordinary["id"]: {"tick": 1, "trigger": {}},
    }

    results = engine._execute_actor_wakes([ordinary, reflection], frozen)

    assert results[reflection["id"]].memory_changed is True
    assert results[ordinary["id"]].memory_before_hash == content_hash("reflected")
    assert memory_path.read_text(encoding="utf-8") == "reflected"


def test_later_wake_failure_compensates_an_earlier_staged_reflection(
    app_config, monkeypatch
):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    profile = "chronicle-batched-reflection-failure"
    memory_path = app_config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("before", encoding="utf-8")
    engine.db.update_worldline_lifetime(
        run_id,
        "dorgon",
        profile_name=profile,
        memory_text="before",
        memory_hash=content_hash("before"),
    )
    reflection = engine.db.create_crisis_wake(
        {
            "id": "wake-failure-a-reflection",
            "worldline_id": run_id,
            "actor_id": "dorgon",
            "wake_type": "REFLECTION",
            "tick": 1,
            "source": "hermes",
        }
    )
    ordinary = engine.db.create_crisis_wake(
        {
            "id": "wake-failure-b-observation",
            "worldline_id": run_id,
            "actor_id": "dorgon",
            "wake_type": "OBSERVATION",
            "tick": 1,
            "source": "hermes",
        }
    )
    calls = 0

    class FailingBatchClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, wake_id):
            return f"session-{wake_id}"

        def chat(self, _profile, _key, _messages, session_id, _actor_key):
            nonlocal calls
            calls += 1
            if calls == 1:
                memory_path.write_text("staged-only", encoding="utf-8")
                return "完成反思。", session_id
            raise RuntimeError("later Wake failed")

    monkeypatch.setattr("chronicle.hermes.HermesClient", FailingBatchClient)
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda _config, _profile: "secret")
    engine.actor_driver = HermesActorDriver(app_config, engine.db)
    frozen = {
        reflection["id"]: {"tick": 1, "trigger": {}},
        ordinary["id"]: {"tick": 1, "trigger": {}},
    }

    with pytest.raises(CrisisRunError, match="actor wake failed"):
        engine._execute_actor_wakes([ordinary, reflection], frozen)

    assert memory_path.read_text(encoding="utf-8") == "before"
    assert engine.db.worldline_lifetime(run_id, "dorgon")["memory_text"] == "before"


def test_reflection_memory_change_commits_lifetime_ledger_and_version_atomically(app_config):
    reflected_text = "只保留一次危局中经验证的长期教训。"

    class ReflectionDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "li-zicheng" and wake["wake_type"] == "REFLECTION":
                return ActorTurnResult(
                    "完成反思。",
                    memory_before_text="",
                    memory_before_hash=content_hash(""),
                    memory_before_existed=True,
                    memory_text=reflected_text,
                    memory_hash=content_hash(reflected_text),
                    memory_changed=True,
                )
            return ActorTurnResult("本次不行动。")

    engine = CrisisRunEngine(app_config, actor_driver=ReflectionDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    trigger_event = engine.db.worldline_events(run_id)[-1]["id"]
    engine._queue_wake(
        run_id,
        "li-zicheng",
        "REFLECTION",
        1,
        trigger_event_id=trigger_event,
    )

    result = engine.run_until_idle(run_id)

    lifetime = engine.db.worldline_lifetime(run_id, "li-zicheng")
    versions = engine.db.memory_versions(f"{run_id}:li-zicheng")
    reflected_event = next(
        event for event in result["events"] if event["event_type"] == "MEMORY_REFLECTED"
    )
    assert lifetime["memory_text"] == reflected_text
    assert lifetime["memory_hash"] == content_hash(reflected_text)
    assert [version["mutation_kind"] for version in versions] == ["genesis", "reflection"]
    assert reflected_event["causal_parent_ids"] == [trigger_event]


def test_replay_preserves_actor_visibility_and_message_causality(app_config):
    class PrivateMessageDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.communicate(
                    "li-zicheng",
                    "这封信不应成为吴三桂当时可见的内容。",
                    idempotency_key="dorgon-to-li",
                )
            return ActorTurnResult("完成有限判断。")

    engine = CrisisRunEngine(app_config, actor_driver=PrivateMessageDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)
    engine.seal(run_id, "test")
    replay = engine.replay(run_id)

    dispatch = next(
        item
        for item in replay["items"]
        if "这封信不应" in item["detail"] and item["title"] == "一封信已经上路"
    )
    delivery = next(
        item
        for item in replay["items"]
        if "这封信不应" in item["detail"] and item["title"] == "一封信抵达收信人"
    )
    assert dispatch["visible_to"] == ["dorgon"]
    assert delivery["visible_to"] == ["dorgon", "li-zicheng"]
    assert "wu-sangui" not in delivery["visible_to"]
    assert delivery["causal_parent_ids"] == [dispatch["id"]]
    assert delivery["causes"] == [
        {"id": dispatch["id"], "title": dispatch["title"], "actor_id": "dorgon"}
    ]


def test_replay_resolves_plan_message_receipt_plan_chain(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)
    engine.seal(run_id, "test")
    items = engine.replay(run_id)["items"]
    by_id = {item["id"]: item for item in items}

    dispatch = next(
        item
        for item in items
        if item["title"] == "一封信已经上路"
        and item["causes"]
        and item["causes"][0]["title"] == "有人修正了自己的打算"
    )
    delivery = next(
        item
        for item in items
        if item["title"] == "一封信抵达收信人"
        and item["causal_parent_ids"] == [dispatch["id"]]
    )
    recipient_plan = next(
        item
        for item in items
        if item["title"] == "有人修正了自己的打算"
        and item["causal_parent_ids"] == [delivery["id"]]
    )

    assert by_id[dispatch["causal_parent_ids"][0]]["title"] == "有人修正了自己的打算"
    assert recipient_plan["actor_id"] == delivery["actor_id"]


def test_atomic_wake_commits_private_plan_before_outgoing_message(app_config):
    class SendThenPlanDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.communicate(
                    "li-zicheng",
                    "先由模型调用通信，再登记本次判断。",
                    idempotency_key="send-first",
                )
                world.update_plan(
                    "先形成可追溯的判断，再让去信成为其外部效果",
                    ["等待回信"],
                    rationale="同一 Wake 的世界效果在一个原子 moment 提交。",
                    idempotency_key="plan-second",
                )
            return ActorTurnResult("完成判断。")

    engine = CrisisRunEngine(app_config, actor_driver=SendThenPlanDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    assert engine.advance_one(run_id) is True
    events = engine.db.worldline_events(run_id)
    plan = next(
        event
        for event in events
        if event["event_type"] == "PLAN_UPDATED" and event["seat_id"] == "dorgon"
    )
    dispatch = next(
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("content") == "先由模型调用通信，再登记本次判断。"
    )

    assert plan["sequence"] < dispatch["sequence"]
    assert dispatch["causal_parent_ids"] == [plan["id"]]

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


def test_watch_fixture_lives_autonomously_for_seven_simulated_days(app_config):
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
    assert result["run"]["current_tick"] == 7
    assert any(event["event_type"] == "COMMITMENT_SCHEDULED" for event in events)
    assert any(wake["wake_type"] == "COMMITMENT_DUE" for wake in wakes)
    assert any(wake["wake_type"] == "REFLECTION" for wake in wakes)
    assert any(event["event_type"] == "MESSAGE_DELIVERED" for event in events)
    assert any(event["event_type"] == "WAKE_NOOP" for event in events)
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
        commitment["status"] == "FULFILLED"
        for lifetime in engine.db.worldline_lifetimes(run_id)
        for commitment in lifetime["commitments"]
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


def test_live_watch_and_takeover_materialize_only_agent_controlled_profiles(
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

    assert calls[0][1] == {"li-zicheng", "wu-sangui", "dorgon"}
    assert calls[1][1] == {"li-zicheng", "dorgon"}
    assert watch["run"]["runtime_mode"] == "live"
    assert takeover["run"]["controller_map"]["wu-sangui"] == "HUMAN"
    assert all(
        binding["token_hash"] and "world-token" not in str(binding)
        for binding in CrisisRunEngine(watch_config).db.agent_bindings(watch["run"]["id"])
    )


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
    rejected = world.schedule_followup(
        0,
        "现在立刻再次唤醒",
        idempotency_key="invalid-followup",
    )
    recovered = world.schedule_followup(
        2,
        "两日后复查",
        idempotency_key="valid-followup",
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

    assert rejected == {"status": "rejected", "code": "invalid_followup"}
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


def test_prepare_and_hold_require_owned_resource_or_current_position(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "wu-sangui"
    )
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")
    world = engine.world.fixture_session(wake["id"], "wu-sangui")

    rejected = world.act(
        "prepare",
        "动用不存在的重炮。",
        target="nonexistent-artillery",
        idempotency_key="bad-resource",
    )
    accepted = world.act(
        "hold",
        "维持关口防备。",
        target="shanhaiguan",
        idempotency_key="grounded-position",
    )

    assert rejected == {"status": "rejected", "code": "unknown_resource_or_position"}
    assert accepted["status"] == "accepted"


def test_movement_arrival_advances_truth_then_wakes_only_the_moving_actor(app_config):
    class MoveDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            from chronicle.crisis_runtime import ActorTurnResult

            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.act(
                    "move",
                    "向山海关方向继续行军。",
                    target="shanhaiguan",
                    idempotency_key="move-west",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=MoveDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)

    assert engine.db.worldline_snapshot(run_id)["projection"]["positions"]["dorgon"] == "shanhaiguan"
    assert any(event["event_type"] == "MOVEMENT_ARRIVED" for event in result["events"])
    observation_wakes = [
        wake for wake in result["wakes"] if wake["wake_type"] == "OBSERVATION"
    ]
    assert {(wake["actor_id"], wake["tick"]) for wake in observation_wakes} == {
        ("dorgon", 2)
    }
    assert "已到达山海关" not in str(engine.actor_perspective(run_id, "li-zicheng"))


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

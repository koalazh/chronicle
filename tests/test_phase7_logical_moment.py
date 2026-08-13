from __future__ import annotations

from dataclasses import replace

import pytest

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
    host.volume_runtime.inhabit(worldline_id, wu["id"])
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:wake:dorgon:logical-moment",
            "worldline_id": worldline_id,
            "actor_id": dorgon["id"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "phase7-test",
            "trigger_event_id": f"{worldline_id}:trigger:dorgon",
        }
    )
    return runtime, worldline_id, wu, dorgon


def _semantic_result(runtime, worldline_id: str) -> dict[str, object]:
    events = runtime.db.worldline_events(worldline_id)
    logical_intents = [
        (
            event["seat_id"],
            event["payload"]["source"],
            event["payload"]["intent"],
        )
        for event in events
        if event["event_type"] == "INTENT_COMMITTED"
    ]
    logical_messages = [
        {
            key: event["payload"][key]
            for key in ("sender", "recipient", "content", "dispatch_tick", "delivery_tick")
        }
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "logical_moment"
    ]
    logical_messages.sort(key=lambda message: (message["sender"], message["recipient"]))
    wakes = runtime.db.subject_wakes(worldline_id)
    wake_states = []
    for wake in wakes:
        lifetime = runtime.db.worldline_lifetime_by_id(worldline_id, wake["actor_id"])
        lifetime = lifetime or runtime.db.worldline_lifetime(worldline_id, wake["actor_id"])
        assert lifetime is not None
        wake_states.append(
            (
                lifetime["seat"],
                wake["status"],
                wake["result"].get("delivery_tick"),
            )
        )
    wake_states.sort()
    operation_states = sorted(
        (
            operation["payload"]["seat"],
            operation["status"],
            operation["result"].get("status"),
            operation["result"].get("delivery_tick"),
        )
        for wake in wakes
        for operation in runtime.db.crisis_wake_operations(wake["id"])
        if operation["payload"].get("moment_id")
    )
    projection = runtime.worldline(worldline_id)["projection"]
    return {
        "tick": runtime.db.worldline(worldline_id)["current_tick"],
        "intent_order": [item[0] for item in logical_intents],
        "intents": sorted(logical_intents, key=lambda item: item[0]),
        "messages": logical_messages,
        "wake_states": wake_states,
        "operation_states": operation_states,
        "has_pending_moment": "pending_moment" in projection,
    }


def _commit_in_order(app_config, suffix: str, stage_order: list[str]):
    runtime, worldline_id, wu, dorgon = _runtime(app_config, suffix)
    frozen = runtime.freeze_pending_moment(worldline_id)
    assert runtime.next_tick(worldline_id) is None
    with pytest.raises(VolumeRuntimeConflict, match="Pending Logical Moment"):
        runtime.advance_one(worldline_id)
    intents = {
        "wu-sangui": {
            "type": "message",
            "recipient": "shi-kefa",
            "content": "human staged",
            "delivery_tick": 3,
        },
        "dorgon": {
            "type": "message",
            "recipient": "li-zicheng",
            "content": "agent staged",
            "delivery_tick": 4,
        },
    }
    lifetimes = {wu["seat"]: wu, dorgon["seat"]: dorgon}
    for seat in stage_order:
        runtime.stage_intent(
            worldline_id,
            lifetimes[seat]["id"],
            intents[seat],
            source="human" if seat == "wu-sangui" else "agent",
        )
    committed = runtime.commit_pending_moment(worldline_id)
    assert committed["moment_id"] == frozen["moment_id"]
    return _semantic_result(runtime, worldline_id)


def test_pending_moment_is_independent_of_staging_order(app_config):
    forward = _commit_in_order(app_config, "forward", ["wu-sangui", "dorgon"])
    reverse = _commit_in_order(app_config, "reverse", ["dorgon", "wu-sangui"])

    assert forward == reverse
    assert forward["intent_order"] == ["dorgon", "wu-sangui"]
    assert forward["tick"] == 1
    assert forward["has_pending_moment"] is False


def test_pending_moment_does_not_partially_commit_before_all_intents(app_config):
    runtime, worldline_id, wu, dorgon = _runtime(app_config, "atomic")
    runtime.freeze_pending_moment(worldline_id)
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "message",
            "recipient": "shi-kefa",
            "content": "human staged",
            "delivery_tick": 3,
        },
        source="human",
    )

    with pytest.raises(VolumeRuntimeConflict, match="all Human and Agent intents"):
        runtime.commit_pending_moment(worldline_id)

    assert runtime.db.worldline(worldline_id)["current_tick"] == 1
    assert "pending_moment" in runtime.worldline(worldline_id)["projection"]
    assert not any(
        event["event_type"] == "INTENT_COMMITTED"
        for event in runtime.db.worldline_events(worldline_id)
    )

    runtime.stage_intent(
        worldline_id,
        dorgon["id"],
        {
            "type": "message",
            "recipient": "li-zicheng",
            "content": "agent staged",
            "delivery_tick": 4,
        },
        source="agent",
    )
    committed = runtime.commit_pending_moment(worldline_id)
    retried = runtime.commit_pending_moment(worldline_id)

    assert committed["idempotent"] is False
    assert retried["idempotent"] is True
    assert _semantic_result(runtime, worldline_id)["has_pending_moment"] is False


def test_pending_moment_retries_after_executor_restart_before_commit(app_config):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name("restart-before-commit-base.db"),
        runtime_dir=app_config.runtime_dir / "restart-before-commit-base",
        hermes_home=app_config.hermes_home / "restart-before-commit-base",
    )
    runtime, worldline_id, wu, dorgon = _runtime(config, "restart-before-commit")
    runtime.freeze_pending_moment(worldline_id)
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {"type": "update_plan", "objective": "保留选择", "steps": ["等待核验"]},
        source="human",
    )
    runtime.stage_intent(
        worldline_id,
        dorgon["id"],
        {"type": "wait"},
        source="agent",
    )

    restarted_config = replace(
        config,
        database_path=config.database_path.with_name("chronicle-restart-before-commit.db"),
    )
    restarted = ChronicleHost(restarted_config).volume_runtime
    committed = restarted.commit_pending_moment(worldline_id)
    retried_after_ack_loss = runtime.commit_pending_moment(worldline_id)

    assert committed["idempotent"] is False
    assert retried_after_ack_loss["idempotent"] is True
    assert [event["event_type"] for event in restarted.db.worldline_events(worldline_id)].count(
        "MOMENT_COMMITTED"
    ) == 1


def test_pending_moment_retry_after_commit_before_ack(app_config):
    base_config = replace(
        app_config,
        database_path=app_config.database_path.with_name("commit-before-ack-base.db"),
        runtime_dir=app_config.runtime_dir / "commit-before-ack-base",
        hermes_home=app_config.hermes_home / "commit-before-ack-base",
    )
    runtime, worldline_id, wu, dorgon = _runtime(base_config, "commit-before-ack")
    runtime.freeze_pending_moment(worldline_id)
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {"type": "update_plan", "objective": "保留选择", "steps": ["等待核验"]},
        source="human",
    )
    runtime.stage_intent(worldline_id, dorgon["id"], {"type": "wait"}, source="agent")

    committed = runtime.commit_pending_moment(worldline_id)
    restarted_config = replace(
        base_config,
        database_path=base_config.database_path.with_name("chronicle-commit-before-ack.db"),
        runtime_dir=base_config.runtime_dir / "commit-before-ack",
        hermes_home=base_config.hermes_home / "commit-before-ack",
    )
    restarted = ChronicleHost(restarted_config).volume_runtime
    retried = restarted.commit_pending_moment(worldline_id)

    assert committed["idempotent"] is False
    assert retried["idempotent"] is True
    assert [event["event_type"] for event in restarted.db.worldline_events(worldline_id)].count(
        "MOMENT_COMMITTED"
    ) == 1

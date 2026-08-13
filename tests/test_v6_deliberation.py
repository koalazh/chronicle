from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntimeConflict, VolumeRuntimeError


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-deliberation-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-deliberation-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-deliberation-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return config, runtime, worldline_id, wu


def _establish_course(runtime, worldline_id, wu):
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "等待多尔衮明确回复",
            "steps": ["守住关口", "核验来信"],
            "open_dependencies": [
                {"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}
            ],
        },
        source="agent",
        idempotency_key="v6-deliberation-course",
    )
    runtime.commit_pending_moment(worldline_id)


def _matching_wake(runtime, worldline_id):
    return next(
        wake
        for wake in reversed(runtime.db.subject_wakes(worldline_id))
        if wake["actor_id"] == "wu-sangui"
        and wake["source"] == "v6-attention"
        and wake["wake_type"] == "OBSERVATION"
    )


def test_hold_is_a_first_class_atomic_deliberation_without_world_action(app_config):
    _config, runtime, worldline_id, wu = _runtime(app_config, "hold")
    _establish_course(runtime, worldline_id, wu)
    before = copy.deepcopy(runtime.db.worldline_lifetime(worldline_id, wu["seat"])["plan"][0])
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-hold",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-deliberation-test",
            "trigger_event_id": f"{worldline_id}:hold-trigger",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = next(
        item for item in frozen["pending_moment"]["wake_ids"] if item.endswith(":v6-hold")
    )

    staged = runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        {"outcome": "HOLD", "world_actions": []},
        source="agent",
        idempotency_key="v6-hold-once",
        wake_id=wake_id,
    )
    committed = runtime.commit_pending_moment(worldline_id)
    event_types = [event["event_type"] for event in committed["events"]]
    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None

    assert staged["outcome"] == "HOLD"
    assert "DELIBERATION_COMMITTED" in event_types
    assert "DECISION_HORIZON_HELD" in event_types
    assert "MESSAGE_DISPATCHED" not in event_types
    assert lifetime["plan"][0]["course"] == before["course"]
    assert lifetime["plan"][0]["last_deliberated_event_id"]
    assert lifetime["plan"][0]["last_deliberated_event_id"] != before["last_deliberated_event_id"]


def test_agent_revise_requires_visible_evidence_and_can_commit_one_action(app_config):
    _config, runtime, worldline_id, wu = _runtime(app_config, "revise")
    _establish_course(runtime, worldline_id, wu)
    delivered = runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="dorgon",
        recipient="wu-sangui",
        content="清方已有明确条件。",
        delivery_tick=2,
    )
    advanced = runtime.advance_one(worldline_id)
    delivered_event = next(
        event for event in advanced["events"] if event["event_type"] == "MESSAGE_DELIVERED"
    )
    assert delivered["message"]["id"]
    runtime.freeze_pending_moment(worldline_id)
    wake = _matching_wake(runtime, worldline_id)

    staged = runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        {
            "outcome": "REVISE",
            "course": {
                "summary": "收到明确条件后改为先核验通行边界",
                "steps": ["核验边界"],
                "evidence_event_ids": [delivered_event["id"]],
            },
            "open_dependencies": [],
            "world_actions": [
                {
                    "tool": "communicate",
                    "arguments": {
                        "recipient": "dorgon",
                        "content": "请提交可核验的通行边界。",
                    },
                }
            ],
        },
        source="agent",
        idempotency_key="v6-revise-once",
        wake_id=wake["id"],
    )
    committed = runtime.commit_pending_moment(worldline_id)
    event_types = [event["event_type"] for event in committed["events"]]
    deliberation = next(
        event for event in committed["events"] if event["event_type"] == "DELIBERATION_COMMITTED"
    )
    message = next(
        event for event in committed["events"] if event["event_type"] == "MESSAGE_DISPATCHED"
    )
    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None

    assert staged["outcome"] == "REVISE"
    assert event_types.count("DELIBERATION_COMMITTED") == 1
    assert event_types.count("MESSAGE_DISPATCHED") == 1
    assert event_types[-1] == "MOMENT_COMMITTED"
    assert lifetime["plan"][0]["course"] == "收到明确条件后改为先核验通行边界"
    assert lifetime["plan"][0]["evidence_event_ids"] == [delivered_event["id"]]
    assert message["causal_parent_ids"] == [deliberation["id"]]


def test_agent_revise_without_evidence_is_rejected_before_staging(app_config):
    _config, runtime, worldline_id, wu = _runtime(app_config, "missing-evidence")
    _establish_course(runtime, worldline_id, wu)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-revise-no-evidence",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-deliberation-test",
            "trigger_event_id": "",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = next(
        item
        for item in frozen["pending_moment"]["wake_ids"]
        if item.endswith(":v6-revise-no-evidence")
    )

    with pytest.raises(VolumeRuntimeConflict, match="requires actor-visible evidence"):
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            {"outcome": "REVISE", "course": {"summary": "临时改主意"}},
            source="agent",
            idempotency_key="v6-revise-missing-evidence",
            wake_id=wake_id,
        )

    wake = runtime.db.crisis_wake(wake_id)
    assert wake is not None and wake["status"] == "STAGED"
    operations = runtime.db.crisis_wake_operations(wake_id)
    assert len(operations) == 1
    assert operations[0]["result"]["status"] == "rejected"
    assert operations[0]["payload"]["proposal_hash"]


def test_deliberation_rejects_multiple_world_actions_atomically(app_config):
    _config, runtime, worldline_id, wu = _runtime(app_config, "multi-action")
    _establish_course(runtime, worldline_id, wu)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-multi-action",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-deliberation-test",
            "trigger_event_id": "",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = next(
        item for item in frozen["pending_moment"]["wake_ids"] if item.endswith(":v6-multi-action")
    )

    with pytest.raises(VolumeRuntimeError, match="at most one action"):
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            {
                "outcome": "HOLD",
                "world_actions": [
                    {"tool": "schedule_revisit", "arguments": {"after_days": 1, "reason": "甲"}},
                    {"tool": "schedule_revisit", "arguments": {"after_days": 2, "reason": "乙"}},
                ],
            },
            source="agent",
            idempotency_key="v6-multi-action",
            wake_id=wake_id,
        )
    operations = runtime.db.crisis_wake_operations(wake_id)
    assert len(operations) == 1
    assert operations[0]["result"]["status"] == "rejected"


def test_agent_rejected_deliberation_is_idempotent_and_consumes_the_wake(app_config):
    config, runtime, worldline_id, wu = _runtime(app_config, "reject-once")
    _establish_course(runtime, worldline_id, wu)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-reject-once",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-deliberation-test",
            "trigger_event_id": "",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = next(
        item for item in frozen["pending_moment"]["wake_ids"] if item.endswith(":v6-reject-once")
    )
    invalid = {
        "outcome": "HOLD",
        "world_actions": [
            {"tool": "schedule_revisit", "arguments": {"after_days": 1, "reason": "甲"}},
            {"tool": "schedule_revisit", "arguments": {"after_days": 2, "reason": "乙"}},
        ],
    }

    with pytest.raises(VolumeRuntimeError, match="at most one action"):
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            invalid,
            source="agent",
            idempotency_key="v6-reject-once",
            wake_id=wake_id,
        )
    first = runtime.db.crisis_wake_operations(wake_id)[0]
    exact_retry = runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        invalid,
        source="agent",
        idempotency_key="v6-reject-once",
        wake_id=wake_id,
    )
    assert exact_retry["idempotent"] is True
    assert exact_retry["rejected"] is True
    assert exact_retry["operation"]["id"] == first["id"]
    with pytest.raises(VolumeRuntimeConflict, match="one Deliberation proposal"):
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            {"outcome": "HOLD", "world_actions": []},
            source="agent",
            idempotency_key="v6-reject-once-different",
            wake_id=wake_id,
        )

    restarted = ChronicleHost(config).volume_runtime
    with pytest.raises(VolumeRuntimeConflict, match="one Deliberation proposal"):
        restarted.stage_deliberation(
            worldline_id,
            wu["id"],
            {"outcome": "HOLD", "world_actions": []},
            source="agent",
            idempotency_key="v6-reject-once-after-restart",
            wake_id=wake_id,
        )
    committed = restarted.commit_pending_moment(worldline_id)
    event_types = [event["event_type"] for event in committed["events"]]
    assert "INTENT_REJECTED" in event_types
    assert "DELIBERATION_COMMITTED" not in event_types
    assert restarted.db.crisis_wake(wake_id)["status"] == "COMPLETED"


def test_staged_deliberation_survives_restart_and_replays_once(app_config):
    config, runtime, worldline_id, wu = _runtime(app_config, "restart")
    _establish_course(runtime, worldline_id, wu)
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-restart",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-deliberation-test",
            "trigger_event_id": "",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = next(
        item for item in frozen["pending_moment"]["wake_ids"] if item.endswith(":v6-restart")
    )
    runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        {"outcome": "HOLD"},
        source="agent",
        idempotency_key="v6-restart-once",
        wake_id=wake_id,
    )

    restarted = ChronicleHost(config).volume_runtime
    committed = restarted.commit_pending_moment(worldline_id)
    repeated = restarted.commit_pending_moment(worldline_id)
    events = restarted.db.worldline_events(worldline_id)
    assert any(event["event_type"] == "DELIBERATION_COMMITTED" for event in committed["events"])
    assert repeated["idempotent"] is True
    assert sum(event["event_type"] == "DELIBERATION_COMMITTED" for event in events) == 1

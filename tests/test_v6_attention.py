from __future__ import annotations

from dataclasses import replace

from chronicle.host import ChronicleHost
from chronicle.subject_attention import AttentionDecision, evaluate_attention


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-attention-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-attention-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-attention-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return runtime, worldline_id, wu


def _establish_course(runtime, worldline_id, wu, dependencies):
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "维持关口可控",
            "steps": ["继续核验"],
            "open_dependencies": dependencies,
        },
        source="agent",
        idempotency_key=f"v6-attention-course-{len(dependencies)}",
    )
    runtime.commit_pending_moment(worldline_id)


def _attention_event(runtime, worldline_id, seat: str):
    return next(
        event
        for event in reversed(runtime.db.worldline_events(worldline_id))
        if event["event_type"] == "ATTENTION_EVALUATED" and event["seat_id"] == seat
    )


def test_irrelevant_known_message_is_background_without_a_wake(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "irrelevant-message")
    _establish_course(
        runtime,
        worldline_id,
        wu,
        [{"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}],
    )
    dispatched = runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="li-zicheng",
        recipient="wu-sangui",
        content="另一封已知但不相关的来信。",
        delivery_tick=2,
    )

    advanced = runtime.advance_one(worldline_id)
    lifetime = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert lifetime is not None
    attention = _attention_event(runtime, worldline_id, "wu-sangui")

    assert advanced["tick"] == 2
    assert any(
        item.get("message_id") == dispatched["message"]["id"]
        for item in lifetime["knowledge"]
        if isinstance(item, dict)
    )
    assert attention["payload"] == {
        "seat": "wu-sangui",
        "new_known_event_ids": [
            next(
                event["id"]
                for event in advanced["events"]
                if event["event_type"] == "MESSAGE_DELIVERED"
            )
        ],
        "decision": "BACKGROUND",
        "reason_code": "NO_REOPEN_CONDITION",
        "trigger_event_ids": [
            next(
                event["id"]
                for event in advanced["events"]
                if event["event_type"] == "MESSAGE_DELIVERED"
            )
        ],
        "matched_dependency_ids": [],
    }
    assert not [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=2)
        if wake["actor_id"] == "wu-sangui" and wake["source"] == "v6-attention"
    ]


def test_typed_message_dependency_reopens_one_wake(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "matching-message")
    _establish_course(
        runtime,
        worldline_id,
        wu,
        [{"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}],
    )
    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="dorgon",
        recipient="wu-sangui",
        content="我方已有明确回复。",
        delivery_tick=2,
    )

    runtime.advance_one(worldline_id)
    attention = _attention_event(runtime, worldline_id, "wu-sangui")
    wakes = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=2)
        if wake["actor_id"] == "wu-sangui" and wake["source"] == "v6-attention"
    ]

    assert attention["payload"]["decision"] == "REOPEN"
    assert attention["payload"]["reason_code"] == "OPEN_DEPENDENCY_MATCH"
    assert attention["payload"]["matched_dependency_ids"] == ["await-dorgon"]
    assert len(wakes) == 1
    assert wakes[0]["wake_type"] == "OBSERVATION"
    assert wakes[0]["trigger_event_id"] == attention["id"]
    assert wakes[0]["result"]["attention"] == {
        "decision": "REOPEN",
        "reason_code": "OPEN_DEPENDENCY_MATCH",
        "trigger_event_ids": attention["payload"]["trigger_event_ids"],
        "matched_dependency_ids": ["await-dorgon"],
    }


def test_expected_operation_completion_is_known_but_background(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "expected-operation")
    _establish_course(runtime, worldline_id, wu, [])
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-attention-operation",
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "v6-attention-test",
            "trigger_event_id": "",
        }
    )
    runtime.freeze_pending_moment(worldline_id)
    runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "operate",
        {
            "operation_definition_id": "prepare_force",
            "targets": ["wu-field-force"],
            "description": "整备所部",
        },
        idempotency_key="v6-expected-operation",
    )
    runtime.commit_pending_moment(worldline_id)

    advanced = runtime.advance_one(worldline_id)
    lifetime = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert lifetime is not None
    completion = next(
        event for event in advanced["events"] if event["event_type"] == "OPERATION_COMPLETED"
    )
    attention = _attention_event(runtime, worldline_id, "wu-sangui")

    assert any(
        item.get("event_id") == completion["id"]
        for item in lifetime["knowledge"]
        if isinstance(item, dict)
    )
    assert attention["payload"]["decision"] == "BACKGROUND"
    assert attention["payload"]["reason_code"] == "NO_REOPEN_CONDITION"
    assert not [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=advanced["tick"])
        if wake["actor_id"] == "wu-sangui" and wake["source"] == "v6-attention"
    ]


def test_deadline_dependency_is_a_host_owned_attention_boundary(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "deadline")
    _establish_course(
        runtime,
        worldline_id,
        wu,
        [{"id": "review-at-three", "type": "DEADLINE", "due_tick": 3}],
    )

    advanced = runtime.advance_one(worldline_id)
    attention = _attention_event(runtime, worldline_id, "wu-sangui")

    assert advanced["tick"] == 3
    assert attention["payload"]["decision"] == "REOPEN"
    assert attention["payload"]["matched_dependency_ids"] == ["review-at-three"]
    assert any(event["event_type"] == "DECISION_DEPENDENCY_DUE" for event in advanced["events"])


def test_attention_policy_is_pure_and_requires_explicit_reopen_conditions():
    lifetime = {
        "seat": "wu-sangui",
        "plan": [
            {
                "course": "维持关口可控",
                "status": "IN_FORCE",
                "open_dependencies": [],
            }
        ],
    }

    result = evaluate_attention(
        lifetime,
        [{"event_id": "known-1", "event_type": "MESSAGE_DELIVERED", "actor_id": "li-zicheng"}],
        {"tick": 2},
    )

    assert result.decision == AttentionDecision.BACKGROUND
    assert result.reason_code == "NO_REOPEN_CONDITION"

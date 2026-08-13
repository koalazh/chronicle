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
                "course_schema_version": 1,
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


def test_structural_pressure_reaches_attention_from_the_shared_volume(app_config):
    runtime, worldline_id, _wu = _runtime(app_config, "structural-pressure")
    pending = runtime.worldline(worldline_id)["projection"]["pending_moment"]
    for wake_id in pending["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        lifetime = runtime.db.worldline_lifetime(worldline_id, wake["actor_id"])
        assert lifetime is not None
        intent = (
            {
                "type": "update_plan",
                "objective": "维持关口可控",
                "steps": ["继续核验"],
                "open_dependencies": [],
            }
            if wake["actor_id"] == "wu-sangui"
            else {"type": "wait"}
        )
        runtime.stage_intent(
            worldline_id,
            lifetime["id"],
            intent,
            source="agent",
            idempotency_key=f"v6-structural-pressure-wait-{wake_id}",
            wake_id=wake_id,
        )
    runtime.commit_pending_moment(worldline_id)

    while runtime.worldline(worldline_id)["worldline"]["current_tick"] < 5:
        advanced = runtime.advance_one(worldline_id)

    pressure = next(
        event for event in advanced["events"] if event["event_type"] == "CRISIS_PRESSURE_APPLIED"
    )
    attention = _attention_event(runtime, worldline_id, "wu-sangui")
    lifetime = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert lifetime is not None

    assert attention["payload"]["decision"] == "REOPEN"
    assert attention["payload"]["reason_code"] == "STRUCTURAL_WORLD_SHOCK"
    assert pressure["id"] in attention["payload"]["trigger_event_ids"]
    assert any(
        item.get("kind") == "structural_pressure"
        and item.get("event_id") == pressure["id"]
        for item in lifetime["knowledge"]
        if isinstance(item, dict)
    )


def test_rejected_world_action_reopens_own_consequence(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "own-consequence")
    runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "schedule_revisit",
        {"after_days": 0, "reason": ""},
        idempotency_key="v6-own-consequence-rejected",
    )

    committed = runtime.commit_pending_moment(worldline_id)
    attention = _attention_event(runtime, worldline_id, "wu-sangui")
    wakes = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=1)
        if wake["source"] == "v6-attention"
        and wake["wake_type"] == "UNEXPECTED_CONSEQUENCE"
    ]

    assert "INTENT_REJECTED" in {event["event_type"] for event in committed["events"]}
    assert attention["payload"]["decision"] == "REOPEN"
    assert attention["payload"]["reason_code"] == "OWN_CONSEQUENCE_UNEXPECTED"
    assert len(wakes) == 1


def test_attention_policy_reopens_for_each_non_course_source():
    lifetime = {
        "seat": "wu-sangui",
        "plan": [{"course_schema_version": 1, "course": "维持关口可控", "status": "IN_FORCE", "open_dependencies": []}],
    }

    structural = evaluate_attention(
        lifetime,
        [{"event_id": "pressure-1", "structural_shock": True}],
        {"tick": 5},
    )
    unexpected = evaluate_attention(
        lifetime,
        [{"event_id": "consequence-1", "actor_id": "wu-sangui", "unexpected_consequence": True}],
        {"tick": 5},
    )

    assert structural.reason_code == "STRUCTURAL_WORLD_SHOCK"
    assert unexpected.reason_code == "OWN_CONSEQUENCE_UNEXPECTED"
    assert structural.decision == unexpected.decision == AttentionDecision.REOPEN

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from chronicle.host import ChronicleHost
from chronicle.volume_live import HermesVolumeActorDriver
from chronicle.volume_runtime import VolumeRuntimeError


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-course-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-course-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-course-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return config, host, runtime, worldline_id, wu


def _establish_course(runtime, worldline_id, wu, *, objective: str = "维持关口可控"):
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": objective,
            "steps": ["核验来信", "保留选择"],
            "rationale": "现有来信不足以作出最终承诺",
            "open_dependencies": [
                {
                    "id": "await-dorgon-reply",
                    "type": "MESSAGE_FROM",
                    "actor_id": "dorgon",
                },
                {"id": "review-at-four", "type": "DEADLINE", "due_tick": 4},
            ],
        },
        source="agent",
        idempotency_key="v6-establish-course",
    )
    return runtime.commit_pending_moment(worldline_id)


def _queue_wu_wake(runtime, worldline_id, wu, suffix: str):
    tick = runtime.db.worldline(worldline_id)["current_tick"]
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v6-course-wake:{suffix}",
            "worldline_id": worldline_id,
            "actor_id": wu["id"],
            "wake_type": "OBSERVATION",
            "tick": tick,
            "status": "QUEUED",
            "source": "v6-decision-horizon-test",
            "trigger_event_id": "",
        }
    )


def test_current_course_is_single_typed_and_ledger_backed(app_config):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, "establish")

    committed = _establish_course(runtime, worldline_id, wu)
    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None
    course = lifetime["plan"][0]
    horizon = next(
        event
        for event in committed["events"]
        if event["event_type"] == "DECISION_HORIZON_ESTABLISHED"
    )

    assert len(lifetime["plan"]) == 1
    assert course["course"] == "维持关口可控"
    assert course["status"] == "IN_FORCE"
    assert course["established_tick"] == 1
    assert course["established_event_id"] == horizon["id"]
    assert course["last_deliberated_tick"] == 1
    assert course["last_deliberated_event_id"] == horizon["id"]
    assert course["open_dependencies"] == [
        {"id": "await-dorgon-reply", "type": "MESSAGE_FROM", "actor_id": "dorgon"},
        {"id": "review-at-four", "type": "DEADLINE", "due_tick": 4},
    ]
    assert horizon["payload"]["course"] == course
    assert any(event["event_type"] == "PLAN_UPDATED" for event in committed["events"])
    assert runtime.lifetime_context(worldline_id, wu["id"])["current_course"] == course


def test_current_course_survives_tick_restart_controller_switch_and_fresh_perspective(app_config):
    config, host, runtime, worldline_id, wu = _runtime(app_config, "continuity")
    _establish_course(runtime, worldline_id, wu)
    before = copy.deepcopy(runtime.db.worldline_lifetime(worldline_id, wu["seat"])["plan"][0])

    runtime.advance_one(worldline_id)
    host.worldline_runtime.inhabit(worldline_id, wu["id"])
    host.worldline_runtime.leave(worldline_id)
    restarted = ChronicleHost(config).volume_runtime
    after = restarted.db.worldline_lifetime(worldline_id, wu["seat"])
    assert after is not None
    assert after["plan"] == [before]

    _queue_wu_wake(restarted, worldline_id, after, "fresh-session")
    frozen = restarted.freeze_pending_moment(worldline_id)
    wake = restarted.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    assert wake["frozen_perspective"]["context"]["current_course"] == before
    fresh_session_payload = json.loads(
        HermesVolumeActorDriver(config, restarted.db)._messages(
            wake, wake["frozen_perspective"]
        )[1]["content"]
    )
    assert fresh_session_payload["frozen_perspective"]["context"]["current_course"] == before


def test_current_course_revision_replaces_the_projection_and_keeps_ledger_history(app_config):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, "revision")
    _establish_course(runtime, worldline_id, wu)
    original = runtime.db.worldline_lifetime(worldline_id, wu["seat"])["plan"][0]
    _queue_wu_wake(runtime, worldline_id, wu, "revision")
    runtime.freeze_pending_moment(worldline_id)

    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "等待明确条件后再决定通行",
            "steps": ["核验新条件"],
            "open_dependencies": [
                {"id": "offer-change", "type": "OFFER_CHANGE", "offer_id": "offer-1"}
            ],
        },
        source="agent",
        idempotency_key="v6-revise-course",
    )
    committed = runtime.commit_pending_moment(worldline_id)
    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None
    revised = lifetime["plan"][0]
    horizon_events = [
        event
        for event in runtime.db.worldline_events(worldline_id)
        if event["event_type"].startswith("DECISION_HORIZON_")
    ]
    revised_event = next(
        event
        for event in committed["events"]
        if event["event_type"] == "DECISION_HORIZON_REVISED"
    )

    assert len(lifetime["plan"]) == 1
    assert revised["course"] == "等待明确条件后再决定通行"
    assert revised["established_event_id"] == revised_event["id"]
    assert revised_event["payload"]["previous_course_event_id"] == original[
        "established_event_id"
    ]
    assert [event["event_type"] for event in horizon_events] == [
        "DECISION_HORIZON_ESTABLISHED",
        "DECISION_HORIZON_REVISED",
    ]


def test_legacy_v5_plan_is_read_as_a_current_course_without_mutating_it(app_config):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, "legacy-read")
    legacy = {
        "version": "legacy-plan",
        "objective": "暂缓定论",
        "steps": ["继续核验"],
        "rationale": "旧记录",
        "reconsider_when": ["收到回信"],
        "updated_tick": 1,
    }
    runtime.db.update_worldline_lifetime(
        worldline_id,
        wu["seat"],
        plan_json=json.dumps([legacy], ensure_ascii=False, sort_keys=True),
    )

    context = runtime.lifetime_context(worldline_id, wu["id"])
    stored = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert stored is not None

    assert stored["plan"] == [legacy]
    assert context["current_course"] == {
        **legacy,
        "course_schema_version": 1,
        "course": "暂缓定论",
        "status": "IN_FORCE",
        "established_tick": 1,
        "established_event_id": "",
        "open_dependencies": [],
        "explicit_rationale": "旧记录",
        "evidence_event_ids": [],
        "last_deliberated_tick": 1,
        "last_deliberated_event_id": "",
    }


def test_open_dependencies_are_typed_and_reject_free_form_predicates(app_config):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, "typed-dependencies")

    with pytest.raises(VolumeRuntimeError, match="unsupported fields"):
        runtime.stage_intent(
            worldline_id,
            wu["id"],
            {
                "type": "update_plan",
                "objective": "等待回应",
                "steps": ["暂不行动"],
                "open_dependencies": [
                    {
                        "type": "MESSAGE_FROM",
                        "actor_id": "dorgon",
                        "predicate": "if Dorgon changes his mind",
                    }
                ],
            },
            source="agent",
        )

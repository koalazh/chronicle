from __future__ import annotations

import copy
from dataclasses import replace

from chronicle.host import ChronicleHost


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
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return runtime, worldline_id, wu


def test_volume_world_tools_share_one_atomic_moment_and_are_idempotent(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "world-tools")

    first = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "investigate",
        {
            "question": "核验关口态势",
            "target": "shanhai-pass",
            "method": "courier_report",
        },
        idempotency_key="investigate-once",
    )
    repeated = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "investigate",
        {
            "question": "核验关口态势",
            "target": "shanhai-pass",
            "method": "courier_report",
        },
        idempotency_key="investigate-once",
    )

    assert first["status"] == "accepted"
    assert repeated["idempotent"] is True
    wake_id = first["operation"]["wake_id"]
    assert len(runtime.db.crisis_wake_operations(wake_id)) == 1

    committed = runtime.commit_pending_moment(worldline_id)
    event_types = [event["event_type"] for event in committed["events"]]
    assert event_types == ["INTENT_COMMITTED", "INVESTIGATION_STARTED", "MOMENT_COMMITTED"]
    assert runtime.commit_pending_moment(worldline_id)["idempotent"] is True

    advanced = runtime.advance_one(worldline_id)
    assert advanced["tick"] == 3
    assert {event["event_type"] for event in advanced["events"]} >= {
        "INVESTIGATION_COMPLETED",
        "OBSERVATION_OBTAINED",
    }
    investigation = runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "before-shanhaiguan"
    ]["investigations"][0]
    assert investigation["status"] == "COMPLETED"


def test_volume_wake_id_routes_tools_to_the_exact_duplicate_subject_wake(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "world-tools-exact-wake")
    snapshot = runtime.db.worldline_snapshot(worldline_id, 1)
    assert snapshot is not None
    pending = snapshot["projection"]["pending_moment"]
    first_wake_id = pending["wake_ids"][0]
    exact_wake_id = f"{worldline_id}:duplicate-wu-wake"
    runtime.db.create_subject_wake(
        {
            "id": exact_wake_id,
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "trigger_event_id": "duplicate-wu-trigger",
            "frozen_perspective": pending,
        }
    )
    projection = copy.deepcopy(snapshot["projection"])
    projection["pending_moment"]["wake_ids"].append(exact_wake_id)
    runtime.db.append_worldline_snapshot(
        worldline_id,
        1,
        int(snapshot["ledger_cursor"]) + 1,
        projection,
    )

    tool = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "operate",
        {
            "operation_definition_id": "prepare_force",
            "targets": ["wu-field-force"],
            "description": "只写入指定的重复 Wake",
        },
        idempotency_key="exact-wake-tool",
        wake_id=exact_wake_id,
    )
    intent = runtime.stage_intent(
        worldline_id,
        wu["id"],
        {"type": "wait"},
        source="agent",
        idempotency_key="exact-wake-intent",
        wake_id=first_wake_id,
    )

    assert tool["operation"]["wake_id"] == exact_wake_id
    assert intent["operation"]["wake_id"] == first_wake_id


def test_volume_operation_offer_and_revisit_survive_commit(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "world-stateful-tools")

    operation = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "operate",
        {
            "operation_definition_id": "prepare_force",
            "targets": ["wu-field-force"],
            "description": "整备所部",
        },
        idempotency_key="operation-once",
    )
    runtime.commit_pending_moment(worldline_id)
    runtime.advance_one(worldline_id)
    state = runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "before-shanhaiguan"
    ]
    assert operation["status"] == "accepted"
    assert state["operations"][0]["status"] == "COMPLETED"
    assert state["entities"]["wu-field-force"]["state"] == "READY"

    runtime.freeze_pending_moment(worldline_id)
    current_wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert current_wu is not None
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert dorgon is not None
    runtime.stage_intent(worldline_id, dorgon["id"], {"type": "wait"}, source="agent")
    offer = runtime.stage_actor_tool(
        worldline_id,
        current_wu["id"],
        "manage_offer",
        {
            "action": "PROPOSE",
            "recipient": "dorgon",
            "terms": [
                {"type": "passage", "subject": "shanhai-pass", "value": "permitted"}
            ],
            "message": "约定通行",
            "expires_after_days": 2,
        },
        idempotency_key="offer-once",
    )
    runtime.commit_pending_moment(worldline_id)
    state = runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "before-shanhaiguan"
    ]
    assert offer["status"] == "accepted"
    assert state["offers"][0]["status"] == "PROPOSED"
    assert runtime.next_tick(worldline_id) == runtime.worldline(worldline_id)["worldline"]["current_tick"] + 2
    advanced_offer = runtime.advance_one(worldline_id)
    assert advanced_offer["tick"] == 5
    assert any(event["event_type"] == "MESSAGE_DISPATCHED" for event in advanced_offer["events"]) is False
    assert not [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=4)
        if wake["wake_type"] == "OFFER_CHANGE"
    ]
    assert any(event["event_type"] == "MESSAGE_DELIVERED" for event in advanced_offer["events"])
    assert any(event["event_type"] == "OFFER_CHANGED" for event in advanced_offer["events"])
    offer_wakes = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=5)
        if wake["wake_type"] == "OFFER_CHANGE"
    ]
    assert len(offer_wakes) == 1

    revisit_runtime, revisit_worldline_id, revisit_wu = _runtime(
        app_config, "world-stateful-tools-revisit"
    )
    revisit = revisit_runtime.stage_actor_tool(
        revisit_worldline_id,
        revisit_wu["id"],
        "schedule_revisit",
        {"after_days": 2, "reason": "等候关口来报"},
        idempotency_key="revisit-once",
    )
    revisit_runtime.commit_pending_moment(revisit_worldline_id)
    assert revisit["status"] == "accepted"
    stored = revisit_runtime.db.worldline_lifetime(revisit_worldline_id, "wu-sangui")
    assert stored is not None
    assert stored["revisits"][0]["due_tick"] == 3


def test_volume_communication_uses_shared_northern_transport_graph(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "world-communication")

    message = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "communicate",
        {"recipient": "dorgon", "content": "关口可见态势仍需核验。"},
        idempotency_key="communication-once",
    )
    assert message["status"] == "accepted"
    assert message["arrival_tick"] == 3

    committed = runtime.commit_pending_moment(worldline_id)
    assert "MESSAGE_DISPATCHED" in [event["event_type"] for event in committed["events"]]

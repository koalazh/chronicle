from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from chronicle import world_mcp
from chronicle.app import create_app
from chronicle.host import ChronicleHost
from chronicle.world import WorldAccessError


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    frozen = runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return config, runtime, worldline_id, wu, frozen


def test_v5_message_delivery_admits_knowledge_and_queues_observation(app_config):
    _config, runtime, worldline_id, wu, _frozen = _runtime(app_config, "message-admission")

    delivered = next(
        event
        for event in runtime.db.worldline_events(worldline_id)
        if event["event_type"] == "MESSAGE_DELIVERED"
    )
    wakes = runtime.db.subject_wakes(worldline_id, tick=1)

    assert any(
        isinstance(item, dict)
        and item.get("message_id") == delivered["payload"]["message_id"]
        for item in wu["knowledge"]
    )
    assert [
        wake
        for wake in wakes
        if wake["actor_id"] == "wu-sangui"
        and wake["wake_type"] == "OBSERVATION"
        and wake["trigger_event_id"] == delivered["id"]
    ]


@pytest.mark.parametrize(
    ("tool_name", "arguments", "admission_event_type", "wake_type"),
    [
        (
            "operate",
            {
                "operation_definition_id": "prepare_force",
                "targets": ["wu-field-force"],
                "description": "整备所部",
            },
            "OPERATION_COMPLETED",
            "OPERATION_RESULT",
        ),
        (
            "investigate",
            {
                "question": "核验关口态势",
                "target": "shanhai-pass",
                "method": "courier_report",
            },
            "OBSERVATION_OBTAINED",
            "INVESTIGATION_RESULT",
        ),
    ],
)
def test_v5_completion_admits_knowledge_and_queues_result_wake(
    app_config, tool_name, arguments, admission_event_type, wake_type
):
    _config, runtime, worldline_id, wu, _frozen = _runtime(app_config, tool_name)

    staged = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        tool_name,
        arguments,
        idempotency_key=f"v6-characterize-{tool_name}",
    )
    assert staged["status"] == "accepted"
    runtime.commit_pending_moment(worldline_id)
    advanced = runtime.advance_one(worldline_id)
    admitted = next(
        event for event in advanced["events"] if event["event_type"] == admission_event_type
    )
    updated_wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert updated_wu is not None

    assert any(
        isinstance(item, dict) and item.get("event_id") == admitted["id"]
        for item in updated_wu["knowledge"]
    )
    assert [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=advanced["tick"])
        if wake["actor_id"] == "wu-sangui"
        and wake["wake_type"] == wake_type
        and wake["trigger_event_id"] == admitted["id"]
    ]


def test_v5_plan_is_a_single_current_plan_with_prose_reconsideration(app_config):
    _config, runtime, worldline_id, wu, _frozen = _runtime(app_config, "current-plan")

    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "先守住山海关的选择权",
            "steps": ["核验来信", "等待可见兵情"],
            "rationale": "当前来信尚不足以改变守关判断",
            "reconsider_when": ["出现可核验的援军动向"],
        },
        source="agent",
        idempotency_key="v6-characterize-current-plan",
    )
    runtime.commit_pending_moment(worldline_id)
    updated_wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert updated_wu is not None
    context = runtime.lifetime_context(worldline_id, updated_wu["id"])

    assert len(updated_wu["plan"]) == 1
    assert updated_wu["plan"][0]["objective"] == "先守住山海关的选择权"
    assert updated_wu["plan"][0]["reconsider_when"] == ["出现可核验的援军动向"]
    assert context["current_plan"] == updated_wu["plan"]


def test_v5_volume_mcp_rejects_a_second_write_for_the_same_wake(app_config, monkeypatch):
    config, runtime, worldline_id, wu, frozen = _runtime(app_config, "single-write")
    wake_id = frozen["pending_moment"]["wake_ids"][0]
    wake = runtime.db.crisis_wake(wake_id)
    assert wake is not None
    binding = {"worldline_id": worldline_id, "role": wu["seat"]}
    monkeypatch.setattr(
        world_mcp,
        "_volume_context",
        lambda requested_wake_id: (config, runtime.db, binding, runtime.db.crisis_wake(requested_wake_id)),
    )

    first = world_mcp._volume_tool(
        "update_plan",
        {"objective": "先核验来信", "steps": ["等待回报"]},
        "v6-characterize-first-write",
        wake_id,
    )

    assert first["status"] == "accepted"
    with pytest.raises(WorldAccessError, match="one V5 action"):
        world_mcp._volume_tool(
            "communicate",
            {"recipient": "dorgon", "content": "请确认行军态势。"},
            "v6-characterize-second-write",
            wake_id,
        )


def test_v5_continue_performs_one_global_advance_per_request(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        created = client.post("/api/worldlines", json={"live": False})
        assert created.status_code == 200
        worldline_id = created.json()["worldline"]["id"]
        host = ChronicleHost(config)
        before = sum(
            event["event_type"] == "TIME_ADVANCED"
            for event in host.db.worldline_events(worldline_id)
        )

        continued = client.post(f"/api/worldlines/{worldline_id}/continue")

        assert continued.status_code == 200
        after = sum(
            event["event_type"] == "TIME_ADVANCED"
            for event in host.db.worldline_events(worldline_id)
        )
        assert continued.json()["advanced"] is True
        assert after == before + 1

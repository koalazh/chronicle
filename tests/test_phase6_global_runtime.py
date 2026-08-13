from __future__ import annotations

from dataclasses import replace

import pytest

from chronicle.models import CrisisInstanceStatus, WorldlineStatus
from chronicle.volume_runtime import VolumeRuntimeConflict


def test_volume_runtime_uses_one_clock_for_multiple_crises(host):
    runtime = host.volume_runtime
    runtime.pack = replace(
        runtime.pack,
        world=replace(
            runtime.pack.world,
            historical_field=(
                {
                    "id": "field-global-window",
                    "tick": 2,
                    "effects": [{"subject": "global-window", "state": "OPEN"}],
                },
            ),
        ),
    )
    created = runtime.create()
    worldline_id = created["worldline"]["id"]

    assert created["worldline"]["kind"] == "VOLUME"
    assert created["worldline"]["current_tick"] == 0
    assert len(created["lifetimes"]) == 6
    assert all(
        lifetime["profile_name"] == f"chronicle-{worldline_id}-{lifetime['seat']}"
        for lifetime in created["lifetimes"]
    )
    assert {binding["binding_scope"] for binding in created["bindings"]} == {"VOLUME"}

    shanhai = runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    nanjing = runtime.activate_crisis(worldline_id, "nanjing-succession")
    assert shanhai["instance"]["status"] == CrisisInstanceStatus.ACTIVE.value
    assert nanjing["instance"]["status"] == CrisisInstanceStatus.ACTIVE.value
    projection = runtime.worldline(worldline_id)["projection"]
    assert "prepare_force" in projection["affordances"]["before-shanhaiguan"]["operations"]
    assert (
        "convene_recognition_assembly"
        in projection["affordances"]["nanjing-succession"]["operations"]
    )
    assert len(runtime.activate_crisis(worldline_id, "before-shanhaiguan")["crisis_instances"]) == 3
    assert projection["active_crisis_ids"] == ["before-shanhaiguan", "nanjing-succession"]
    assert runtime.next_tick(worldline_id) == 1

    first_step = runtime.advance_one(worldline_id)
    assert first_step["tick"] == 1
    assert [message["recipient"] for message in first_step["delivered_messages"]] == ["wu-sangui"]
    wu = next(
        lifetime
        for lifetime in runtime.db.worldline_lifetimes(worldline_id)
        if lifetime["seat"] == "wu-sangui"
    )
    assert any(
        isinstance(item, dict) and item["message_id"] == "before-shanhaiguan:letter-li-wu-opening"
        for item in wu["knowledge"]
    )
    assert len(runtime.db.subject_wakes(worldline_id, tick=1)) == 1

    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="li-zicheng",
        recipient="shi-kefa",
        content="跨危局测试消息",
        delivery_tick=2,
    )
    assert runtime.next_tick(worldline_id) == 2
    second_step = runtime.advance_one(worldline_id)
    assert second_step["tick"] == 2
    assert second_step["field_events"][0]["id"] == "field-global-window"
    assert (
        runtime.worldline(worldline_id)["projection"]["institutional_state"]["global-window"]
        == "OPEN"
    )
    assert any(message["recipient"] == "shi-kefa" for message in second_step["delivered_messages"])
    shi = runtime.db.worldline_lifetime(worldline_id, "shi-kefa")
    assert shi is not None
    assert any(
        item.get("content") == "跨危局测试消息"
        for item in shi["knowledge"]
        if isinstance(item, dict)
    )

    assert runtime.next_tick(worldline_id) == 3
    assert runtime.advance_one(worldline_id)["tick"] == 3
    assert runtime.next_tick(worldline_id) == 5
    pressure_step = runtime.advance_one(worldline_id)
    assert pressure_step["tick"] == 5
    assert pressure_step["pressures"][0]["id"] == "eastern-transit-window-narrows"

    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["crisis_instances"]["before-shanhaiguan"]["local_tick"] == 5
    assert projection["crisis_instances"]["nanjing-succession"]["local_tick"] == 5

    settled = runtime.settle_crisis(
        worldline_id,
        "before-shanhaiguan",
        outcome={"summary": "phase6 test settlement"},
    )
    assert settled["instance"]["status"] == CrisisInstanceStatus.SETTLED.value
    worldline = runtime.db.worldline(worldline_id)
    assert worldline is not None
    assert worldline["kind"] == "VOLUME"
    assert worldline["status"] == WorldlineStatus.ACTIVE.value
    assert (
        runtime.db.crisis_instances(worldline_id, status=CrisisInstanceStatus.ACTIVE.value)[0][
            "crisis_id"
        ]
        == "nanjing-succession"
    )
    assert all(binding["status"] == "ACTIVE" for binding in runtime.db.agent_bindings(worldline_id))
    assert not any(
        event["event_type"] == "RUN_SEALED" for event in runtime.db.worldline_events(worldline_id)
    )


def test_active_crisis_presence_protects_one_unresolved_knot(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.activate_crisis(worldline_id, "nanjing-succession")

    li = runtime.db.worldline_lifetime(worldline_id, "li-zicheng")
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert li is not None and wu is not None
    host.volume_runtime.inhabit(worldline_id, li["id"])
    host.volume_runtime.leave(worldline_id)

    with pytest.raises(VolumeRuntimeConflict, match="another inhabited"):
        host.volume_runtime.inhabit(worldline_id, wu["id"])

    # The parallel Crisis remains inhabitable, while the original knot is protected.
    shi = runtime.db.worldline_lifetime(worldline_id, "shi-kefa")
    assert shi is not None
    host.volume_runtime.inhabit(worldline_id, shi["id"])
    host.volume_runtime.leave(worldline_id)

    runtime.settle_crisis(worldline_id, "before-shanhaiguan")
    eligibility = host.volume_runtime.presence_eligibility(worldline_id, wu["id"])
    assert eligibility["allowed"] is False
    assert eligibility["reason_code"] == "NO_CURRENT_QUESTION"
    with pytest.raises(VolumeRuntimeConflict, match="not part of a current"):
        host.volume_runtime.inhabit(worldline_id, wu["id"])


def test_global_clock_queues_offscreen_wake_without_inventing_agent_intent(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")

    advanced = runtime.advance_one(worldline_id)

    assert advanced["tick"] == 1
    wakes = runtime.db.subject_wakes(worldline_id, tick=1)
    assert [wake["actor_id"] for wake in wakes] == ["wu-sangui"]
    assert wakes[0]["status"] == "QUEUED"
    assert not any(
        event["event_type"] == "INTENT_COMMITTED"
        for event in runtime.db.worldline_events(worldline_id)
    )

from __future__ import annotations

import pytest

from chronicle.volume_runtime import VolumeRuntimeConflict

pytestmark = pytest.mark.skip(
    reason="历史南方/南京 braided-volume 范围已从当前产品收敛"
)


def test_phase9_southern_knot_waits_for_shared_political_center(host):
    pack = host.volume_runtime.pack

    assert {reference.id for reference in pack.volume.crises} == {
        "before-shanhaiguan",
        "nanjing-succession",
        "southern-consolidation",
    }
    assert "yangzhou" in pack.world.location_by_id
    southern = pack.pack("southern-consolidation")
    assert southern.assertion_by_id["s001"].source_ids
    assert "jiangbei-mandate" in southern.entity_by_id
    assert "shi-kefa-leverage" not in southern.entity_by_id
    assert "nanjing-political-center" in {entity.id for entity in pack.world.entities}

    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.settle_crisis(
        worldline_id,
        "nanjing-succession",
        outcome={"summary": "南京定策已经留下后续江北安排问题"},
    )
    with pytest.raises(VolumeRuntimeConflict, match="nanjing-political-center"):
        runtime.activate_crisis(worldline_id, "southern-consolidation")
    projection = runtime.worldline(worldline_id)["projection"]
    assert "southern-consolidation" not in projection["active_crisis_ids"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "UNFORMED"


def test_phase9_north_south_bridge_is_silent_without_world_position_change(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.settle_crisis(
        worldline_id,
        "nanjing-succession",
        outcome={"summary": "南京定策已经留下后续江北安排问题"},
    )

    applied = None
    while runtime.worldline(worldline_id)["worldline"]["current_tick"] < 9:
        applied = runtime.advance_one(worldline_id)

    assert applied is not None
    assert applied["tick"] == 9
    assert applied["field_events"][0]["id"] == "north-south-recognition-bridge"
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "UNFORMED"
    dispatches = [
        event for event in applied["events"] if event["event_type"] == "MESSAGE_DISPATCHED"
    ]
    assert dispatches == []

    delivered = runtime.advance_one(worldline_id)
    assert delivered["tick"] == 9
    assert delivered["advanced"] is False
    assert delivered["delivered_messages"] == []

    events = runtime.db.worldline_events(worldline_id)
    bridge_dispatches = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    ]
    bridge_deliveries = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DELIVERED"
        and event["payload"].get("source") == "historical_field"
    ]
    assert bridge_dispatches == []
    assert bridge_deliveries == []

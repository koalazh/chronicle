from __future__ import annotations

from chronicle.models import CrisisInstanceStatus


def test_phase9_adds_a_southern_knot_with_present_leverage(host):
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

    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.settle_crisis(
        worldline_id,
        "nanjing-succession",
        outcome={"summary": "南京定策已经留下后续江北安排问题"},
    )
    activated = runtime.activate_crisis(worldline_id, "southern-consolidation")

    assert activated["instance"]["status"] == CrisisInstanceStatus.ACTIVE.value
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["active_crisis_ids"] == ["southern-consolidation"]
    assert (
        projection["crisis_instances"]["southern-consolidation"]["entities"]["shi-kefa-leverage"][
            "state"
        ]
        == "PRESENT"
    )


def test_phase9_north_south_bridge_delivers_public_record_to_southern_lifetimes(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.activate_crisis(worldline_id, "southern-consolidation")

    applied = None
    while runtime.worldline(worldline_id)["worldline"]["current_tick"] < 9:
        applied = runtime.advance_one(worldline_id)

    assert applied is not None
    assert applied["tick"] == 9
    assert applied["field_events"][0]["id"] == "north-south-recognition-bridge"
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["north-affairs-recognition"]["state"] == "AVAILABLE"
    dispatches = [
        event for event in applied["events"] if event["event_type"] == "MESSAGE_DISPATCHED"
    ]
    assert len(dispatches) == 3
    assert all(event["provenance"] == "historical" for event in dispatches)
    assert all(event["payload"]["assertion_ids"] == ["n013"] for event in dispatches)

    delivered = runtime.advance_one(worldline_id)
    assert delivered["tick"] == 10
    assert {message["recipient"] for message in delivered["delivered_messages"]} == {
        "shi-kefa",
        "ma-shiying",
        "han-zanzhou",
    }
    content = "沿线公开文书传入南京：山海关方向的战事与清军入关消息已进入可核验的北方军情记录；它说明北方秩序正在重排，但没有替南方裁定继统或江北安排。"
    for seat in ("shi-kefa", "ma-shiying", "han-zanzhou"):
        lifetime = runtime.db.worldline_lifetime(worldline_id, seat)
        assert lifetime is not None
        assert any(
            isinstance(item, dict)
            and item.get("content") == content
            and item.get("source") == "historical_field"
            and item.get("assertion_ids") == ["n013"]
            for item in lifetime["knowledge"]
        )
        context = runtime.lifetime_context(worldline_id, seat)
        assert any(item.get("content") == content for item in context["relevant_evidence"])

    events = runtime.db.worldline_events(worldline_id)
    bridge_dispatches = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("assertion_ids") == ["n013"]
    ]
    bridge_deliveries = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DELIVERED"
        and event["payload"].get("assertion_ids") == ["n013"]
    ]
    assert len(bridge_dispatches) == 3
    assert len(bridge_deliveries) == 3

from __future__ import annotations

from chronicle.product_projection import ProductProjection


def test_archive_history_coalesces_public_consequences_with_actor_attribution(host):
    projection = ProductProjection(host, lambda _active, _worldline_id: {})
    events = [
        {
            "id": "operation-completed",
            "tick": 3,
            "event_type": "OPERATION_COMPLETED",
            "payload": {
                "operation": {
                    "id": "operation-1",
                    "definition_id": "make_fu_backing_visible",
                    "actor_id": "ma-shiying",
                },
                "visibility": ["shi-kefa", "ma-shiying", "han-zanzhou"],
            },
        },
        {
            "id": "operation-state-change",
            "tick": 3,
            "event_type": "ENTITY_STATE_CHANGED",
            "causal_parent_ids": ["operation-completed"],
            "payload": {
                "operation_id": "operation-1",
                "crisis_id": "nanjing-succession",
                "entity_id": "jiangbei-military-backing",
                "after": "FU_BACKED",
                "visibility": ["shi-kefa", "ma-shiying", "han-zanzhou"],
            },
        },
        {
            "id": "delivery-shi",
            "tick": 9,
            "event_type": "MESSAGE_DELIVERED",
            "payload": {
                "source": "historical_field",
                "content": "北方军情进入南京",
                "recipient": "shi-kefa",
                "crisis_id": "nanjing-succession",
            },
        },
        {
            "id": "delivery-ma",
            "tick": 9,
            "event_type": "MESSAGE_DELIVERED",
            "payload": {
                "source": "historical_field",
                "content": "北方军情进入南京",
                "recipient": "ma-shiying",
                "crisis_id": "nanjing-succession",
            },
        },
        {
            "id": "public-pressure",
            "tick": 10,
            "event_type": "CRISIS_PRESSURE_APPLIED",
            "payload": {
                "crisis_id": "nanjing-succession",
                "pressure": {
                    "title": "留都制度真空收紧",
                    "visibility": "PUBLIC",
                },
            },
        },
        {
            "id": "sealed",
            "tick": 12,
            "event_type": "VOLUME_SEALED",
            "payload": {},
        },
    ]

    beats = projection.history_beats(events)

    action_beats = [item for item in beats if item["kind"] == "行动"]
    record_beats = [item for item in beats if item["kind"] == "公共记录"]
    assert len(action_beats) == 1
    assert "马士英" in action_beats[0]["text"]
    assert "一项行动留下了" not in action_beats[0]["text"]
    assert action_beats[0]["actor"]["display_name"] == "马士英"
    assert len(record_beats) == 1
    assert record_beats[0]["recipients"] == ["史可法", "马士英"]
    pressure_beats = [item for item in beats if item["kind"] == "外部现实"]
    assert len(pressure_beats) == 1
    assert pressure_beats[0]["text"] == "留都制度真空收紧"
    assert pressure_beats[0]["actor"] == {
        "id": "external-reality",
        "display_name": "外部现实",
    }
    assert not any(item["id"] == "sealed" for item in beats)


def test_follow_and_replay_filter_runtime_lifecycle_and_limit_public_consequences(
    host, monkeypatch
):
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    projection = ProductProjection(host, lambda active, identifier: active.db.worldline(identifier))
    participants = sorted(host.volume_runtime.pack.pack("nanjing-succession").participant_ids)

    def operation(event_id: str, tick: int) -> dict[str, object]:
        return {
            "id": event_id,
            "tick": tick,
            "event_type": "OPERATION_COMPLETED",
            "seat_id": "ma-shiying",
            "payload": {
                "operation": {
                    "id": event_id,
                    "crisis_id": "nanjing-succession",
                    "definition_id": "make_fu_backing_visible",
                    "actor_id": "ma-shiying",
                },
                "visibility": participants,
            },
        }

    events = [
        {
            "id": "activation",
            "tick": 1,
            "event_type": "CRISIS_ACTIVATED",
            "payload": {"crisis_id": "nanjing-succession"},
        },
        {"id": "field", "tick": 2, "event_type": "FIELD_EVENT_APPLIED", "payload": {}},
        {"id": "inhabited", "tick": 3, "event_type": "LIFETIME_INHABITED", "payload": {}},
        {"id": "moment", "tick": 4, "event_type": "MOMENT_COMMITTED", "payload": {}},
        {"id": "sealed", "tick": 5, "event_type": "VOLUME_SEALED", "payload": {}},
        *[operation(f"operation-{index}", index + 6) for index in range(5)],
    ]
    monkeypatch.setattr(host.db, "worldline_events", lambda _worldline_id: events)

    follow = projection.public_follow(worldline_id, "ma-shiying")
    assert len(follow["trace"]) == 4
    assert [item["id"] for item in follow["trace"]] == [
        "operation-1",
        "operation-2",
        "operation-3",
        "operation-4",
    ]
    assert all(item["type"] == "ACTION" for item in follow["trace"])
    assert all(item["actor"]["display_name"] == "马士英" for item in follow["trace"])
    assert not any(
        item["event_type"].startswith(("CRISIS_", "LIFETIME_", "MOMENT_"))
        or item["event_type"] in {"FIELD_EVENT_APPLIED", "VOLUME_SEALED"}
        for item in events
        if item["id"] in {trace["id"] for trace in follow["trace"]}
    )

    for event in events[:5]:
        assert projection.public_replay_event(event) is None
        assert projection.lifetime_replay_event(event, "ma-shiying") is None

    public_reality = {
        "id": "public-reality",
        "tick": 12,
        "event_type": "ENTITY_STATE_CHANGED",
        "payload": {
            "crisis_id": "nanjing-succession",
            "entity_id": "nanjing-recognition",
            "after": "URGENT",
            "visibility": "PUBLIC",
        },
    }
    assert projection.public_replay_event(public_reality)["actor"] == {
        "id": "external-reality",
        "display_name": "外部现实",
    }


def test_judgment_consequences_are_typed_readable_and_actor_attributed(host):
    projection = ProductProjection(host, lambda _active, _worldline_id: {})
    participants = sorted(host.volume_runtime.pack.pack("nanjing-succession").participant_ids)
    events = [
        {
            "id": "horizon",
            "tick": 1,
            "event_type": "DECISION_HORIZON_ESTABLISHED",
            "seat_id": "ma-shiying",
            "payload": {"seat": "ma-shiying", "course": {"course": "先稳住南京"}},
        },
        {
            "id": "operation",
            "tick": 2,
            "event_type": "OPERATION_COMPLETED",
            "seat_id": "ma-shiying",
            "payload": {
                "operation": {
                    "crisis_id": "nanjing-succession",
                    "definition_id": "make_fu_backing_visible",
                    "actor_id": "ma-shiying",
                },
                "visibility": participants,
            },
        },
        {"id": "field", "tick": 3, "event_type": "FIELD_EVENT_APPLIED", "payload": {}},
        {"id": "moment", "tick": 4, "event_type": "MOMENT_COMMITTED", "payload": {}},
        {"id": "sealed", "tick": 5, "event_type": "VOLUME_SEALED", "payload": {}},
    ]

    history = projection.judgment_history({"seat": "ma-shiying"}, events)

    assert history[0]["consequences"] == [
        {
            "type": "ACTION",
            "kind": "行动",
            "text": "马士英一项行动已经完成。",
            "actor": {"id": "ma-shiying", "display_name": "马士英"},
            "actors": [{"id": "ma-shiying", "display_name": "马士英"}],
        }
    ]

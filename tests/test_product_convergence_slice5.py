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
    assert not any(item["id"] == "sealed" for item in beats)

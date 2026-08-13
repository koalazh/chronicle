from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntimeConflict


def test_product_reads_fail_closed_when_volume_content_identity_drifts(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        created = client.post("/api/worldlines", json={"live": False})
        assert created.status_code == 200
        worldline_id = created.json()["worldline"]["id"]

        host = ChronicleHost(config)
        before_events = host.db.worldline_events(worldline_id)
        before_snapshot = host.db.worldline_snapshot(worldline_id, 0)["projection"]
        with host.db.transaction() as connection:
            connection.execute(
                "UPDATE worldlines SET volume_content_version = ? WHERE id = ?",
                (1, worldline_id),
            )

        for path in (
            f"/api/worldlines/{worldline_id}/world",
            "/api/worldlines/active",
        ):
            response = client.get(path)
            assert response.status_code == 409
            assert response.json()["detail"] == (
                "这份卷册由不同版本的内容创建，当前版本无法可靠回放。"
            )

        assert host.db.worldline_events(worldline_id) == before_events
        assert host.db.worldline_snapshot(worldline_id, 0)["projection"] == before_snapshot


def test_presence_eligibility_is_the_product_read_contract(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        host = ChronicleHost(config)
        available = host.volume_runtime.presence_eligibility(worldline_id, "wu-sangui")
        assert available["allowed"] is True
        assert available["reason_code"] == "AVAILABLE"

        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "li-zicheng"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/leave").status_code == 200

        locked = host.volume_runtime.presence_eligibility(worldline_id, "wu-sangui")
        assert locked["allowed"] is False
        assert locked["reason_code"] == "ACTIVE_CRISIS_PRESENCE_LOCK"
        follow = client.get(f"/api/worldlines/{worldline_id}/follow/wu-sangui")
        assert follow.status_code == 200
        assert follow.json()["lifetime"]["available"] is False
        assert "另一个人的位置" in follow.json()["lifetime"]["availability_reasons"][0]


def test_voluntary_reconsideration_is_one_per_lifetime_and_tick(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待可核验的消息"},
        ).status_code == 200

        host = ChronicleHost(config)
        runtime = host.volume_runtime
        opened = runtime.open_voluntary_reconsideration(worldline_id, "wu-sangui")
        wake_id = opened["pending_moment"]["wake_ids"][0]
        runtime.stage_deliberation(
            worldline_id,
            "wu-sangui",
            {"outcome": "HOLD", "world_actions": []},
            source="human",
            wake_id=wake_id,
        )
        runtime.commit_pending_moment(worldline_id)

        with pytest.raises(VolumeRuntimeConflict, match="这一刻已经重新判断过"):
            runtime.open_voluntary_reconsideration(worldline_id, "wu-sangui")

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_v5_product_shell_creates_one_braided_volume_and_public_world(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))

    created = client.post("/api/worldlines", json={"live": False})

    assert created.status_code == 200
    payload = created.json()
    worldline = payload["worldline"]
    assert worldline["kind"] == "VOLUME"
    assert len(payload["world"]["active_knots"]) == 3
    assert {item["display_name"] for item in payload["lifetimes"]["lifetimes"]} == {
        "吴三桂",
        "史可法",
        "多尔衮",
        "马士英",
        "韩赞周",
        "李自成",
    }

    world = client.get(f"/api/worldlines/{worldline['id']}/world")
    assert world.status_code == 200
    assert not _keys(world.json()) & {
        "knowledge",
        "beliefs",
        "plan",
        "controller",
        "profile_name",
        "runtime_epoch",
    }


def test_v5_product_shell_derives_private_desk_and_keeps_follow_public(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))
    worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]

    assert client.get(f"/api/worldlines/{worldline_id}/desk").status_code == 409
    follow = client.get(f"/api/worldlines/{worldline_id}/follow/wu-sangui")
    assert follow.status_code == 200
    assert not _keys(follow.json()) & {"knowledge", "beliefs", "plan", "controller"}

    inhabited = client.post(
        f"/api/worldlines/{worldline_id}/inhabit",
        json={"lifetime_id": "wu-sangui"},
    )
    assert inhabited.status_code == 200
    assert next(
        item for item in inhabited.json()["world"]["people"] if item["id"] == "wu-sangui"
    )["inhabited"] is True
    desk = client.get(f"/api/worldlines/{worldline_id}/desk")
    assert desk.status_code == 200
    assert {"arrivals", "known", "uncertainty", "current_plan", "active_obligations"} <= set(
        desk.json()["desk"]
    )

    continued = client.post(f"/api/worldlines/{worldline_id}/continue")
    assert continued.status_code == 200
    if continued.json().get("pending_moment"):
        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"intent": {"type": "wait"}},
        )
        assert decided.status_code == 200

    left = client.post(f"/api/worldlines/{worldline_id}/leave")
    assert left.status_code == 200
    assert left.json()["worldline"]["inhabited_lifetime_id"] == ""


def test_v5_product_shell_resolves_handoff_moment_before_continuing(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))
    worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]

    assert client.post(
        f"/api/worldlines/{worldline_id}/inhabit",
        json={"lifetime_id": "wu-sangui"},
    ).status_code == 200
    waiting = client.post(f"/api/worldlines/{worldline_id}/continue")
    assert waiting.status_code == 200
    assert waiting.json()["pending_moment"]

    left = client.post(f"/api/worldlines/{worldline_id}/leave")
    assert left.status_code == 200

    resumed = client.post(f"/api/worldlines/{worldline_id}/continue")

    assert resumed.status_code == 200
    assert resumed.json().get("pending_moment") is None
    assert resumed.json()["worldline"]["current_tick"] == 3


def test_v5_product_shell_keeps_fixture_creation_dev_only(app_config):
    client = TestClient(create_app(app_config))

    response = client.post("/api/worldlines", json={"live": False})

    assert response.status_code == 409
    assert "开发模式" in response.json()["detail"]


def test_live_volume_start_materializes_lifetimes_before_returning(app_config, monkeypatch):
    calls: dict[str, Any] = {}

    def fake_materialize(config, worldline_id, lifetimes, **kwargs):
        calls["worldline_id"] = worldline_id
        calls["lifetime_ids"] = [item["id"] for item in lifetimes]
        calls["kwargs"] = kwargs
        return {
            item["id"]: {
                "profile": f"chronicle-{worldline_id}-{item['id']}",
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{item['id']}",
            }
            for item in lifetimes
        }

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    created = ChronicleHost(app_config).volume_runtime.create(runtime_mode="live")

    assert set(calls["lifetime_ids"]) == {
        "dorgon",
        "han-zanzhou",
        "li-zicheng",
        "ma-shiying",
        "shi-kefa",
        "wu-sangui",
    }
    assert created["profile_records"]
    assert calls["kwargs"]["volume_id"] == "jiashen"

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


def test_v6_product_shell_creates_one_braided_volume_and_public_world(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))

    created = client.post("/api/worldlines", json={"live": False})

    assert created.status_code == 200
    payload = created.json()
    worldline = payload["worldline"]
    assert worldline["kind"] == "VOLUME"
    assert len(payload["world"]["open_questions"]) == 2
    assert {
        question["id"] for question in payload["world"]["open_questions"]
    } == {"before-shanhaiguan", "nanjing-succession"}
    assert {
        participant["display_name"]
        for question in payload["world"]["open_questions"]
        for participant in question["participants"]
    } == {
        "吴三桂",
        "史可法",
        "多尔衮",
        "马士英",
        "韩赞周",
        "李自成",
    }
    assert payload["world"]["present_reality"] == []
    assert payload["world"]["current_life"] is None
    assert payload["world"]["continuation"] == {"status": "available"}
    assert "lifetimes" not in payload
    assert not {"active_knots", "people", "public_facts"} & set(payload["world"])

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
    assert world.json()["present_reality"] == []
    assert not {"active_knots", "people", "public_facts"} & set(world.json())
    assert client.get(f"/api/worldlines/{worldline['id']}/lifetimes").status_code == 404


def test_v6_product_shell_derives_private_desk_and_keeps_follow_public(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))
    worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]

    assert client.get(f"/api/worldlines/{worldline_id}/desk").status_code == 409
    follow = client.get(f"/api/worldlines/{worldline_id}/follow/wu-sangui")
    assert follow.status_code == 200
    assert not _keys(follow.json()) & {"knowledge", "beliefs", "plan", "controller"}
    follow_text = str(follow.json()["trace"])
    assert "c002" not in follow_text
    assert "c003" not in follow_text

    inhabited = client.post(
        f"/api/worldlines/{worldline_id}/inhabit",
        json={"lifetime_id": "wu-sangui"},
    )
    assert inhabited.status_code == 200
    assert inhabited.json()["world"]["current_life"]["id"] == "wu-sangui"
    assert inhabited.json()["world"]["current_life"]["inhabited"] is True
    desk = client.get(f"/api/worldlines/{worldline_id}/desk")
    assert desk.status_code == 200
    desk_fields = set(desk.json()["desk"])
    assert {
        "uncertainty",
        "current_course",
        "since_last_deliberation",
        "why_now",
        "binding_reality",
        "reconsideration",
    } <= desk_fields
    assert not {
        "arrivals",
        "known",
        "current_plan",
        "active_obligations",
        "position",
        "role",
    } & desk_fields
    desk_payload = desk.json()
    desk_text = str(desk_payload)
    assert "c002" not in desk_text
    assert "c003" not in desk_text
    assert "c010" not in desk_text
    assert desk_payload["desk"]["since_last_deliberation"] == []
    assert any(item["text"].startswith("你现在在山海关") for item in desk_payload["desk"]["binding_reality"])

    continued = client.post(f"/api/worldlines/{worldline_id}/continue")
    assert continued.status_code == 200
    if continued.json().get("pending_moment"):
        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "WAIT", "text": ""},
        )
        assert decided.status_code == 200

    left = client.post(f"/api/worldlines/{worldline_id}/leave")
    assert left.status_code == 200
    assert left.json()["worldline"]["inhabited_lifetime_id"] == ""


def test_product_world_reports_when_no_automatic_trigger_remains(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        result = None
        for _ in range(4):
            result = client.post(f"/api/worldlines/{worldline_id}/continue").json()
            if result["continue_status"] == "no_future_trigger":
                break

        assert result is not None
        assert result["continue_status"] == "no_future_trigger"
        world = client.get(f"/api/worldlines/{worldline_id}/world").json()
        assert world["continuation"] == {"status": "no_future_trigger"}


def test_v6_product_shell_continues_after_agent_handoff(app_config):
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
    assert resumed.json()["worldline"]["current_tick"] > 1
    assert resumed.json()["advanced_ticks"] > 0


def test_v6_product_shell_keeps_fixture_creation_dev_only(app_config):
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

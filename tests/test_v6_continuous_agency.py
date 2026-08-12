from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


def test_continue_stops_at_human_attention_after_agent_time_is_compressed(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        first = client.post(f"/api/worldlines/{worldline_id}/continue")
        assert first.status_code == 200
        assert first.json()["pending_moment"]

        established = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={
                "intent": {
                    "outcome": "REVISE",
                    "course": {
                        "summary": "暂不作最终归属，继续维持关口可控",
                        "steps": ["守住关口", "等清方明确回复"],
                    },
                    "open_dependencies": [
                        {"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}
                    ],
                    "world_actions": [],
                }
            },
        )
        assert established.status_code == 200
        assert established.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
            "暂不作最终归属"
        )

        host = ChronicleHost(config)
        row = host.db.worldline(worldline_id)
        assert row is not None
        current_tick = int(row["current_tick"])
        host.volume_runtime.dispatch_message(
            worldline_id,
            crisis_id="before-shanhaiguan",
            sender="dorgon",
            recipient="wu-sangui",
            content="清方终于给出明确回复。",
            delivery_tick=current_tick + 1,
        )
        assert client.post(f"/api/worldlines/{worldline_id}/leave").status_code == 200
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200

        continued = client.post(f"/api/worldlines/{worldline_id}/continue")

        assert continued.status_code == 200
        payload = continued.json()
        assert payload["advanced_ticks"] == 1
        assert payload["continue_status"] == "human_judgment"
        assert payload["pending_moment"]
        desk = client.get(f"/api/worldlines/{worldline_id}/desk").json()["desk"]
        assert desk["why_now"]["open"] is True
        assert desk["why_now"]["facts"]


def test_human_can_reconsider_at_current_tick_without_advancing_or_hermes(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()["pending_moment"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"text": "先守住关口，暂不作最终归属"},
        ).status_code == 200

        before = ChronicleHost(config).db.worldline(worldline_id)
        assert before is not None
        before_tick = int(before["current_tick"])
        before_time_advances = sum(
            event["event_type"] == "TIME_ADVANCED"
            for event in ChronicleHost(config).db.worldline_events(worldline_id)
        )
        left = client.post(f"/api/worldlines/{worldline_id}/leave")
        assert left.status_code == 200
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200

        reconsidered = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"text": "现在改为先核验关口边界"},
        )

        assert reconsidered.status_code == 200
        payload = reconsidered.json()
        assert payload["worldline"]["current_tick"] == before_tick
        assert payload["desk"]["desk"]["current_course"][0]["text"].startswith(
            "现在改为先核验"
        )
        events = ChronicleHost(config).db.worldline_events(worldline_id)
        assert sum(event["event_type"] == "TIME_ADVANCED" for event in events) == before_time_advances


def test_life_desk_projects_v6_judgment_sections_without_internal_terms(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()["worldline"]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()["pending_moment"]
        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"text": "暂时守住关口，等待明确回复"},
        )
        assert decided.status_code == 200

        desk = client.get(f"/api/worldlines/{worldline_id}/desk")
        assert desk.status_code == 200
        projected = desk.json()["desk"]
        assert {
            "current_course",
            "since_last_deliberation",
            "why_now",
            "binding_reality",
            "reconsideration",
        } <= set(projected)
        assert projected["reconsideration"]["prompt"] == "现在还这样办吗？"
        projected_text = str(projected)
        assert not any(
            term in projected_text
            for term in ("Decision Horizon", "Attention Boundary", "Wake", "Hermes", "MCP")
        )

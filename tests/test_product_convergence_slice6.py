from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


def test_product_decision_requires_explicit_action_and_reconsider(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200

        quiet = client.get(f"/api/worldlines/{worldline_id}/desk")
        assert quiet.status_code == 200
        assert quiet.json()["desk"]["decision_state"] == "QUIET_NO_COURSE"

        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"intent": {"type": "wait"}},
        ).status_code == 422
        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"text": "先守住关口"},
        ).status_code == 422

        opened = client.post(f"/api/worldlines/{worldline_id}/reconsider")
        assert opened.status_code == 200
        assert opened.json()["desk"]["desk"]["decision_state"] == "NEEDS_FIRST_JUDGMENT"
        assert opened.json()["desk"]["desk"]["reconsideration"]["prompt"] == "你准备怎样办？"
        assert opened.json()["desk"]["desk"]["reconsideration"]["voluntary"] is False
        assert "你主动重新考虑了这份判断。" not in str(opened.json()["desk"])

        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "KEEP", "text": ""},
        ).status_code == 409
        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "   "},
        ).status_code == 409


def test_product_desk_four_states_and_explicit_judgment_actions(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200

        opened = client.post(f"/api/worldlines/{worldline_id}/reconsider")
        assert opened.status_code == 200
        waited = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "WAIT", "text": ""},
        )
        assert waited.status_code == 200
        assert waited.json()["desk"]["desk"]["decision_state"] == "QUIET_NO_COURSE"

        continued = client.post(f"/api/worldlines/{worldline_id}/continue")
        assert continued.status_code == 200
        assert continued.json()["pending_moment"]
        changed = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        )
        assert changed.status_code == 200
        assert changed.json()["desk"]["desk"]["decision_state"] == "COURSE_IN_FORCE"

        wakes_before = ChronicleHost(config).db.crisis_wakes(worldline_id)
        implicit = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "不应偷偷重新开一笔判断"},
        )
        assert implicit.status_code == 409
        assert ChronicleHost(config).db.crisis_wakes(worldline_id) == wakes_before

        reconsidered = client.post(f"/api/worldlines/{worldline_id}/reconsider")
        assert reconsidered.status_code == 200
        reconsidered_desk = reconsidered.json()["desk"]["desk"]
        assert reconsidered_desk["decision_state"] == "NEEDS_RECONSIDERATION"
        assert reconsidered_desk["reconsideration"]["voluntary"] is True
        assert reconsidered_desk["reconsideration"]["prompt"] == "你主动重新考虑了这份判断。"
        assert reconsidered_desk["why_now"]["open"] is False

        waiting_with_course = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "WAIT", "text": ""},
        )
        assert waiting_with_course.status_code == 409

        kept = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "KEEP", "text": ""},
        )
        assert kept.status_code == 200
        assert kept.json()["desk"]["desk"]["decision_state"] == "COURSE_IN_FORCE"
        assert kept.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
            "先守住关口"
        )

        repeated = client.post(f"/api/worldlines/{worldline_id}/reconsider")
        assert repeated.status_code == 409

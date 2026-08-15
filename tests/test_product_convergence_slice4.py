from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


@pytest.mark.skip(reason="历史南京/全局 field 投影；当前产品只呈现山海关走廊")
def test_world_projects_durable_reality_and_silences_historical_field(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        created = client.post("/api/worldlines", json={"live": False})
        assert created.status_code == 200
        worldline_id = created.json()["worldline"]["id"]

        host = ChronicleHost(config)
        snapshot = host.db.worldline_snapshot(worldline_id, 0)
        assert snapshot is not None
        projection = copy.deepcopy(snapshot["projection"])
        projection["field_events"][0]["status"] = "APPLIED"
        projection["entities"]["nanjing-political-center"]["state"] = "FU_RECOGNIZED"
        host.db.append_worldline_snapshot(
            worldline_id,
            0,
            int(snapshot["ledger_cursor"]) + 1,
            projection,
        )

        world = client.get(f"/api/worldlines/{worldline_id}/world")

    assert world.status_code == 200
    payload = world.json()
    assert payload["open_questions"]
    assert payload["present_reality"] == [
        {
            "id": "nanjing-political-center",
            "title": "南京政治中心",
            "state": "FU_RECOGNIZED",
            "text": "南京已经形成福王承认的政治中心",
        }
    ]
    assert not any("c002" in str(item) for item in payload["present_reality"])
    assert not {"active_knots", "people", "public_facts"} & set(payload)


def test_world_question_participants_follow_runtime_eligibility(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        first = client.get(f"/api/worldlines/{worldline_id}/world").json()
        wu = next(
            participant
            for question in first["open_questions"]
            for participant in question["participants"]
            if participant["id"] == "wu-sangui"
        )
        assert wu["available"] is True

        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "li-zicheng"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/leave").status_code == 200

        second = client.get(f"/api/worldlines/{worldline_id}/world").json()
        wu_after = next(
            participant
            for question in second["open_questions"]
            for participant in question["participants"]
            if participant["id"] == "wu-sangui"
        )

    assert wu_after["available"] is False
    assert "另一个人的位置" in wu_after["availability_reasons"][0]

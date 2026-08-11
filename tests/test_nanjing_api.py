from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from chronicle.app import create_app


def test_product_api_exposes_and_creates_the_nanjing_political_crisis(app_config, tmp_path):
    config = replace(app_config, database_path=tmp_path / "nanjing-api.db", dev=True)
    client = TestClient(create_app(config))

    crises = client.get("/api/crises")
    detail = client.get("/api/crises/nanjing-succession")
    created = client.post(
        "/api/runs",
        json={
            "crisis_id": "nanjing-succession",
            "mode": "TAKEOVER",
            "human_actor_id": "shi-kefa",
            "live": False,
        },
    )

    assert crises.status_code == 200
    assert [item["id"] for item in crises.json()["crises"]] == [
        "before-shanhaiguan",
        "nanjing-succession",
    ]
    assert detail.status_code == 200
    assert detail.json()["surface"]["kind"] == "POLITICAL"
    assert [item["id"] for item in detail.json()["actors"]] == [
        "shi-kefa",
        "ma-shiying",
        "han-zanzhou",
    ]
    assert all(item["playable"] for item in detail.json()["actors"])
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]
    assert created.json()["run"]["crisis_id"] == "nanjing-succession"
    assert created.json()["run"]["mode"] == "TAKEOVER"
    assert created.json()["run"]["human_actor"] == "shi-kefa"

    perspective = client.get(f"/api/runs/{run_id}/perspective/shi-kefa")
    forbidden = client.get(f"/api/runs/{run_id}/perspective/ma-shiying")

    assert perspective.status_code == 200
    assert perspective.json()["surface"]["kind"] == "POLITICAL"
    assert forbidden.status_code == 403

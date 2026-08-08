from __future__ import annotations

from fastapi.testclient import TestClient

from chronicle.app import create_app


def test_api_exposes_canon_sources_branch_and_masked_setup(app_config):
    client = TestClient(create_app(app_config))

    assert client.get("/health").json()["status"] == "ok"
    scenario = client.get("/api/scenario")
    assert scenario.status_code == 200
    assert scenario.json()["summary"]["event_count"] == 36

    knowledge = client.get("/api/who-knows?tick=44").json()["seats"]
    assert {item["seat"]: item["known_assertions"] for item in knowledge}["A"]
    assert "a019" not in {item["seat"]: item["known_assertions"] for item in knowledge}["B"]

    source = client.get("/api/sources/a019")
    assert source.status_code == 200
    assert source.json()["assertion"]["evidence_status"] == "disputed"

    setup = client.get("/api/config").json()
    assert setup["setup_required"] is True
    assert "CHRONICLE" not in setup.get("api_key", "")
    assert client.post("/api/setup/test", json={"base_url":"https://example.test/v1", "api_key":"", "model":"demo"}).json()["ok"] is False

    early_branch = client.post("/api/branch")
    assert early_branch.status_code == 409
    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 200
    branch = client.post("/api/branch")
    assert branch.status_code == 200
    branch_id = branch.json()["id"]
    step = client.post(f"/api/branch/{branch_id}/step?seat=A", json={"type":"WAIT"})
    assert step.status_code == 200
    assert step.json()["result"]["provenance"] == "branch_derived"


def test_setup_writes_a_server_side_masked_runtime(app_config):
    client = TestClient(create_app(app_config))
    response = client.post(
        "/api/setup/configure",
        json={
            "base_url": "https://provider.example/v1",
            "api_key": "test-secret-not-returned",
            "model": "demo-model",
        },
    )
    assert response.status_code == 200
    assert response.json()["api_key"] == "••••••••••••"
    assert response.json()["runtime_file_mode"] == "0o600"
    config = client.get("/api/config").json()
    assert config["setup_required"] is False
    assert config["api_key"] == "••••••••••••"


def test_live_wake_fails_closed_without_hermes(app_config):
    client = TestClient(create_app(app_config))

    response = client.post("/api/lifetimes/A/wake", json={"tick": 4, "live": True})

    assert response.status_code == 503
    assert "live Hermes" in response.json()["detail"]

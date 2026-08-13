from __future__ import annotations

from fastapi.testclient import TestClient

import chronicle.app as app_module
from chronicle.app import create_app


def test_current_api_exposes_v6_readiness_and_rejects_removed_routes(app_config):
    client = TestClient(create_app(app_config))

    assert client.get("/health").json()["status"] == "ok"
    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["setup_required"] is True
    assert config.json()["runtime_mode"] == "live"
    assert config.json()["hermes_ready"] is False

    assert client.get("/api/volume").status_code == 200
    assert client.get("/api/crises").status_code == 200
    assert client.get("/api/runs").status_code == 404
    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 404
    assert client.get("/v3").status_code == 404
    assert client.get("/legacy").status_code == 404


def test_setup_test_requires_credentials(app_config):
    client = TestClient(create_app(app_config))

    response = client.post(
        "/api/setup/test",
        json={"base_url": "https://example.test/v1", "api_key": "", "model": "demo"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_setup_writes_a_server_side_masked_runtime(app_config, monkeypatch):
    monkeypatch.setattr(
        app_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
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
    assert client.get("/api/config").json()["setup_required"] is False


def test_setup_configures_oauth_without_an_api_key(app_config):
    client = TestClient(create_app(app_config))

    response = client.post(
        "/api/setup/configure",
        json={
            "auth_mode": "oauth",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
        },
    )

    assert response.status_code == 200
    assert response.json()["auth_mode"] == "oauth"
    assert response.json()["provider"] == "openai-codex"
    assert response.json()["api_key"] == ""
    config = client.get("/api/config").json()
    assert config["setup_required"] is False
    assert config["auth_mode"] == "oauth"
    assert config["provider"] == "openai-codex"

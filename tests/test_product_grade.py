from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import chronicle.app as app_module
import chronicle.cli as cli_module
from chronicle.app import create_app
from chronicle.config import write_runtime_env

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_rejects_non_loopback_host_override(app_config, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "load_config", lambda: app_config)

    assert cli_module.main(["serve", "--host", "0.0.0.0"]) == 1
    assert "loopback" in capsys.readouterr().err


def test_cli_start_uses_the_v6_runtime_entry(app_config, monkeypatch):
    created: dict[str, object] = {}
    served: dict[str, object] = {}

    def fake_create(config):
        created["config"] = config
        return "chronicle-app"

    def fake_run(app, **kwargs):
        served.update({"app": app, **kwargs})

    monkeypatch.setattr(cli_module, "load_config", lambda: app_config)
    monkeypatch.setattr(cli_module, "create_app", fake_create)
    monkeypatch.setattr(cli_module.uvicorn, "run", fake_run)

    assert cli_module.main(["start"]) == 0
    assert created == {"config": app_config}
    assert served["app"] == "chronicle-app"
    assert served["reload"] is False


def test_cli_serve_uses_an_import_string_when_development_reload_is_enabled(
    app_config, monkeypatch
):
    served: dict[str, object] = {}

    monkeypatch.setattr(cli_module, "load_config", lambda: replace(app_config, dev=True))
    monkeypatch.setattr(
        cli_module.uvicorn,
        "run",
        lambda app, **kwargs: served.update({"app": app, **kwargs}),
    )

    assert cli_module.main(["serve"]) == 0
    assert served["app"] == "chronicle.app:app"
    assert served["reload"] is True


def test_app_rejects_non_loopback_binding(app_config):
    with pytest.raises(ValueError, match="loopback"):
        create_app(replace(app_config, host="0.0.0.0"))


def test_runtime_env_rejects_newline_injection(app_config):
    with pytest.raises(ValueError, match="newlines"):
        write_runtime_env(app_config, {"CHRONICLE_LLM_MODEL": "safe\nINJECTED=value"})


def test_setup_test_rejects_private_provider_and_unknown_model(app_config, monkeypatch):
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": [{"id": "other-model"}]},
        )

    monkeypatch.setattr(app_module.httpx, "get", fake_get)
    monkeypatch.setattr(
        app_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    client = TestClient(create_app(app_config))

    private = client.post(
        "/api/setup/test",
        json={
            "base_url": "http://169.254.169.254/latest/meta-data",
            "api_key": "secret-probe",
            "model": "requested-model",
        },
    )
    assert private.status_code == 200
    assert private.json()["ok"] is False
    assert calls == []

    unknown = client.post(
        "/api/setup/test",
        json={
            "base_url": "https://provider.example/v1",
            "api_key": "secret-probe",
            "model": "requested-model",
        },
    )
    assert unknown.status_code == 200
    assert unknown.json()["ok"] is False
    assert "requested-model" in unknown.json()["message"]


def test_frontend_exposes_the_v6_product_contract():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "web" / "app.js",
            PROJECT_ROOT / "web" / "api.js",
            PROJECT_ROOT / "web" / "state.js",
            PROJECT_ROOT / "web" / "router.js",
        )
    )
    index = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "此刻哪里值得我去活？" in source
    assert "open_questions" in source
    assert "present_reality" in source
    assert "active_knots" not in source
    assert 'data-action="inhabit"' in source
    assert 'data-action="leave-life"' in source
    assert "AbortController" in source
    assert "aria-live" in source or "aria-live" in index
    assert "/api/worldlines" in source
    assert "Watch" not in source
    assert "Takeover" not in source

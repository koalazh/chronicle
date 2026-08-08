from __future__ import annotations

from dataclasses import replace

import pytest

from chronicle.hermes import (
    PROFILE_NAMES,
    HermesClient,
    HermesRuntimeError,
    enabled_toolset_names,
    probe,
)


def test_enabled_toolset_names_uses_actual_enabled_entries():
    payload = {
        "data": [
            {"name": "bfl", "enabled": True},
            {"name": "memory", "enabled": True},
            {"name": "terminal", "enabled": False},
        ]
    }

    assert enabled_toolset_names(payload) == ("bfl", "memory")


def test_probe_collects_profile_routes_toolsets_and_key_isolation(monkeypatch, app_config):
    keys = {
        PROFILE_NAMES["A"]: "key-a",
        PROFILE_NAMES["B"]: "key-b",
        PROFILE_NAMES["C"]: "key-c",
    }

    def fake_get_json(self, path, *, profile=None, key=""):
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/v1/capabilities":
            return 200, {"features": {"multiplex_profiles": True}}
        if path == "/v1/models" and profile is None:
            return 200, {"data": [{"id": "gateway"}]}
        if path == "/v1/models" and profile:
            expected = keys[profile]
            if key != expected:
                return 401, {"error": "unauthorized"}
            return 200, {"data": [{"id": profile}]}
        if path == "/v1/toolsets" and profile:
            return 200, {"data": [{"name": "memory", "enabled": True}]}
        raise AssertionError((path, profile, key))

    monkeypatch.setattr(HermesClient, "get_json", fake_get_json)
    monkeypatch.setattr("chronicle.hermes.cli_version", lambda _config: "Hermes Agent v0.20.0")
    monkeypatch.setattr("chronicle.hermes.profile_api_key", lambda _config, profile: keys[profile])

    result = probe(app_config, list(PROFILE_NAMES.values()))

    assert result.health is True
    assert result.profile_status == {profile: 200 for profile in PROFILE_NAMES.values()}
    assert result.profile_toolsets == {profile: ("memory",) for profile in PROFILE_NAMES.values()}
    assert result.valid_profile_status == 200
    assert result.cross_profile_status == 401


def test_live_wake_does_not_fallback_to_fixture_on_session_failure(host, app_config, monkeypatch):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    live_host = type(host)(configured, db=host.db, pack=host.pack)
    monkeypatch.setattr("chronicle.host.ChronicleHost._profile_key", lambda _self, _profile: "profile-key")
    monkeypatch.setattr(HermesClient, "create_fresh_session", lambda *_args, **_kwargs: None)

    with pytest.raises(HermesRuntimeError, match="live Hermes"):
        live_host.wake("A", tick=4, live=True)

    assert live_host.db.life_records("A") == []

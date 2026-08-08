from __future__ import annotations

import json
from dataclasses import replace

from chronicle.doctor import doctor
from chronicle.hermes import PROFILE_NAMES, HermesProbeResult


def test_doctor_rejects_actual_extra_profile_toolsets(monkeypatch, app_config):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    for profile in PROFILE_NAMES.values():
        profile_home = configured.hermes_home / "profiles" / profile
        profile_home.mkdir(parents=True)
        (profile_home / "chronicle-genesis.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")

    profiles = list(PROFILE_NAMES.values())
    monkeypatch.setattr("chronicle.doctor.cli_version", lambda _config: "Hermes Agent v0.20.0")
    monkeypatch.setattr(
        "chronicle.doctor.probe",
        lambda _config, _profiles: HermesProbeResult(
            available=True,
            version="Hermes Agent v0.20.0",
            cli_output="Hermes Agent v0.20.0",
            health=True,
            capabilities={"features": {"multiplex_profiles": True}},
            models={"data": [{"id": "gateway"}]},
            profiles=profiles,
            multiplex=True,
            profile_status={profile: 200 for profile in profiles},
            profile_toolsets={profile: ("bfl", "memory") for profile in profiles},
            valid_profile_status=200,
            cross_profile_status=401,
        ),
    )

    result = doctor(configured)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["status"] == "NOT_READY"
    assert checks["toolset_restriction"]["ok"] is False

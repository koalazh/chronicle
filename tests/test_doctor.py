from __future__ import annotations

import json
from dataclasses import replace

import yaml

from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
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


def test_doctor_rejects_root_gateway_probe_errors(monkeypatch, app_config):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    for profile in PROFILE_NAMES.values():
        profile_home = configured.hermes_home / "profiles" / profile
        profile_home.mkdir(parents=True)
        (profile_home / "chronicle-genesis.json").write_text(
            json.dumps({"profile": profile}), encoding="utf-8"
        )

    profiles = list(PROFILE_NAMES.values())
    monkeypatch.setattr("chronicle.doctor.cli_version", lambda _config: "Hermes Agent v0.20.0")
    monkeypatch.setattr(
        "chronicle.doctor.probe",
        lambda _config, _profiles: HermesProbeResult(
            available=True,
            version="Hermes Agent v0.20.0",
            cli_output="Hermes Agent v0.20.0",
            health=True,
            capabilities={},
            models={},
            profiles=profiles,
            multiplex=True,
            profile_status={profile: 200 for profile in profiles},
            profile_toolsets={profile: ("memory",) for profile in profiles},
            valid_profile_status=200,
            cross_profile_status=401,
            errors=("Hermes capabilities unavailable (401)",),
        ),
    )

    result = doctor(configured)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["status"] == "NOT_READY"
    assert checks["gateway_api_probe"]["ok"] is False


def test_doctor_probes_active_v3_profiles_and_identity_specific_world_mcp(
    monkeypatch, app_config
):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )

    def fake_materialize(config, run_id, actors, *, crisis_id, runtime_epoch):
        records = {}
        for actor in actors:
            actor_id = actor["id"]
            profile = actor["profile"]
            server = actor["world_server_name"]
            profile_home = config.hermes_home / "profiles" / profile
            profile_home.mkdir(parents=True)
            (profile_home / "chronicle-genesis.json").write_text(
                json.dumps(
                    {
                        "profile": profile,
                        "actor_id": actor_id,
                        "crisis_id": crisis_id,
                        "run_id": run_id,
                        "worldline_id": run_id,
                        "genesis_hash": actor["genesis_hash"],
                        "initial_memory_snapshot": actor["initial_memory_snapshot"],
                            "runtime_epoch": runtime_epoch,
                            "ownership_marker": actor["ownership_marker"],
                            "toolsets": ["memory", server],
                    }
                ),
                encoding="utf-8",
            )
            (profile_home / "config.yaml").write_text(
                yaml.safe_dump(
                    {
                        "platform_toolsets": {"api_server": ["memory", server]},
                        "mcp_servers": {server: {"command": "python"}},
                    }
                ),
                encoding="utf-8",
            )
            records[actor_id] = {
                "profile": profile,
                "profile_key": f"key-{actor_id}",
                "world_token": f"token-{actor_id}",
                "ownership_marker": actor["ownership_marker"],
                "world_server_name": server,
            }
        return records

    engine = CrisisRunEngine(configured)
    run_id = engine.create(RunMode.WATCH, runtime_mode="live")["run"]["id"]
    run = engine.db.worldline(run_id)
    records = fake_materialize(
        configured,
        run_id,
        engine.live_profile_specs(run_id),
        crisis_id=run["crisis_id"],
        runtime_epoch=run["runtime_epoch"],
    )
    engine.activate_live_runtime(run_id, records)
    profiles = [
        lifetime["profile_name"]
        for lifetime in engine.db.worldline_lifetimes(run_id)
    ]
    monkeypatch.setattr("chronicle.doctor.cli_version", lambda _config: "Hermes Agent v0.20.0")
    monkeypatch.setattr(
        "chronicle.doctor.probe",
        lambda _config, requested: HermesProbeResult(
            available=True,
            version="Hermes Agent v0.20.0",
            cli_output="Hermes Agent v0.20.0",
            health=True,
            capabilities={"features": {"multiplex_profiles": True}},
            models={"data": [{"id": "gateway"}]},
            profiles=requested,
            multiplex=True,
            profile_status={profile: 200 for profile in requested},
            profile_toolsets={profile: ("memory",) for profile in requested},
            valid_profile_status=200,
            cross_profile_status=401,
        ),
    )
    monkeypatch.setattr(
        "chronicle.doctor.probe_mcp_tools",
        lambda _config, _server: (
            "communicate",
            "investigate",
            "manage_offer",
            "operate",
            "schedule_revisit",
            "update_plan",
        ),
    )

    result = doctor(configured)
    checks = {item["name"]: item for item in result["checks"]}

    assert set(profiles) == set(result["config"]["profiles"])
    assert checks["world_mcp_configuration"]["ok"] is True
    assert checks["world_mcp_discovery"]["ok"] is True
    assert checks["schema_version"]["ok"] is True
    assert checks["agent_binding_integrity"]["ok"] is True
    assert checks["profile_identity_integrity"]["ok"] is True
    assert checks["native_memory_integrity"]["ok"] is True
    assert checks["wake_scheduler_integrity"]["ok"] is True
    assert checks["ledger_snapshot_integrity"]["ok"] is True
    assert checks["memory_lineage"]["ok"] is True

    db = engine.db
    binding = db.agent_bindings(run_id)[0]
    with db.transaction() as connection:
        connection.execute(
            "UPDATE worldline_agent_bindings SET token_hash = '' WHERE id = ?",
            (binding["id"],),
        )
    profile = profiles[0]
    memory_path = configured.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("drift", encoding="utf-8")
    marker_path = configured.hermes_home / "profiles" / profile / "chronicle-genesis.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["runtime_epoch"] = "wrong-epoch"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    corrupted = doctor(configured)
    corrupted_checks = {item["name"]: item for item in corrupted["checks"]}

    assert corrupted_checks["agent_binding_integrity"]["ok"] is False
    assert corrupted_checks["profile_identity_integrity"]["ok"] is False
    assert corrupted_checks["native_memory_integrity"]["ok"] is False

    for wake in db.crisis_wakes(run_id, status="QUEUED", tick=0):
        db.update_crisis_wake(
            wake["id"], status="COMPLETED", hermes_session_id=f"session-{wake['id']}"
        )
    execution_checks = {
        item["name"]: item for item in doctor(configured)["checks"]
    }
    assert execution_checks["world_mcp_execution"]["ok"] is False
    assert execution_checks["world_mcp_execution"]["required"] is True


def test_doctor_rejects_scheduler_ledger_and_memory_lineage_corruption(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = engine.db.crisis_wakes(run_id)[0]
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")
    snapshot = engine.db.worldline_snapshot(run_id)
    events = engine.db.worldline_events(run_id)
    engine.db.append_worldline_snapshot(
        run_id,
        snapshot["tick"],
        int(events[-1]["sequence"]) + 10,
        snapshot["projection"],
    )
    engine.db.update_worldline_lifetime(run_id, "li-zicheng", memory_hash="drift")

    result = doctor(app_config)
    checks = {item["name"]: item for item in result["checks"]}

    assert checks["wake_scheduler_integrity"]["ok"] is False
    assert checks["ledger_snapshot_integrity"]["ok"] is False
    assert checks["memory_lineage"]["ok"] is False


def test_doctor_rejects_missing_wake_for_pending_revisit(app_config):
    class RevisitDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "li-zicheng" and wake["wake_type"] == "ORIENT":
                world.schedule_revisit(
                    2,
                    "两日后复查",
                    idempotency_key="li-revisit",
                )
            return ActorTurnResult("完成当前判断。")

    engine = CrisisRunEngine(app_config, actor_driver=RevisitDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    assert engine.advance_one(run_id) is True
    due_wakes = [
        wake
        for wake in engine.db.crisis_wakes(run_id, status="QUEUED")
        if wake["wake_type"] == "REVISIT_DUE"
    ]
    assert len(due_wakes) == 1

    with engine.db.transaction() as connection:
        connection.execute("DELETE FROM crisis_wakes WHERE id = ?", (due_wakes[0]["id"],))

    checks = {item["name"]: item for item in doctor(app_config)["checks"]}

    assert checks["wake_scheduler_integrity"]["ok"] is False
    assert "revisits=1" in checks["wake_scheduler_integrity"]["detail"]
    assert "revisit_wakes=0" in checks["wake_scheduler_integrity"]["detail"]

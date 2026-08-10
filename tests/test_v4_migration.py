from __future__ import annotations

import json
from dataclasses import replace

from chronicle.crisis_runtime import CrisisRunEngine, RunMode
from chronicle.db import ChronicleDB


def test_v9_migration_seals_an_active_v3_crisis_as_legacy_without_rewriting_it(
    app_config, tmp_path
):
    path = tmp_path / "chronicle.db"
    config = replace(app_config, database_path=path)
    engine = CrisisRunEngine(config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]
    legacy_commitments = [
        {
            "id": "legacy-followup",
            "actor_id": "wu-sangui",
            "created_tick": 0,
            "due_tick": 2,
            "reason": "旧版复查",
            "status": "PENDING",
        }
    ]
    engine.db.update_worldline_lifetime(
        run_id,
        "wu-sangui",
        commitments_json=json.dumps(legacy_commitments, ensure_ascii=False),
    )
    with engine.db.transaction() as connection:
        connection.execute("UPDATE app_meta SET value = '8' WHERE key = 'schema_version'")

    migrated = ChronicleDB(path)
    run = migrated.worldline(run_id)

    assert migrated.get_meta("schema_version") == "9"
    assert migrated.migration_backup_path is not None
    assert ".pre-v9." in migrated.migration_backup_path.name
    assert run["status"] == "SEALED"
    assert run["seal_reason"] == "LEGACY_V3"
    assert run["crisis_phase"] == "LEGACY_V3"
    assert json.loads(run["outcome_json"]) == {"kind": "LEGACY_V3"}
    assert run["settlement_reason"] == "LEGACY_V3"
    lifetime = migrated.worldline_lifetime(run_id, "wu-sangui")
    assert lifetime["commitments"] == legacy_commitments
    assert lifetime["revisits"] == []
    assert {binding["status"] for binding in migrated.agent_bindings(run_id)} == {"REVOKED"}
    assert {wake["status"] for wake in migrated.crisis_wakes(run_id)} == {"CANCELLED"}
    seal = next(
        event
        for event in migrated.worldline_events(run_id)
        if event["event_type"] == "LEGACY_V3_SEALED"
    )
    assert seal["payload"] == {
        "reason": "LEGACY_V3",
        "resumable_as_v4": False,
        "replay_mode": "legacy_v3",
    }
    snapshot = migrated.worldline_snapshot(run_id)
    assert snapshot is not None
    assert snapshot["ledger_cursor"] == seal["sequence"]
    assert migrated.active_run() is None


def test_new_crisis_run_pins_v4_content_and_seed(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    run = engine.db.worldline(run_id)

    assert run["volume_id"] == "jiashen"
    assert run["crisis_id"] == "before-shanhaiguan"
    assert run["crisis_version"] == 1
    assert run["crisis_hash"] == engine.pack.content_hash
    assert run["resolution_contract_id"] == "legacy-v3-boundary"
    assert run["resolution_contract_version"] == 1
    assert run["resolution_seed"]
    assert run["crisis_phase"] == "OPEN"
    assert json.loads(run["outcome_json"]) == {}
    assert all(lifetime["revisits"] == [] for lifetime in engine.db.worldline_lifetimes(run_id))


def test_v9_migration_marks_a_live_v3_run_for_safe_cleanup(app_config, tmp_path):
    path = tmp_path / "live-chronicle.db"
    config = replace(app_config, database_path=path)
    engine = CrisisRunEngine(config)
    run_id = engine.create(RunMode.WATCH, runtime_mode="live")["run"]["id"]
    with engine.db.transaction() as connection:
        connection.execute("UPDATE app_meta SET value = '8' WHERE key = 'schema_version'")

    migrated = ChronicleDB(path)
    run = migrated.worldline(run_id)

    assert run["status"] == "SEALED"
    assert run["runtime_phase"] == "CLEANUP_PENDING"
    assert run["runtime_error_code"] == "legacy_v3_migration"

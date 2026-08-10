from __future__ import annotations

import json
import sqlite3

from chronicle.db import SCHEMA, V2_SCHEMA, V3_SCHEMA, ChronicleDB


def test_v8_migration_backs_up_and_seals_active_v2(tmp_path):
    path = tmp_path / "chronicle.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.executescript(V2_SCHEMA)
        connection.executescript(V3_SCHEMA)
        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES ('schema_version', '4')"
        )
        connection.execute(
            "INSERT INTO worldlines(id, scenario_id, kind, status, entry_id, controller_seat, "
            "current_tick, runtime_epoch, runtime_mode, seal_reason, outcome, "
            "pending_confirmation_json, created_at, updated_at) "
            "VALUES ('legacy-active', 'jiashen', 'BRANCH', 'ACTIVE', 'entry', 'A', 44, "
            "'epoch', 'live', '', '', '', '2026-01-01', '2026-01-01')"
        )
        connection.execute(
            "INSERT INTO worldline_lifetimes(id, worldline_id, seat, controller, status, "
            "parent_canon_lifetime, profile_name, profile_metadata_json, genesis_hash, "
            "memory_text, memory_hash, knowledge_json, belief_json, authority_json, "
            "created_at, updated_at) VALUES ('life-a', 'legacy-active', 'A', 'HUMAN', "
            "'ACTIVE', '', '', '{}', '', '', '', '[]', '{}', '[]', '2026-01-01', '2026-01-01')"
        )

    db = ChronicleDB(path)

    assert db.get_meta("schema_version") == "8"
    assert db.migration_backup_path is not None
    assert ".pre-v7." in db.migration_backup_path.name
    assert db.worldline("legacy-active")["status"] == "SEALED"
    assert db.worldline("legacy-active")["seal_reason"] == "legacy_v3_migration"
    assert db.worldline_lifetime("legacy-active", "A")["status"] == "SEALED"
    seal = next(
        event
        for event in db.worldline_events("legacy-active")
        if event["event_type"] == "LEGACY_V2_SEALED"
    )
    assert seal["payload"] == {
        "reason": "legacy_v3_migration",
        "resumable_as_v3": False,
    }


def test_v8_schema_preserves_preexisting_v6_tables(tmp_path):
    path = tmp_path / "chronicle.db"
    db = ChronicleDB(path)
    with db.transaction() as connection:
        connection.execute(
            "CREATE TABLE preserved_v6_state(id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO preserved_v6_state VALUES ('keep-me', ?)",
            (json.dumps({"preserved": True}),),
        )
        connection.execute("UPDATE app_meta SET value = '6' WHERE key = 'schema_version'")

    migrated = ChronicleDB(path)

    assert migrated.get_meta("schema_version") == "8"
    with migrated.transaction() as connection:
        row = connection.execute(
            "SELECT payload_json FROM preserved_v6_state WHERE id = 'keep-me'"
        ).fetchone()
        lifetime_columns = {
            item["name"] for item in connection.execute("PRAGMA table_info(worldline_lifetimes)")
        }
        worldline_columns = {
            item["name"] for item in connection.execute("PRAGMA table_info(worldlines)")
        }
    assert json.loads(row["payload_json"]) == {"preserved": True}
    assert {"role_charter_json", "plan_json", "commitments_json", "resources_json"}.issubset(
        lifetime_columns
    )
    assert {"crisis_id", "controller_map_json", "simulation_boundary_json", "runtime_phase", "runtime_error_code"}.issubset(
        worldline_columns
    )

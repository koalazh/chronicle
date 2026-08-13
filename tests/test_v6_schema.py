from __future__ import annotations

import sqlite3

from chronicle.db import ChronicleDB


def test_v6_schema_contains_only_current_volume_tables(tmp_path):
    db = ChronicleDB(tmp_path / "chronicle.db")

    with sqlite3.connect(db.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        worldline_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(worldlines)")
        }

    assert db.get_meta("schema_version") == "10"
    assert {
        "app_meta",
        "worldlines",
        "worldline_events",
        "worldline_snapshot_history",
        "worldline_lifetimes",
        "worldline_agent_bindings",
        "crisis_wakes",
        "crisis_wake_operations",
        "worldline_crisis_instances",
        "protocol_violations",
    } <= tables
    assert not {
        "branches",
        "branch_records",
        "memory_versions",
        "life_records",
        "wake_sessions",
        "worldline_snapshots",
        "runtime_epochs",
    } & tables
    assert {
        "volume_id",
        "volume_content_version",
        "volume_content_hash",
        "runtime_phase",
        "human_lifetime_id",
    } <= worldline_columns


def test_v6_database_rejects_an_older_schema(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES ('schema_version', '5')"
        )
        connection.commit()

    try:
        ChronicleDB(path)
    except RuntimeError as exc:
        assert "recreate the database for V6" in str(exc)
    else:
        raise AssertionError("an older database schema must not be opened")

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"app_meta"}


def test_v6_database_rejects_an_unmarked_database_without_mutating_it(tmp_path):
    path = tmp_path / "unmarked.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.commit()

    try:
        ChronicleDB(path)
    except RuntimeError as exc:
        assert "without a V6 schema marker" in str(exc)
    else:
        raise AssertionError("an unmarked database must not be opened")

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"sentinel"}


def test_v6_schema_repairs_the_current_lifetime_column_shape(tmp_path):
    path = tmp_path / "current-v6.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE worldline_lifetimes ("
            "id TEXT PRIMARY KEY, parent_canon_lifetime TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES ('schema_version', '10')"
        )
        connection.execute(
            "INSERT INTO worldline_lifetimes(id, parent_canon_lifetime) VALUES (?, ?)",
            ("life-1", "jiashen:wu-sangui"),
        )
        connection.commit()

    ChronicleDB(path)

    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(worldline_lifetimes)")
        }
        value = connection.execute(
            "SELECT genesis_parent_id FROM worldline_lifetimes WHERE id = ?",
            ("life-1",),
        ).fetchone()[0]
    assert "genesis_parent_id" in columns
    assert value == "jiashen:wu-sangui"

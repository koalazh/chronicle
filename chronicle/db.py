from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_epochs (
    id TEXT PRIMARY KEY,
    hermes_version TEXT NOT NULL,
    provider_base_url_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    soul_hash TEXT NOT NULL,
    skill_hash TEXT NOT NULL,
    toolset_hash TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS life_records (
    id TEXT PRIMARY KEY,
    seat TEXT NOT NULL,
    tick INTEGER NOT NULL,
    wake_type TEXT NOT NULL,
    observation_ids TEXT NOT NULL,
    belief_before TEXT NOT NULL,
    belief_after TEXT NOT NULL,
    intentions TEXT NOT NULL,
    memory_hash_before TEXT NOT NULL,
    memory_hash_after TEXT NOT NULL,
    runtime_epoch TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS life_records_append_only_update
BEFORE UPDATE ON life_records
BEGIN
    SELECT RAISE(ABORT, 'life_records are append-only');
END;

CREATE TRIGGER IF NOT EXISTS life_records_append_only_delete
BEFORE DELETE ON life_records
BEGIN
    SELECT RAISE(ABORT, 'life_records are append-only');
END;

CREATE TABLE IF NOT EXISTS beliefs (
    seat TEXT NOT NULL,
    belief_key TEXT NOT NULL,
    confidence REAL NOT NULL,
    direction TEXT NOT NULL,
    statement TEXT NOT NULL,
    updated_tick INTEGER NOT NULL,
    PRIMARY KEY (seat, belief_key)
);

CREATE TABLE IF NOT EXISTS memory_versions (
    id TEXT PRIMARY KEY,
    seat TEXT NOT NULL,
    memory_text TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    memory_hash TEXT NOT NULL,
    mutation_kind TEXT NOT NULL,
    source_record_ids TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS memory_versions_append_only_update
BEFORE UPDATE ON memory_versions
BEGIN
    SELECT RAISE(ABORT, 'memory_versions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS memory_versions_append_only_delete
BEFORE DELETE ON memory_versions
BEGIN
    SELECT RAISE(ABORT, 'memory_versions are append-only');
END;

CREATE TABLE IF NOT EXISTS wake_sessions (
    id TEXT PRIMARY KEY,
    seat TEXT NOT NULL,
    wake_type TEXT NOT NULL,
    hermes_session_id TEXT,
    source TEXT NOT NULL,
    runtime_epoch TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS protocol_violations (
    id TEXT PRIMARY KEY,
    seat TEXT NOT NULL,
    tick INTEGER NOT NULL,
    wake_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    memory_hash_before TEXT NOT NULL,
    memory_hash_after TEXT NOT NULL,
    memory_diff TEXT NOT NULL,
    action TEXT NOT NULL,
    runtime_epoch TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS protocol_violations_append_only_update
BEFORE UPDATE ON protocol_violations
BEGIN
    SELECT RAISE(ABORT, 'protocol_violations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS protocol_violations_append_only_delete
BEFORE DELETE ON protocol_violations
BEGIN
    SELECT RAISE(ABORT, 'protocol_violations are append-only');
END;

CREATE TABLE IF NOT EXISTS branches (
    id TEXT PRIMARY KEY,
    fork_id TEXT NOT NULL,
    status TEXT NOT NULL,
    tick INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    boundary_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branch_records (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL REFERENCES branches(id),
    tick INTEGER NOT NULL,
    actor_seat TEXT NOT NULL,
    action_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS worldlines (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    entry_id TEXT NOT NULL DEFAULT '',
    controller_seat TEXT NOT NULL DEFAULT '',
    current_tick INTEGER NOT NULL,
    runtime_epoch TEXT NOT NULL DEFAULT '',
    runtime_mode TEXT NOT NULL DEFAULT 'fixture',
    seal_reason TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    pending_confirmation_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS worldlines_status_idx ON worldlines(status, kind, updated_at);

CREATE UNIQUE INDEX IF NOT EXISTS active_human_worldline_idx
ON worldlines(controller_seat)
WHERE kind = 'BRANCH' AND status = 'ACTIVE' AND controller_seat <> '';

CREATE UNIQUE INDEX IF NOT EXISTS active_human_worldline_singleton_idx
ON worldlines((1))
WHERE kind = 'BRANCH' AND status = 'ACTIVE' AND controller_seat <> '';

CREATE TABLE IF NOT EXISTS worldline_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    tick INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    seat_id TEXT,
    payload_json TEXT NOT NULL,
    provenance TEXT NOT NULL,
    causal_parent_ids TEXT NOT NULL,
    runtime_epoch TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS worldline_events_lookup_idx
ON worldline_events(worldline_id, tick, sequence);

CREATE TRIGGER IF NOT EXISTS worldline_events_append_only_update
BEFORE UPDATE ON worldline_events
BEGIN
    SELECT RAISE(ABORT, 'worldline_events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS worldline_events_append_only_delete
BEFORE DELETE ON worldline_events
BEGIN
    SELECT RAISE(ABORT, 'worldline_events are append-only');
END;

CREATE TABLE IF NOT EXISTS worldline_snapshots (
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    tick INTEGER NOT NULL,
    ledger_cursor INTEGER NOT NULL,
    projection_json TEXT NOT NULL,
    projection_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (worldline_id, tick)
);

CREATE TRIGGER IF NOT EXISTS worldline_snapshots_append_only_update
BEFORE UPDATE ON worldline_snapshots
BEGIN
    SELECT RAISE(ABORT, 'worldline_snapshots are append-only');
END;

CREATE TRIGGER IF NOT EXISTS worldline_snapshots_append_only_delete
BEFORE DELETE ON worldline_snapshots
BEGIN
    SELECT RAISE(ABORT, 'worldline_snapshots are append-only');
END;

CREATE TABLE IF NOT EXISTS worldline_lifetimes (
    id TEXT PRIMARY KEY,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    seat TEXT NOT NULL,
    controller TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_canon_lifetime TEXT NOT NULL DEFAULT '',
    profile_name TEXT NOT NULL DEFAULT '',
    profile_metadata_json TEXT NOT NULL DEFAULT '{}',
    genesis_hash TEXT NOT NULL DEFAULT '',
    memory_text TEXT NOT NULL DEFAULT '',
    memory_hash TEXT NOT NULL DEFAULT '',
    knowledge_json TEXT NOT NULL DEFAULT '[]',
    belief_json TEXT NOT NULL DEFAULT '{}',
    authority_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, seat)
);
"""


V3_SCHEMA = """
CREATE TABLE IF NOT EXISTS worldline_snapshot_history (
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    tick INTEGER NOT NULL,
    ledger_cursor INTEGER NOT NULL,
    projection_json TEXT NOT NULL,
    projection_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (worldline_id, tick, ledger_cursor)
);

CREATE INDEX IF NOT EXISTS worldline_snapshot_history_tick_idx
ON worldline_snapshot_history(worldline_id, tick, ledger_cursor);

CREATE TRIGGER IF NOT EXISTS worldline_snapshot_history_append_only_update
BEFORE UPDATE ON worldline_snapshot_history
BEGIN
    SELECT RAISE(ABORT, 'worldline_snapshot_history is append-only');
END;

CREATE TRIGGER IF NOT EXISTS worldline_snapshot_history_append_only_delete
BEFORE DELETE ON worldline_snapshot_history
BEGIN
    SELECT RAISE(ABORT, 'worldline_snapshot_history is append-only');
END;
"""


V7_SCHEMA = """
CREATE TABLE IF NOT EXISTS worldline_agent_bindings (
    id TEXT PRIMARY KEY,
    worldline_id TEXT,
    role TEXT NOT NULL,
    profile_identity TEXT NOT NULL,
    distribution_version TEXT NOT NULL,
    ownership_marker TEXT NOT NULL,
    status TEXT NOT NULL,
    token_hash TEXT NOT NULL DEFAULT '',
    revoked_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, role)
);

CREATE UNIQUE INDEX IF NOT EXISTS worldline_agent_bindings_token_idx
ON worldline_agent_bindings(token_hash)
WHERE token_hash <> '';

CREATE TABLE IF NOT EXISTS crisis_wakes (
    id TEXT PRIMARY KEY,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    actor_id TEXT NOT NULL,
    wake_type TEXT NOT NULL,
    tick INTEGER NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    trigger_event_id TEXT NOT NULL DEFAULT '',
    hermes_session_id TEXT NOT NULL DEFAULT '',
    frozen_perspective_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, actor_id, wake_type, tick, trigger_event_id)
);

CREATE INDEX IF NOT EXISTS crisis_wakes_due_idx
ON crisis_wakes(worldline_id, status, tick, actor_id);

CREATE TABLE IF NOT EXISTS crisis_wake_operations (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    wake_id TEXT NOT NULL REFERENCES crisis_wakes(id),
    tool_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(wake_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS crisis_wake_operations_lookup_idx
ON crisis_wake_operations(wake_id, sequence);

CREATE UNIQUE INDEX IF NOT EXISTS active_playable_run_singleton_idx
ON worldlines((1))
WHERE kind IN ('BRANCH', 'CRISIS') AND status = 'ACTIVE';
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ChronicleDB:
    def __init__(self, path: Path):
        self.path = path
        self.migration_backup_path: Path | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        existing_before = self.path.exists() and self.path.stat().st_size > 0
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
            version = int(row["value"]) if row and str(row["value"]).isdigit() else 1
        if version < 2:
            if existing_before:
                self.migration_backup_path = self._backup_before_v2()
            with self.transaction() as connection:
                connection.executescript(V2_SCHEMA)
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '2') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )
            self._import_legacy_branches()
            version = 2
        if version < 3:
            if existing_before and self.migration_backup_path is None:
                self.migration_backup_path = self._backup_before_v3()
            with self.transaction() as connection:
                connection.executescript(V3_SCHEMA)
                connection.execute(
                    "INSERT OR IGNORE INTO worldline_snapshot_history "
                    "(worldline_id, tick, ledger_cursor, projection_json, projection_hash, created_at) "
                    "SELECT worldline_id, tick, ledger_cursor, projection_json, projection_hash, created_at "
                    "FROM worldline_snapshots"
                )
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '3') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )
            version = 3
        if version < 4:
            if existing_before and self.migration_backup_path is None:
                self.migration_backup_path = self._backup_before_v4()
            with self.transaction() as connection:
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(worldlines)")}
                if "runtime_mode" not in columns:
                    connection.execute(
                        "ALTER TABLE worldlines ADD COLUMN runtime_mode TEXT NOT NULL DEFAULT 'fixture'"
                    )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS active_human_worldline_singleton_idx "
                    "ON worldlines((1)) "
                    "WHERE kind = 'BRANCH' AND status = 'ACTIVE' AND controller_seat <> ''"
                )
                rows = connection.execute(
                    "SELECT id FROM worldlines WHERE kind = 'BRANCH'"
                ).fetchall()
                for row in rows:
                    event = connection.execute(
                        "SELECT payload_json FROM worldline_events "
                        "WHERE worldline_id = ? AND event_type = 'WORLDLINE_CREATED' "
                        "ORDER BY sequence LIMIT 1",
                        (row["id"],),
                    ).fetchone()
                    if not event:
                        continue
                    payload = json.loads(event["payload_json"])
                    mode = payload.get("runtime_mode")
                    if mode in {"fixture", "live"}:
                        connection.execute(
                            "UPDATE worldlines SET runtime_mode = ? WHERE id = ?",
                            (mode, row["id"]),
                        )
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '4') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )
            version = 4
        if version < 7:
            if existing_before and self.migration_backup_path is None:
                self.migration_backup_path = self._backup_before_v7()
            with self.transaction() as connection:
                self._seal_active_v2_for_v3(connection)
                self._add_column(
                    connection,
                    "worldlines",
                    "crisis_id",
                    "TEXT NOT NULL DEFAULT ''",
                )
                self._add_column(
                    connection,
                    "worldlines",
                    "controller_map_json",
                    "TEXT NOT NULL DEFAULT '{}'",
                )
                self._add_column(
                    connection,
                    "worldlines",
                    "simulation_boundary_json",
                    "TEXT NOT NULL DEFAULT '{}'",
                )
                for name, declaration in (
                    ("role_charter_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("plan_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("commitments_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("resources_json", "TEXT NOT NULL DEFAULT '{}'") ,
                    ("last_perspective_json", "TEXT NOT NULL DEFAULT '{}'") ,
                    ("wake_count", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    self._add_column(connection, "worldline_lifetimes", name, declaration)
                connection.executescript(V7_SCHEMA)
                self._add_column(
                    connection,
                    "worldline_agent_bindings",
                    "token_hash",
                    "TEXT NOT NULL DEFAULT ''",
                )
                self._add_column(
                    connection,
                    "worldline_agent_bindings",
                    "revoked_at",
                    "TEXT NOT NULL DEFAULT ''",
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS worldline_agent_bindings_token_idx "
                    "ON worldline_agent_bindings(token_hash) WHERE token_hash <> ''"
                )
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '7') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )
            version = 7
        if version < 8:
            if existing_before and self.migration_backup_path is None:
                self.migration_backup_path = self._backup_before_v8()
            with self.transaction() as connection:
                self._add_column(
                    connection,
                    "worldlines",
                    "runtime_phase",
                    "TEXT NOT NULL DEFAULT 'READY'",
                )
                self._add_column(
                    connection,
                    "worldlines",
                    "runtime_error_code",
                    "TEXT NOT NULL DEFAULT ''",
                )
                connection.execute(
                    "UPDATE worldlines SET runtime_phase = 'RECONCILING' "
                    "WHERE kind = 'CRISIS' AND status = 'ACTIVE' AND runtime_mode = 'live'"
                )
                connection.execute(
                    "UPDATE worldlines SET runtime_phase = 'CLEANUP_PENDING', "
                    "runtime_error_code = 'runtime_cleanup_pending' "
                    "WHERE kind = 'CRISIS' AND status = 'SEALED' AND runtime_mode = 'live'"
                )
                changed_at = now_iso()
                connection.execute(
                    "UPDATE worldline_agent_bindings SET status = 'REVOKED', revoked_at = ?, "
                    "updated_at = ? WHERE worldline_id IN "
                    "(SELECT id FROM worldlines WHERE kind = 'CRISIS' AND status = 'SEALED') "
                    "AND status = 'ACTIVE'",
                    (changed_at, changed_at),
                )
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '8') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )
            version = 8
        if version < 9:
            if existing_before and self.migration_backup_path is None:
                self.migration_backup_path = self._backup_before_v9()
            with self.transaction() as connection:
                for name, declaration in (
                    ("volume_id", "TEXT NOT NULL DEFAULT ''"),
                    ("crisis_version", "INTEGER NOT NULL DEFAULT 0"),
                    ("crisis_hash", "TEXT NOT NULL DEFAULT ''"),
                    ("resolution_contract_id", "TEXT NOT NULL DEFAULT ''"),
                    ("resolution_contract_version", "INTEGER NOT NULL DEFAULT 0"),
                    ("resolution_seed", "TEXT NOT NULL DEFAULT ''"),
                    ("crisis_phase", "TEXT NOT NULL DEFAULT ''"),
                    ("outcome_json", "TEXT NOT NULL DEFAULT '{}'"),
                    ("settlement_reason", "TEXT NOT NULL DEFAULT ''"),
                ):
                    self._add_column(connection, "worldlines", name, declaration)
                self._add_column(
                    connection,
                    "worldline_lifetimes",
                    "revisits_json",
                    "TEXT NOT NULL DEFAULT '[]'",
                )
                self._seal_active_v3_for_v4(connection)
                connection.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('schema_version', '9') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                )

    @staticmethod
    def _add_column(
        connection: sqlite3.Connection,
        table: str,
        name: str,
        declaration: str,
    ) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    @staticmethod
    def _seal_active_v2_for_v3(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, current_tick, runtime_epoch FROM worldlines "
            "WHERE kind = 'BRANCH' AND status = 'ACTIVE'"
        ).fetchall()
        changed_at = now_iso()
        for row in rows:
            event_id = f"v3-legacy-seal-{row['id']}"
            connection.execute(
                "INSERT OR IGNORE INTO worldline_events(id, worldline_id, tick, event_type, seat_id, "
                "payload_json, provenance, causal_parent_ids, runtime_epoch, created_at) "
                "VALUES (?, ?, ?, 'LEGACY_V2_SEALED', NULL, ?, 'branch_derived', '[]', ?, ?)",
                (
                    event_id,
                    row["id"],
                    int(row["current_tick"]),
                    json.dumps(
                        {
                            "reason": "legacy_v3_migration",
                            "resumable_as_v3": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    row["runtime_epoch"],
                    changed_at,
                ),
            )
            connection.execute(
                "UPDATE worldlines SET status = 'SEALED', seal_reason = 'legacy_v3_migration', "
                "updated_at = ? WHERE id = ? AND status = 'ACTIVE'",
                (changed_at, row["id"]),
            )
            connection.execute(
                "UPDATE worldline_lifetimes SET status = 'SEALED', updated_at = ? "
                "WHERE worldline_id = ?",
                (changed_at, row["id"]),
            )

    @staticmethod
    def _seal_active_v3_for_v4(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, current_tick, runtime_epoch, runtime_mode FROM worldlines "
            "WHERE kind = 'CRISIS' AND status = 'ACTIVE'"
        ).fetchall()
        changed_at = now_iso()
        for row in rows:
            event_id = f"v4-legacy-seal-{row['id']}"
            connection.execute(
                "INSERT OR IGNORE INTO worldline_events(id, worldline_id, tick, event_type, seat_id, "
                "payload_json, provenance, causal_parent_ids, runtime_epoch, created_at) "
                "VALUES (?, ?, ?, 'LEGACY_V3_SEALED', NULL, ?, 'branch_derived', '[]', ?, ?)",
                (
                    event_id,
                    row["id"],
                    int(row["current_tick"]),
                    json.dumps(
                        {
                            "reason": "LEGACY_V3",
                            "resumable_as_v4": False,
                            "replay_mode": "legacy_v3",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    row["runtime_epoch"],
                    changed_at,
                ),
            )
            snapshot = connection.execute(
                "SELECT projection_json, projection_hash FROM worldline_snapshot_history "
                "WHERE worldline_id = ? ORDER BY tick DESC, ledger_cursor DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            if snapshot is not None:
                ledger_cursor = connection.execute(
                    "SELECT MAX(sequence) FROM worldline_events WHERE worldline_id = ?",
                    (row["id"],),
                ).fetchone()[0]
                connection.execute(
                    "INSERT OR IGNORE INTO worldline_snapshot_history("
                    "worldline_id, tick, ledger_cursor, projection_json, projection_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        row["id"],
                        int(row["current_tick"]),
                        int(ledger_cursor),
                        snapshot["projection_json"],
                        snapshot["projection_hash"],
                        changed_at,
                    ),
                )
            runtime_phase = (
                "CLEANUP_PENDING" if row["runtime_mode"] == "live" else "READY"
            )
            runtime_error_code = "legacy_v3_migration" if row["runtime_mode"] == "live" else ""
            connection.execute(
                "UPDATE worldlines SET status = 'SEALED', seal_reason = 'LEGACY_V3', "
                "runtime_phase = ?, runtime_error_code = ?, crisis_phase = 'LEGACY_V3', "
                "outcome_json = ?, settlement_reason = 'LEGACY_V3', updated_at = ? "
                "WHERE id = ? AND status = 'ACTIVE'",
                (
                    runtime_phase,
                    runtime_error_code,
                    json.dumps({"kind": "LEGACY_V3"}, ensure_ascii=False, sort_keys=True),
                    changed_at,
                    row["id"],
                ),
            )
            connection.execute(
                "UPDATE worldline_lifetimes SET status = 'SEALED', updated_at = ? "
                "WHERE worldline_id = ?",
                (changed_at, row["id"]),
            )
            connection.execute(
                "UPDATE worldline_agent_bindings SET status = 'REVOKED', revoked_at = ?, "
                "updated_at = ? WHERE worldline_id = ? AND status = 'ACTIVE'",
                (changed_at, changed_at, row["id"]),
            )
            connection.execute(
                "UPDATE crisis_wakes SET status = 'CANCELLED', updated_at = ? "
                "WHERE worldline_id = ? AND status = 'QUEUED'",
                (changed_at, row["id"]),
            )

    def _backup_before_v2(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v2.{stamp}{self.path.suffix}")
        source = self._connect()
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        return backup

    def _backup_before_v3(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v3.{stamp}{self.path.suffix}")
        source = self._connect()
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        return backup

    def _backup_before_v9(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v9.{stamp}{self.path.suffix}")
        source = self._connect()
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        return backup

    def _backup_before_v4(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v4.{stamp}{self.path.suffix}")
        source = self._connect()
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        return backup

    def _backup_before_v7(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v7.{stamp}{self.path.suffix}")
        source = self._connect()
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        return backup

    def _backup_before_v8(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup = self.path.with_name(f"{self.path.stem}.pre-v8.{stamp}{self.path.suffix}")
        with self._connect() as source, sqlite3.connect(backup) as target:
            source.backup(target)
        return backup

    def _import_legacy_branches(self) -> None:
        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM branches ORDER BY created_at").fetchall()
            for row in rows:
                worldline_id = f"legacy-{row['id']}"
                exists = connection.execute(
                    "SELECT 1 FROM worldlines WHERE id = ?", (worldline_id,)
                ).fetchone()
                if exists:
                    continue
                created_at = str(row["created_at"])
                connection.execute(
                    "INSERT INTO worldlines(id, scenario_id, kind, status, entry_id, controller_seat, current_tick, "
                    "runtime_epoch, seal_reason, outcome, pending_confirmation_json, created_at, updated_at) "
                    "VALUES (?, ?, 'BRANCH', 'SEALED', ?, '', ?, '', 'legacy_import', '', '', ?, ?)",
                    (
                        worldline_id,
                        "jiashen",
                        str(row["fork_id"]),
                        int(row["tick"]),
                        created_at,
                        str(row["updated_at"]),
                    ),
                )
                records = connection.execute(
                    "SELECT id, tick, actor_seat, action_json, result_json FROM branch_records "
                    "WHERE branch_id = ? ORDER BY tick, created_at",
                    (row["id"],),
                ).fetchall()
                payload = {
                    "legacy_branch_id": row["id"],
                    "fork_id": row["fork_id"],
                    "state_json": json.loads(row["state_json"]),
                    "records": [
                        {
                            "id": record["id"],
                            "tick": record["tick"],
                            "actor_seat": record["actor_seat"],
                            "action_json": json.loads(record["action_json"]),
                            "result_json": json.loads(record["result_json"]),
                        }
                        for record in records
                    ],
                }
                connection.execute(
                    "INSERT INTO worldline_events(id, worldline_id, tick, event_type, seat_id, payload_json, "
                    "provenance, causal_parent_ids, runtime_epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"legacy-import-{row['id']}",
                        worldline_id,
                        int(row["tick"]),
                        "LEGACY_IMPORT",
                        None,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        "branch_derived",
                        "[]",
                        None,
                        created_at,
                    ),
                )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO app_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def worldline(self, worldline_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
        return dict(row) if row else None

    def worldlines(self, *, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM worldlines"
        args: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            args = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, args).fetchall()]

    def active_human_worldline(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldlines WHERE kind = 'BRANCH' AND status = 'ACTIVE' "
                "AND controller_seat != '' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def active_run(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldlines WHERE kind = 'CRISIS' AND status = 'ACTIVE' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._decode_worldline(row) if row else None

    @staticmethod
    def _decode_worldline(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for key in ("controller_map_json", "simulation_boundary_json"):
            if key in item:
                item[key.removesuffix("_json")] = json.loads(item.pop(key))
        if "outcome_json" in item:
            item["outcome_data"] = json.loads(item["outcome_json"])
        return item

    def create_worldline(self, values: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldlines(id, scenario_id, kind, status, entry_id, controller_seat, current_tick, "
                "runtime_epoch, runtime_mode, seal_reason, outcome, pending_confirmation_json, created_at, updated_at) "
                "VALUES (:id, :scenario_id, :kind, :status, :entry_id, :controller_seat, :current_tick, "
                ":runtime_epoch, :runtime_mode, :seal_reason, :outcome, :pending_confirmation_json, :created_at, :updated_at)",
                {
                    "id": values["id"],
                    "scenario_id": values.get("scenario_id", "jiashen"),
                    "kind": values.get("kind", "BRANCH"),
                    "status": values.get("status", "ACTIVE"),
                    "entry_id": values.get("entry_id", ""),
                    "controller_seat": values.get("controller_seat", ""),
                    "current_tick": values["current_tick"],
                    "runtime_epoch": values.get("runtime_epoch", ""),
                    "runtime_mode": values.get("runtime_mode", "fixture"),
                    "seal_reason": values.get("seal_reason", ""),
                    "outcome": values.get("outcome", ""),
                    "pending_confirmation_json": values.get("pending_confirmation_json", ""),
                    "created_at": values.get("created_at", now_iso()),
                    "updated_at": values.get("updated_at", now_iso()),
                },
            )
        return self.worldline(str(values["id"])) or {}

    def create_worldline_bundle(
        self,
        values: dict[str, Any],
        events: list[dict[str, Any]],
        lifetimes: list[dict[str, Any]],
        projection: dict[str, Any],
    ) -> dict[str, Any]:
        """Create the initial Worldline, lifetimes, ledger, and snapshot atomically."""

        worldline = {
            "id": values["id"],
            "scenario_id": values.get("scenario_id", "jiashen"),
            "kind": values.get("kind", "BRANCH"),
            "status": values.get("status", "ACTIVE"),
            "entry_id": values.get("entry_id", ""),
            "controller_seat": values.get("controller_seat", ""),
            "current_tick": values["current_tick"],
            "runtime_epoch": values.get("runtime_epoch", ""),
            "runtime_mode": values.get("runtime_mode", "fixture"),
            "seal_reason": values.get("seal_reason", ""),
            "outcome": values.get("outcome", ""),
            "pending_confirmation_json": values.get("pending_confirmation_json", ""),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldlines(id, scenario_id, kind, status, entry_id, controller_seat, current_tick, "
                "runtime_epoch, runtime_mode, seal_reason, outcome, pending_confirmation_json, created_at, updated_at) "
                "VALUES (:id, :scenario_id, :kind, :status, :entry_id, :controller_seat, :current_tick, "
                ":runtime_epoch, :runtime_mode, :seal_reason, :outcome, :pending_confirmation_json, :created_at, :updated_at)",
                worldline,
            )
            last_sequence = 0
            for event in events:
                record = {
                    "id": event["id"],
                    "worldline_id": values["id"],
                    "tick": int(event["tick"]),
                    "event_type": event["event_type"],
                    "seat_id": event.get("seat_id"),
                    "payload_json": json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=True),
                    "provenance": event.get("provenance", "branch_derived"),
                    "causal_parent_ids": json.dumps(event.get("causal_parent_ids", []), ensure_ascii=False),
                    "runtime_epoch": event.get("runtime_epoch"),
                    "created_at": event.get("created_at", now_iso()),
                }
                cursor = connection.execute(
                    "INSERT INTO worldline_events(id, worldline_id, tick, event_type, seat_id, payload_json, "
                    "provenance, causal_parent_ids, runtime_epoch, created_at) "
                    "VALUES (:id, :worldline_id, :tick, :event_type, :seat_id, :payload_json, :provenance, "
                    ":causal_parent_ids, :runtime_epoch, :created_at)",
                    record,
                )
                last_sequence = int(cursor.lastrowid or 0)
            for values_for_lifetime in lifetimes:
                connection.execute(
                    "INSERT INTO worldline_lifetimes(id, worldline_id, seat, controller, status, "
                    "parent_canon_lifetime, profile_name, profile_metadata_json, genesis_hash, memory_text, memory_hash, "
                    "knowledge_json, belief_json, authority_json, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :seat, :controller, :status, :parent_canon_lifetime, :profile_name, "
                    ":profile_metadata_json, :genesis_hash, :memory_text, :memory_hash, :knowledge_json, :belief_json, "
                    ":authority_json, :created_at, :updated_at)",
                    {
                        "id": values_for_lifetime["id"],
                        "worldline_id": values["id"],
                        "seat": values_for_lifetime["seat"],
                        "controller": values_for_lifetime["controller"],
                        "status": values_for_lifetime.get("status", "ACTIVE"),
                        "parent_canon_lifetime": values_for_lifetime.get("parent_canon_lifetime", ""),
                        "profile_name": values_for_lifetime.get("profile_name", ""),
                        "profile_metadata_json": json.dumps(
                            values_for_lifetime.get("profile_metadata", {}), ensure_ascii=False
                        ),
                        "genesis_hash": values_for_lifetime.get("genesis_hash", ""),
                        "memory_text": values_for_lifetime.get("memory_text", ""),
                        "memory_hash": values_for_lifetime.get("memory_hash", ""),
                        "knowledge_json": json.dumps(
                            values_for_lifetime.get("knowledge", []), ensure_ascii=False, sort_keys=True
                        ),
                        "belief_json": json.dumps(
                            values_for_lifetime.get("beliefs", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "authority_json": json.dumps(
                            values_for_lifetime.get("authority", []), ensure_ascii=False, sort_keys=True
                        ),
                        "created_at": values_for_lifetime.get("created_at", now_iso()),
                        "updated_at": values_for_lifetime.get("updated_at", now_iso()),
                    },
                )
            connection.execute(
                "INSERT INTO worldline_snapshot_history(worldline_id, tick, ledger_cursor, projection_json, "
                "projection_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    values["id"],
                    int(values["current_tick"]),
                    last_sequence,
                    json.dumps(projection, ensure_ascii=False, sort_keys=True),
                    stable_hash(projection),
                    now_iso(),
                ),
            )
        return self.worldline(str(values["id"])) or {}

    def create_crisis_run_bundle(
        self,
        values: dict[str, Any],
        events: list[dict[str, Any]],
        lifetimes: list[dict[str, Any]],
        projection: dict[str, Any],
    ) -> dict[str, Any]:
        """Create one Crisis Run, actor life states, ledger, and first snapshot atomically."""

        worldline = {
            "id": values["id"],
            "scenario_id": values.get("scenario_id", "jiashen"),
            "kind": "CRISIS",
            "status": "ACTIVE",
            "entry_id": "",
            "controller_seat": "",
            "current_tick": int(values.get("current_tick", 0)),
            "runtime_epoch": values.get("runtime_epoch", ""),
            "runtime_mode": values.get("runtime_mode", "fixture"),
            "runtime_phase": values.get("runtime_phase", "READY"),
            "runtime_error_code": values.get("runtime_error_code", ""),
            "seal_reason": "",
            "outcome": "",
            "pending_confirmation_json": "",
            "crisis_id": values["crisis_id"],
            "volume_id": values.get("volume_id", ""),
            "crisis_version": int(values.get("crisis_version", 0)),
            "crisis_hash": values.get("crisis_hash", ""),
            "resolution_contract_id": values.get("resolution_contract_id", ""),
            "resolution_contract_version": int(values.get("resolution_contract_version", 0)),
            "resolution_seed": values.get("resolution_seed", ""),
            "crisis_phase": values.get("crisis_phase", "OPEN"),
            "outcome_json": json.dumps(values.get("outcome", {}), ensure_ascii=False, sort_keys=True),
            "settlement_reason": values.get("settlement_reason", ""),
            "controller_map_json": json.dumps(
                values["controller_map"], ensure_ascii=False, sort_keys=True
            ),
            "simulation_boundary_json": json.dumps(
                values["simulation_boundary"], ensure_ascii=False, sort_keys=True
            ),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldlines(id, scenario_id, kind, status, entry_id, controller_seat, "
                "current_tick, runtime_epoch, runtime_mode, runtime_phase, runtime_error_code, "
                "seal_reason, outcome, "
                "pending_confirmation_json, crisis_id, volume_id, crisis_version, crisis_hash, "
                "resolution_contract_id, resolution_contract_version, resolution_seed, crisis_phase, "
                "outcome_json, settlement_reason, controller_map_json, "
                "simulation_boundary_json, created_at, updated_at) "
                "VALUES (:id, :scenario_id, :kind, :status, :entry_id, :controller_seat, "
                ":current_tick, :runtime_epoch, :runtime_mode, :runtime_phase, :runtime_error_code, "
                ":seal_reason, :outcome, "
                ":pending_confirmation_json, :crisis_id, :volume_id, :crisis_version, :crisis_hash, "
                ":resolution_contract_id, :resolution_contract_version, :resolution_seed, :crisis_phase, "
                ":outcome_json, :settlement_reason, :controller_map_json, "
                ":simulation_boundary_json, :created_at, :updated_at)",
                worldline,
            )
            last_sequence = 0
            for event in events:
                last_sequence = self._insert_worldline_event(connection, values["id"], event)
            for lifetime in lifetimes:
                connection.execute(
                    "INSERT INTO worldline_lifetimes(id, worldline_id, seat, controller, status, "
                    "parent_canon_lifetime, profile_name, profile_metadata_json, genesis_hash, "
                    "memory_text, memory_hash, knowledge_json, belief_json, authority_json, "
                    "role_charter_json, plan_json, commitments_json, resources_json, "
                    "last_perspective_json, revisits_json, wake_count, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :seat, :controller, 'ACTIVE', '', :profile_name, "
                    ":profile_metadata_json, :genesis_hash, :memory_text, :memory_hash, "
                    ":knowledge_json, :belief_json, :authority_json, :role_charter_json, "
                    ":plan_json, :commitments_json, :resources_json, :last_perspective_json, "
                    ":revisits_json, 0, :created_at, :updated_at)",
                    {
                        "id": lifetime["id"],
                        "worldline_id": values["id"],
                        "seat": lifetime["actor_id"],
                        "controller": lifetime["controller"],
                        "profile_name": lifetime.get("profile_name", ""),
                        "profile_metadata_json": json.dumps(
                            lifetime.get("profile_metadata", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "genesis_hash": lifetime.get("genesis_hash", ""),
                        "memory_text": lifetime.get("memory_text", ""),
                        "memory_hash": lifetime.get("memory_hash", ""),
                        "knowledge_json": json.dumps(
                            lifetime.get("knowledge", []), ensure_ascii=False, sort_keys=True
                        ),
                        "belief_json": json.dumps(
                            lifetime.get("beliefs", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "authority_json": json.dumps(
                            lifetime.get("authority", []), ensure_ascii=False, sort_keys=True
                        ),
                        "role_charter_json": json.dumps(
                            lifetime.get("role_charter", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "plan_json": json.dumps(
                            lifetime.get("plan", []), ensure_ascii=False, sort_keys=True
                        ),
                        "commitments_json": json.dumps(
                            lifetime.get("commitments", []), ensure_ascii=False, sort_keys=True
                        ),
                        "resources_json": json.dumps(
                            lifetime.get("resources", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "last_perspective_json": json.dumps(
                            lifetime.get("last_perspective", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "revisits_json": json.dumps(
                            lifetime.get("revisits", []), ensure_ascii=False, sort_keys=True
                        ),
                        "created_at": lifetime.get("created_at", now_iso()),
                        "updated_at": lifetime.get("updated_at", now_iso()),
                    },
                )
                connection.execute(
                    "INSERT INTO memory_versions(id, seat, memory_text, previous_hash, "
                    "memory_hash, mutation_kind, source_record_ids, created_at) "
                    "VALUES (?, ?, ?, '', ?, 'genesis', ?, ?)",
                    (
                        f"memory-{uuid.uuid4().hex[:12]}",
                        f"{values['id']}:{lifetime['actor_id']}",
                        lifetime.get("memory_text", ""),
                        lifetime.get("memory_hash", ""),
                        json.dumps([events[0]["id"]], ensure_ascii=False),
                        lifetime.get("created_at", now_iso()),
                    ),
                )
            self._insert_snapshot(
                connection,
                {
                    "worldline_id": values["id"],
                    "tick": worldline["current_tick"],
                    "ledger_cursor": last_sequence,
                    "projection": projection,
                },
            )
        return self.active_run() or {}

    def update_worldline(
        self,
        worldline_id: str,
        *,
        current_tick: int | None = None,
        status: str | None = None,
        seal_reason: str | None = None,
        outcome: str | None = None,
        pending_confirmation_json: str | None = None,
    ) -> None:
        current = self.worldline(worldline_id)
        if current is None:
            raise KeyError(f"worldline not found: {worldline_id}")
        if current["status"] == "SEALED" and status != "SEALED":
            raise sqlite3.IntegrityError("worldline is sealed")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE worldlines SET current_tick = ?, status = ?, seal_reason = ?, outcome = ?, "
                "pending_confirmation_json = ?, updated_at = ? WHERE id = ?",
                (
                    current["current_tick"] if current_tick is None else current_tick,
                    current["status"] if status is None else status,
                    current["seal_reason"] if seal_reason is None else seal_reason,
                    current["outcome"] if outcome is None else outcome,
                    current["pending_confirmation_json"]
                    if pending_confirmation_json is None
                    else pending_confirmation_json,
                    now_iso(),
                    worldline_id,
                ),
            )

    def set_crisis_runtime_state(
        self,
        worldline_id: str,
        phase: str,
        *,
        error_code: str = "",
    ) -> dict[str, Any]:
        valid = {
            "BOOTSTRAPPING",
            "READY",
            "RECONCILING",
            "FAILED",
            "SEALING",
            "CLEANUP_PENDING",
        }
        if phase not in valid:
            raise ValueError(f"unknown crisis runtime phase: {phase}")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT kind, status FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if row is None or row["kind"] != "CRISIS":
                raise sqlite3.IntegrityError("crisis Run does not exist")
            if row["status"] == "SEALED" and phase != "CLEANUP_PENDING":
                raise sqlite3.IntegrityError("sealed Run only supports cleanup")
            if row["status"] != "SEALED" and phase == "CLEANUP_PENDING":
                raise sqlite3.IntegrityError("active Run cannot enter cleanup")
            connection.execute(
                "UPDATE worldlines SET runtime_phase = ?, runtime_error_code = ?, updated_at = ? "
                "WHERE id = ?",
                (phase, error_code, now_iso(), worldline_id),
            )
        return self.worldline(worldline_id) or {}

    def append_worldline_event(
        self,
        worldline_id: str,
        tick: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        seat_id: str | None = None,
        provenance: str = "branch_derived",
        causal_parent_ids: list[str] | None = None,
        runtime_epoch: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": event_id or f"wle-{uuid.uuid4().hex[:16]}",
            "worldline_id": worldline_id,
            "tick": tick,
            "event_type": event_type,
            "seat_id": seat_id,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "provenance": provenance,
            "causal_parent_ids": json.dumps(causal_parent_ids or [], ensure_ascii=False),
            "runtime_epoch": runtime_epoch,
            "created_at": now_iso(),
        }
        with self.transaction() as connection:
            worldline = connection.execute(
                "SELECT status FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if worldline is None:
                raise sqlite3.IntegrityError("worldline does not exist")
            if worldline["status"] == "SEALED":
                raise sqlite3.IntegrityError("worldline is sealed")
            cursor = connection.execute(
                "INSERT INTO worldline_events(id, worldline_id, tick, event_type, seat_id, payload_json, "
                "provenance, causal_parent_ids, runtime_epoch, created_at) "
                "VALUES (:id, :worldline_id, :tick, :event_type, :seat_id, :payload_json, :provenance, "
                ":causal_parent_ids, :runtime_epoch, :created_at)",
                record,
            )
            record["sequence"] = cursor.lastrowid
        record["payload"] = payload
        record["causal_parent_ids"] = causal_parent_ids or []
        return record

    @staticmethod
    def _insert_worldline_event(
        connection: sqlite3.Connection, worldline_id: str, event: dict[str, Any]
    ) -> int:
        record = {
            "id": event["id"],
            "worldline_id": worldline_id,
            "tick": int(event["tick"]),
            "event_type": event["event_type"],
            "seat_id": event.get("seat_id"),
            "payload_json": json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=True),
            "provenance": event.get("provenance", "branch_derived"),
            "causal_parent_ids": json.dumps(event.get("causal_parent_ids", []), ensure_ascii=False),
            "runtime_epoch": event.get("runtime_epoch"),
            "created_at": event.get("created_at", now_iso()),
        }
        cursor = connection.execute(
            "INSERT INTO worldline_events(id, worldline_id, tick, event_type, seat_id, payload_json, "
            "provenance, causal_parent_ids, runtime_epoch, created_at) "
            "VALUES (:id, :worldline_id, :tick, :event_type, :seat_id, :payload_json, :provenance, "
            ":causal_parent_ids, :runtime_epoch, :created_at)",
            record,
        )
        return int(cursor.lastrowid or 0)

    @staticmethod
    def _insert_snapshot(connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        projection = record.get("projection")
        if projection is not None:
            record = {
                "worldline_id": record["worldline_id"],
                "tick": int(record["tick"]),
                "ledger_cursor": int(record["ledger_cursor"]),
                "projection_json": json.dumps(projection, ensure_ascii=False, sort_keys=True),
                "projection_hash": stable_hash(projection),
                "created_at": record.get("created_at", now_iso()),
            }
        connection.execute(
            "INSERT INTO worldline_snapshot_history(worldline_id, tick, ledger_cursor, projection_json, "
            "projection_hash, created_at) VALUES (:worldline_id, :tick, :ledger_cursor, :projection_json, "
            ":projection_hash, :created_at)",
            record,
        )

    def commit_worldline_moment(
        self,
        worldline_id: str,
        events: list[dict[str, Any]],
        *,
        current_tick: int,
        lifetime_updates: list[dict[str, Any]] | None = None,
        memory_versions: list[dict[str, Any]] | None = None,
        snapshot: dict[str, Any] | None = None,
        crisis_phase: str | None = None,
        outcome_json: str | None = None,
        settlement_reason: str | None = None,
        pending_confirmation_json: str | None = None,
        expected_pending_confirmation_json: str | None = None,
        expected_current_tick: int | None = None,
    ) -> list[dict[str, Any]]:
        """Commit a prepared moment and its branch-lifetime updates atomically."""

        committed: list[dict[str, Any]] = []
        with self.transaction() as connection:
            for event in events:
                record = {
                    "id": event["id"],
                    "worldline_id": worldline_id,
                    "tick": int(event["tick"]),
                    "event_type": event["event_type"],
                    "seat_id": event.get("seat_id"),
                    "payload_json": json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=True),
                    "provenance": event.get("provenance", "branch_derived"),
                    "causal_parent_ids": json.dumps(
                        event.get("causal_parent_ids", []), ensure_ascii=False
                    ),
                    "runtime_epoch": event.get("runtime_epoch"),
                    "created_at": event.get("created_at", now_iso()),
                }
                cursor = connection.execute(
                    "INSERT INTO worldline_events(id, worldline_id, tick, event_type, seat_id, payload_json, "
                    "provenance, causal_parent_ids, runtime_epoch, created_at) "
                    "VALUES (:id, :worldline_id, :tick, :event_type, :seat_id, :payload_json, :provenance, "
                    ":causal_parent_ids, :runtime_epoch, :created_at)",
                    record,
                )
                committed_record = dict(event)
                committed_record["sequence"] = cursor.lastrowid
                committed_record["worldline_id"] = worldline_id
                committed_record["created_at"] = record["created_at"]
                committed.append(committed_record)

            update_sql = "UPDATE worldlines SET current_tick = ?, updated_at = ?"
            update_args: list[Any] = [current_tick, now_iso()]
            if pending_confirmation_json is not None:
                update_sql += ", pending_confirmation_json = ?"
                update_args.append(pending_confirmation_json)
            if crisis_phase is not None:
                update_sql += ", crisis_phase = ?"
                update_args.append(crisis_phase)
            if outcome_json is not None:
                update_sql += ", outcome_json = ?"
                update_args.append(outcome_json)
            if settlement_reason is not None:
                update_sql += ", settlement_reason = ?"
                update_args.append(settlement_reason)
            update_sql += " WHERE id = ? AND status = 'ACTIVE'"
            update_args.append(worldline_id)
            if expected_current_tick is not None:
                update_sql += " AND current_tick = ?"
                update_args.append(expected_current_tick)
            if expected_pending_confirmation_json is not None:
                update_sql += " AND pending_confirmation_json = ?"
                update_args.append(expected_pending_confirmation_json)
            cursor = connection.execute(update_sql, update_args)
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError("worldline state changed before the moment was committed")
            for update in lifetime_updates or []:
                allowed = {
                    "status",
                    "profile_name",
                    "profile_metadata_json",
                    "memory_text",
                    "memory_hash",
                    "knowledge_json",
                    "belief_json",
                    "authority_json",
                    "role_charter_json",
                    "plan_json",
                    "commitments_json",
                    "revisits_json",
                    "resources_json",
                    "last_perspective_json",
                    "wake_count",
                }
                values = {key: value for key, value in update.items() if key in allowed}
                if not values:
                    raise sqlite3.IntegrityError(
                        f"branch lifetime update has no writable fields for seat {update.get('seat', '')}"
                    )
                assignments = ", ".join(f"{key} = :{key}" for key in values)
                values.update(
                    {
                        "updated_at": now_iso(),
                        "worldline_id": worldline_id,
                        "seat": update["seat"],
                    }
                )
                updated = connection.execute(
                    f"UPDATE worldline_lifetimes SET {assignments}, updated_at = :updated_at "
                    "WHERE worldline_id = :worldline_id AND seat = :seat",
                    values,
                )
                if updated.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        f"branch lifetime is missing for seat {update.get('seat', '')}"
                    )
            for memory_version in memory_versions or []:
                self._insert_memory_version(connection, memory_version)
            if snapshot is not None:
                ledger_cursor = int(committed[-1]["sequence"]) if committed else int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sequence), 0) FROM worldline_events WHERE worldline_id = ?",
                        (worldline_id,),
                    ).fetchone()[0]
                )
                self._insert_snapshot(
                    connection,
                    {
                        "worldline_id": worldline_id,
                        "tick": current_tick,
                        "ledger_cursor": ledger_cursor,
                        "projection": snapshot,
                    },
                )
        return committed

    def commit_worldline_seal(
        self,
        worldline_id: str,
        event: dict[str, Any],
        *,
        reason: str,
        outcome: str,
        pre_events: list[dict[str, Any]] | None = None,
        snapshot: dict[str, Any] | None = None,
        revoke_agent_bindings: bool = False,
        runtime_phase: str | None = None,
        runtime_error_code: str = "",
        cancel_queued_wakes: bool = False,
        crisis_phase: str | None = None,
        outcome_json: str | None = None,
        settlement_reason: str | None = None,
        current_tick: int | None = None,
    ) -> dict[str, Any]:
        """Seal a Worldline, its event ledger, and all branch lifetimes atomically."""

        record = {
            "id": event["id"],
            "worldline_id": worldline_id,
            "tick": int(event["tick"]),
            "event_type": event["event_type"],
            "seat_id": event.get("seat_id"),
            "payload_json": json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=True),
            "provenance": event.get("provenance", "branch_derived"),
            "causal_parent_ids": json.dumps(event.get("causal_parent_ids", []), ensure_ascii=False),
            "runtime_epoch": event.get("runtime_epoch"),
            "created_at": event.get("created_at", now_iso()),
        }
        with self.transaction() as connection:
            worldline = connection.execute(
                "SELECT status FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if worldline is None:
                raise sqlite3.IntegrityError("worldline does not exist")
            if worldline["status"] != "ACTIVE":
                raise sqlite3.IntegrityError("worldline is no longer active")
            for pre_event in pre_events or []:
                self._insert_worldline_event(connection, worldline_id, pre_event)
            seal_cursor = self._insert_worldline_event(connection, worldline_id, event)
            runtime_sql = ", runtime_phase = ?, runtime_error_code = ?" if runtime_phase else ""
            runtime_args: tuple[Any, ...] = (
                (runtime_phase, runtime_error_code) if runtime_phase else ()
            )
            crisis_sql = ""
            crisis_args: tuple[Any, ...] = ()
            if crisis_phase is not None:
                crisis_sql += ", crisis_phase = ?"
                crisis_args += (crisis_phase,)
            if outcome_json is not None:
                crisis_sql += ", outcome_json = ?"
                crisis_args += (outcome_json,)
            if settlement_reason is not None:
                crisis_sql += ", settlement_reason = ?"
                crisis_args += (settlement_reason,)
            if current_tick is not None:
                crisis_sql += ", current_tick = ?"
                crisis_args += (current_tick,)
            updated = connection.execute(
                "UPDATE worldlines SET status = 'SEALED', seal_reason = ?, outcome = ?, "
                "pending_confirmation_json = ''"
                + runtime_sql
                + crisis_sql
                + ", updated_at = ? WHERE id = ? AND status = 'ACTIVE'",
                (reason, outcome, *runtime_args, *crisis_args, now_iso(), worldline_id),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("worldline is no longer active")
            connection.execute(
                "UPDATE worldline_lifetimes SET status = 'SEALED', updated_at = ? WHERE worldline_id = ?",
                (now_iso(), worldline_id),
            )
            if revoke_agent_bindings:
                changed_at = now_iso()
                connection.execute(
                    "UPDATE worldline_agent_bindings SET status = 'REVOKED', revoked_at = ?, "
                    "updated_at = ? WHERE worldline_id = ? AND status = 'ACTIVE'",
                    (changed_at, changed_at, worldline_id),
                )
            if cancel_queued_wakes:
                connection.execute(
                    "UPDATE crisis_wakes SET status = 'CANCELLED', updated_at = ? "
                    "WHERE worldline_id = ? AND status = 'QUEUED'",
                    (now_iso(), worldline_id),
                )
            if snapshot is not None:
                self._insert_snapshot(
                    connection,
                    {
                        "worldline_id": worldline_id,
                        "tick": int(event["tick"]),
                        "ledger_cursor": int(seal_cursor),
                        "projection": snapshot,
                    },
                )
        committed = dict(event)
        committed["worldline_id"] = worldline_id
        committed["created_at"] = record["created_at"]
        committed["sequence"] = seal_cursor
        return committed

    def worldline_events(self, worldline_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM worldline_events WHERE worldline_id = ? ORDER BY sequence", (worldline_id,)
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            item["causal_parent_ids"] = json.loads(item["causal_parent_ids"])
            records.append(item)
        return records

    def append_worldline_snapshot(
        self, worldline_id: str, tick: int, ledger_cursor: int, projection: dict[str, Any]
    ) -> dict[str, Any]:
        record = {
            "worldline_id": worldline_id,
            "tick": tick,
            "ledger_cursor": ledger_cursor,
            "projection_json": json.dumps(projection, ensure_ascii=False, sort_keys=True),
            "projection_hash": stable_hash(projection),
            "created_at": now_iso(),
        }
        with self.transaction() as connection:
            self._insert_snapshot(connection, record)
        return record

    def worldline_snapshot(self, worldline_id: str, tick: int | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM worldline_snapshot_history WHERE worldline_id = ?"
        args: tuple[Any, ...] = (worldline_id,)
        if tick is not None:
            query += " AND tick = ?"
            args += (tick,)
        query += " ORDER BY tick DESC, ledger_cursor DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, args).fetchone()
            if not row:
                legacy_query = "SELECT * FROM worldline_snapshots WHERE worldline_id = ?"
                legacy_args: tuple[Any, ...] = (worldline_id,)
                if tick is not None:
                    legacy_query += " AND tick = ?"
                    legacy_args += (tick,)
                legacy_query += " ORDER BY tick DESC LIMIT 1"
                row = connection.execute(legacy_query, legacy_args).fetchone()
        if not row:
            return None
        item = dict(row)
        item["projection"] = json.loads(item.pop("projection_json"))
        return item

    def create_worldline_lifetime(self, values: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": values["id"],
            "worldline_id": values["worldline_id"],
            "seat": values["seat"],
            "controller": values["controller"],
            "status": values.get("status", "ACTIVE"),
            "parent_canon_lifetime": values.get("parent_canon_lifetime", ""),
            "profile_name": values.get("profile_name", ""),
            "profile_metadata_json": json.dumps(values.get("profile_metadata", {}), ensure_ascii=False),
            "genesis_hash": values.get("genesis_hash", ""),
            "memory_text": values.get("memory_text", ""),
            "memory_hash": values.get("memory_hash", ""),
            "knowledge_json": json.dumps(values.get("knowledge", []), ensure_ascii=False),
            "belief_json": json.dumps(values.get("beliefs", {}), ensure_ascii=False, sort_keys=True),
            "authority_json": json.dumps(values.get("authority", []), ensure_ascii=False),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldline_lifetimes(id, worldline_id, seat, controller, status, "
                "parent_canon_lifetime, profile_name, profile_metadata_json, genesis_hash, memory_text, memory_hash, "
                "knowledge_json, belief_json, authority_json, created_at, updated_at) VALUES "
                "(:id, :worldline_id, :seat, :controller, :status, :parent_canon_lifetime, :profile_name, "
                ":profile_metadata_json, :genesis_hash, :memory_text, :memory_hash, :knowledge_json, :belief_json, "
                ":authority_json, :created_at, :updated_at)",
                record,
            )
        return self.worldline_lifetime(str(values["worldline_id"]), str(values["seat"])) or {}

    def worldline_lifetime(self, worldline_id: str, seat: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldline_lifetimes WHERE worldline_id = ? AND seat = ?",
                (worldline_id, seat),
            ).fetchone()
        return self._decode_worldline_lifetime(row) if row else None

    def worldline_lifetimes(self, worldline_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM worldline_lifetimes WHERE worldline_id = ? ORDER BY seat", (worldline_id,)
            ).fetchall()
        return [self._decode_worldline_lifetime(row) for row in rows]

    @staticmethod
    def _decode_worldline_lifetime(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in (
            "profile_metadata_json",
            "knowledge_json",
            "belief_json",
            "authority_json",
            "role_charter_json",
            "plan_json",
            "commitments_json",
            "revisits_json",
            "resources_json",
            "last_perspective_json",
        ):
            if key not in item:
                continue
            decoded_key = key.removesuffix("_json")
            item[decoded_key] = json.loads(item.pop(key))
        item["beliefs"] = item["belief"]
        return item

    def update_worldline_lifetime(self, worldline_id: str, seat: str, **values: Any) -> None:
        allowed = {
            "status",
            "profile_name",
            "profile_metadata_json",
            "genesis_hash",
            "memory_text",
            "memory_hash",
            "knowledge_json",
            "belief_json",
            "authority_json",
            "role_charter_json",
            "plan_json",
            "commitments_json",
            "revisits_json",
            "resources_json",
            "last_perspective_json",
            "wake_count",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates.update({"worldline_id": worldline_id, "seat": seat, "updated_at": now_iso()})
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE worldline_lifetimes SET {assignments}, updated_at = :updated_at "
                "WHERE worldline_id = :worldline_id AND seat = :seat",
                updates,
            )

    def create_agent_binding(self, values: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": values.get("id", f"binding-{uuid.uuid4().hex[:16]}"),
            "worldline_id": values["worldline_id"],
            "role": values["actor_id"],
            "profile_identity": values["profile_name"],
            "distribution_version": values.get("distribution_version", "chronicle-actor-v3"),
            "ownership_marker": values["ownership_marker"],
            "status": values.get("status", "ACTIVE"),
            "token_hash": values["token_hash"],
            "revoked_at": "",
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldline_agent_bindings(id, worldline_id, role, profile_identity, "
                "distribution_version, ownership_marker, status, token_hash, revoked_at, "
                "created_at, updated_at) VALUES (:id, :worldline_id, :role, :profile_identity, "
                ":distribution_version, :ownership_marker, :status, :token_hash, :revoked_at, "
                ":created_at, :updated_at)",
                record,
            )
        return record

    def activate_crisis_runtime(
        self,
        worldline_id: str,
        bindings: list[dict[str, Any]],
        wakes: list[dict[str, Any]],
    ) -> None:
        """Authorize one bootstrapped live Run and queue its initial Wakes atomically."""

        with self.transaction() as connection:
            run = connection.execute(
                "SELECT kind, status FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
                raise sqlite3.IntegrityError("crisis Run is not active")
            for values in bindings:
                existing = connection.execute(
                    "SELECT profile_identity, ownership_marker, token_hash, status "
                    "FROM worldline_agent_bindings WHERE worldline_id = ? AND role = ?",
                    (worldline_id, values["actor_id"]),
                ).fetchone()
                if existing is not None:
                    matches = (
                        existing["profile_identity"] == values["profile_name"]
                        and existing["ownership_marker"] == values["ownership_marker"]
                        and existing["token_hash"] == values["token_hash"]
                        and existing["status"] == "ACTIVE"
                    )
                    if not matches:
                        raise sqlite3.IntegrityError("crisis binding does not match bootstrap identity")
                    continue
                record = {
                    "id": values.get("id", f"binding-{uuid.uuid4().hex[:16]}"),
                    "worldline_id": worldline_id,
                    "role": values["actor_id"],
                    "profile_identity": values["profile_name"],
                    "distribution_version": values.get("distribution_version", "chronicle-actor-v3"),
                    "ownership_marker": values["ownership_marker"],
                    "status": "ACTIVE",
                    "token_hash": values["token_hash"],
                    "revoked_at": "",
                    "created_at": values.get("created_at", now_iso()),
                    "updated_at": values.get("updated_at", now_iso()),
                }
                connection.execute(
                    "INSERT INTO worldline_agent_bindings(id, worldline_id, role, profile_identity, "
                    "distribution_version, ownership_marker, status, token_hash, revoked_at, "
                    "created_at, updated_at) VALUES (:id, :worldline_id, :role, :profile_identity, "
                    ":distribution_version, :ownership_marker, :status, :token_hash, :revoked_at, "
                    ":created_at, :updated_at)",
                    record,
                )
            for values in wakes:
                existing = connection.execute(
                    "SELECT id FROM crisis_wakes WHERE worldline_id = ? AND actor_id = ? "
                    "AND wake_type = ? AND tick = ? AND trigger_event_id = ?",
                    (
                        worldline_id,
                        values["actor_id"],
                        values["wake_type"],
                        int(values["tick"]),
                        values.get("trigger_event_id", ""),
                    ),
                ).fetchone()
                if existing is not None:
                    continue
                record = {
                    "id": values.get("id", f"wake-{uuid.uuid4().hex[:16]}"),
                    "worldline_id": worldline_id,
                    "actor_id": values["actor_id"],
                    "wake_type": values["wake_type"],
                    "tick": int(values["tick"]),
                    "status": "QUEUED",
                    "source": values.get("source", "hermes"),
                    "trigger_event_id": values.get("trigger_event_id", ""),
                    "hermes_session_id": "",
                    "frozen_perspective_json": "{}",
                    "result_json": "{}",
                    "error_json": "{}",
                    "created_at": values.get("created_at", now_iso()),
                    "updated_at": values.get("updated_at", now_iso()),
                }
                connection.execute(
                    "INSERT INTO crisis_wakes(id, worldline_id, actor_id, wake_type, tick, status, "
                    "source, trigger_event_id, hermes_session_id, frozen_perspective_json, "
                    "result_json, error_json, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :actor_id, :wake_type, :tick, :status, :source, "
                    ":trigger_event_id, :hermes_session_id, :frozen_perspective_json, "
                    ":result_json, :error_json, :created_at, :updated_at)",
                    record,
                )
            connection.execute(
                "UPDATE worldlines SET runtime_phase = 'BOOTSTRAPPING', runtime_error_code = '', "
                "updated_at = ? WHERE id = ?",
                (now_iso(), worldline_id),
            )

    def agent_binding_for_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldline_agent_bindings "
                "WHERE token_hash = ? AND status = 'ACTIVE'",
                (token_hash,),
            ).fetchone()
        return dict(row) if row else None

    def agent_bindings(self, worldline_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM worldline_agent_bindings WHERE worldline_id = ? ORDER BY role",
                (worldline_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_agent_bindings(self, worldline_id: str) -> None:
        changed_at = now_iso()
        with self.transaction() as connection:
            connection.execute(
                "UPDATE worldline_agent_bindings SET status = 'REVOKED', revoked_at = ?, "
                "updated_at = ? WHERE worldline_id = ? AND status = 'ACTIVE'",
                (changed_at, changed_at, worldline_id),
            )

    def nonterminal_crisis_wakes(self, worldline_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM crisis_wakes WHERE worldline_id = ? "
                "AND status IN ('QUEUED', 'RUNNING', 'STAGED') ORDER BY tick, actor_id, id",
                (worldline_id,),
            ).fetchall()
        return [self._decode_crisis_wake(row) for row in rows]

    def create_crisis_wake(self, values: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": values.get("id", f"wake-{uuid.uuid4().hex[:16]}"),
            "worldline_id": values["worldline_id"],
            "actor_id": values["actor_id"],
            "wake_type": values["wake_type"],
            "tick": int(values["tick"]),
            "status": values.get("status", "QUEUED"),
            "source": values.get("source", "fixture"),
            "trigger_event_id": values.get("trigger_event_id", ""),
            "hermes_session_id": values.get("hermes_session_id", ""),
            "frozen_perspective_json": json.dumps(
                values.get("frozen_perspective", {}), ensure_ascii=False, sort_keys=True
            ),
            "result_json": json.dumps(values.get("result", {}), ensure_ascii=False, sort_keys=True),
            "error_json": json.dumps(values.get("error", {}), ensure_ascii=False, sort_keys=True),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO crisis_wakes(id, worldline_id, actor_id, wake_type, tick, status, "
                "source, trigger_event_id, hermes_session_id, frozen_perspective_json, "
                "result_json, error_json, created_at, updated_at) "
                "VALUES (:id, :worldline_id, :actor_id, :wake_type, :tick, :status, :source, "
                ":trigger_event_id, :hermes_session_id, :frozen_perspective_json, "
                ":result_json, :error_json, :created_at, :updated_at)",
                record,
            )
        return self.crisis_wake(record["id"]) or {}

    def crisis_wake(self, wake_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crisis_wakes WHERE id = ?", (wake_id,)
            ).fetchone()
        return self._decode_crisis_wake(row) if row else None

    def crisis_wakes(
        self,
        worldline_id: str,
        *,
        status: str | None = None,
        tick: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM crisis_wakes WHERE worldline_id = ?"
        args: list[Any] = [worldline_id]
        if status is not None:
            query += " AND status = ?"
            args.append(status)
        if tick is not None:
            query += " AND tick = ?"
            args.append(tick)
        query += " ORDER BY tick, actor_id, created_at"
        with self._connect() as connection:
            rows = connection.execute(query, args).fetchall()
        return [self._decode_crisis_wake(row) for row in rows]

    def running_crisis_wake(self, worldline_id: str, actor_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crisis_wakes WHERE worldline_id = ? AND actor_id = ? "
                "AND status = 'RUNNING' ORDER BY updated_at DESC LIMIT 1",
                (worldline_id, actor_id),
            ).fetchone()
        return self._decode_crisis_wake(row) if row else None

    @staticmethod
    def _decode_crisis_wake(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("frozen_perspective_json", "result_json", "error_json"):
            item[key.removesuffix("_json")] = json.loads(item.pop(key))
        return item

    def update_crisis_wake(self, wake_id: str, **values: Any) -> None:
        allowed = {"status", "hermes_session_id"}
        updates = {key: value for key, value in values.items() if key in allowed}
        for key in ("frozen_perspective", "result", "error"):
            if key in values:
                updates[f"{key}_json"] = json.dumps(
                    values[key], ensure_ascii=False, sort_keys=True
                )
        if not updates:
            return
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        updates.update({"id": wake_id, "updated_at": now_iso()})
        with self.transaction() as connection:
            changed = connection.execute(
                f"UPDATE crisis_wakes SET {assignments}, updated_at = :updated_at WHERE id = :id",
                updates,
            )
            if changed.rowcount != 1:
                raise KeyError(f"wake not found: {wake_id}")

    def add_crisis_wake_operation(self, values: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": values.get("id", f"op-{uuid.uuid4().hex[:16]}"),
            "wake_id": values["wake_id"],
            "tool_name": values["tool_name"],
            "payload_json": json.dumps(values["payload"], ensure_ascii=False, sort_keys=True),
            "result_json": json.dumps(values["result"], ensure_ascii=False, sort_keys=True),
            "status": values.get("status", "PROPOSED"),
            "idempotency_key": values["idempotency_key"],
            "created_at": values.get("created_at", now_iso()),
        }
        with self.transaction() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO crisis_wake_operations(id, wake_id, tool_name, payload_json, "
                    "result_json, status, idempotency_key, created_at) "
                    "VALUES (:id, :wake_id, :tool_name, :payload_json, :result_json, :status, "
                    ":idempotency_key, :created_at)",
                    record,
                )
            except sqlite3.IntegrityError:
                existing = connection.execute(
                    "SELECT * FROM crisis_wake_operations "
                    "WHERE wake_id = ? AND idempotency_key = ?",
                    (record["wake_id"], record["idempotency_key"]),
                ).fetchone()
                if existing is None:
                    raise
                return self._decode_crisis_wake_operation(existing)
            record["sequence"] = int(cursor.lastrowid or 0)
        return self._decode_crisis_wake_operation(record)

    def update_crisis_wake_operation_status(
        self,
        operation_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        updates: dict[str, Any] = {"status": status, "id": operation_id}
        if result is not None:
            updates["result_json"] = json.dumps(result, ensure_ascii=False, sort_keys=True)
        assignments = ", ".join(
            f"{key} = :{key}" for key in updates if key != "id"
        )
        with self.transaction() as connection:
            changed = connection.execute(
                f"UPDATE crisis_wake_operations SET {assignments} WHERE id = :id",
                updates,
            )
            if changed.rowcount != 1:
                raise KeyError(f"wake operation not found: {operation_id}")

    def crisis_wake_operations(self, wake_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM crisis_wake_operations WHERE wake_id = ? ORDER BY sequence",
                (wake_id,),
            ).fetchall()
        return [self._decode_crisis_wake_operation(row) for row in rows]

    @staticmethod
    def _decode_crisis_wake_operation(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        item["result"] = json.loads(item.pop("result_json"))
        return item

    def ensure_epoch(self, values: dict[str, str]) -> str:
        fingerprint = stable_hash(values)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM runtime_epochs WHERE provider_base_url_hash = ? AND model = ? AND api_mode = ? AND reasoning_effort = ? AND soul_hash = ? AND skill_hash = ? AND toolset_hash = ? ORDER BY changed_at DESC LIMIT 1",
                (
                    values["provider_base_url_hash"],
                    values["model"],
                    values["api_mode"],
                    values["reasoning_effort"],
                    values["soul_hash"],
                    values["skill_hash"],
                    values["toolset_hash"],
                ),
            ).fetchone()
        if row:
            return str(row["id"])
        epoch_id = f"epoch-{fingerprint[:12]}"
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO runtime_epochs(id, hermes_version, provider_base_url_hash, model, api_mode, reasoning_effort, soul_hash, skill_hash, toolset_hash, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    epoch_id,
                    values["hermes_version"],
                    values["provider_base_url_hash"],
                    values["model"],
                    values["api_mode"],
                    values["reasoning_effort"],
                    values["soul_hash"],
                    values["skill_hash"],
                    values["toolset_hash"],
                    now_iso(),
                ),
            )
        return epoch_id

    def current_beliefs(self, seat: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT belief_key, confidence, direction, statement, updated_tick FROM beliefs WHERE seat = ? ORDER BY belief_key",
                (seat,),
            ).fetchall()
        return {row["belief_key"]: dict(row) for row in rows}

    def update_beliefs(self, seat: str, tick: int, updates: list[dict[str, Any]]) -> None:
        with self.transaction() as connection:
            for update in updates:
                connection.execute(
                    "INSERT INTO beliefs(seat, belief_key, confidence, direction, statement, updated_tick) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(seat, belief_key) DO UPDATE SET confidence=excluded.confidence, direction=excluded.direction, statement=excluded.statement, updated_tick=excluded.updated_tick",
                    (
                        seat,
                        update["belief_key"],
                        float(update["confidence"]),
                        update["direction"],
                        update.get("statement", ""),
                        tick,
                    ),
                )

    def memory_versions(self, seat: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_versions WHERE seat = ? ORDER BY created_at",
                (seat,),
            ).fetchall()
        return [dict(row) for row in rows]

    def current_memory(self, seat: str) -> tuple[str, str]:
        versions = self.memory_versions(seat)
        if not versions:
            return "", stable_hash("")
        latest = versions[-1]
        return str(latest["memory_text"]), str(latest["memory_hash"])

    def add_memory_version(
        self,
        seat: str,
        memory_text: str,
        previous_hash: str,
        source_record_ids: list[str],
        mutation_kind: str,
        *,
        memory_hash: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": f"memory-{uuid.uuid4().hex[:12]}",
            "seat": seat,
            "memory_text": memory_text,
            "previous_hash": previous_hash,
            "memory_hash": memory_hash or stable_hash(memory_text),
            "mutation_kind": mutation_kind,
            "source_record_ids": json.dumps(source_record_ids, ensure_ascii=False),
            "created_at": now_iso(),
        }
        with self.transaction() as connection:
            self._insert_memory_version(connection, record)
        return record

    @staticmethod
    def _insert_memory_version(
        connection: sqlite3.Connection, record: dict[str, Any]
    ) -> None:
        if record["mutation_kind"] != "reflection":
            raise ValueError("Memory can only be mutated by a reflection")
        latest = connection.execute(
            "SELECT memory_hash FROM memory_versions WHERE seat = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (record["seat"],),
        ).fetchone()
        if latest and record["previous_hash"] != latest["memory_hash"]:
            raise ValueError("previous memory hash does not match the latest version")
        if record["memory_hash"] not in {
            stable_hash(record["memory_text"]),
            content_hash(record["memory_text"]),
        }:
            raise ValueError("memory hash does not match the memory content")
        source_record_ids = record["source_record_ids"]
        if isinstance(source_record_ids, list):
            source_record_ids = json.dumps(source_record_ids, ensure_ascii=False)
        if not json.loads(source_record_ids):
            raise ValueError("a memory version needs a source life record")
        values = {
            **record,
            "id": record.get("id", f"memory-{uuid.uuid4().hex[:12]}"),
            "source_record_ids": source_record_ids,
            "created_at": record.get("created_at", now_iso()),
        }
        connection.execute(
            "INSERT INTO memory_versions(id, seat, memory_text, previous_hash, memory_hash, "
            "mutation_kind, source_record_ids, created_at) VALUES (:id, :seat, :memory_text, "
            ":previous_hash, :memory_hash, :mutation_kind, :source_record_ids, :created_at)",
            values,
        )

    def add_protocol_violation(self, record: dict[str, Any]) -> None:
        values = {
            "id": record.get("id", f"violation-{uuid.uuid4().hex[:12]}"),
            "seat": record["seat"],
            "tick": record["tick"],
            "wake_type": record["wake_type"],
            "reason": record["reason"],
            "memory_hash_before": record.get("memory_hash_before", ""),
            "memory_hash_after": record.get("memory_hash_after", ""),
            "memory_diff": record.get("memory_diff", ""),
            "action": record.get("action", "blocked"),
            "runtime_epoch": record.get("runtime_epoch", "unknown"),
            "created_at": record.get("created_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO protocol_violations(id, seat, tick, wake_type, reason, memory_hash_before, memory_hash_after, memory_diff, action, runtime_epoch, created_at) VALUES (:id, :seat, :tick, :wake_type, :reason, :memory_hash_before, :memory_hash_after, :memory_diff, :action, :runtime_epoch, :created_at)",
                values,
            )

    def protocol_violations(self, seat: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM protocol_violations"
        args: tuple[Any, ...] = ()
        if seat:
            query += " WHERE seat = ?"
            args = (seat,)
        query += " ORDER BY tick, created_at"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, args).fetchall()]

    def append_life_record(self, record: dict[str, Any]) -> None:
        values = {
            "id": record.get("id", f"life-{uuid.uuid4().hex[:12]}"),
            "seat": record["seat"],
            "tick": record["tick"],
            "wake_type": record["wake_type"],
            "observation_ids": json.dumps(record.get("observation_ids", []), ensure_ascii=False),
            "belief_before": json.dumps(record.get("belief_before", {}), ensure_ascii=False, sort_keys=True),
            "belief_after": json.dumps(record.get("belief_after", {}), ensure_ascii=False, sort_keys=True),
            "intentions": json.dumps(record.get("intentions", []), ensure_ascii=False, sort_keys=True),
            "memory_hash_before": record.get("memory_hash_before", ""),
            "memory_hash_after": record.get("memory_hash_after", ""),
            "runtime_epoch": record.get("runtime_epoch", "unknown"),
            "created_at": record.get("created_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO life_records(id, seat, tick, wake_type, observation_ids, belief_before, belief_after, intentions, memory_hash_before, memory_hash_after, runtime_epoch, created_at) VALUES (:id, :seat, :tick, :wake_type, :observation_ids, :belief_before, :belief_after, :intentions, :memory_hash_before, :memory_hash_after, :runtime_epoch, :created_at)",
                values,
            )

    def life_records(self, seat: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM life_records"
        args: tuple[Any, ...] = ()
        if seat:
            query += " WHERE seat = ?"
            args = (seat,)
        query += " ORDER BY tick, created_at"
        with self._connect() as connection:
            rows = connection.execute(query, args).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("observation_ids", "belief_before", "belief_after", "intentions"):
                item[key] = json.loads(item[key])
            records.append(item)
        return records

    def add_wake_session(self, record: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO wake_sessions(id, seat, wake_type, hermes_session_id, source, runtime_epoch, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["id"],
                    record["seat"],
                    record["wake_type"],
                    record.get("hermes_session_id"),
                    record["source"],
                    record["runtime_epoch"],
                    record["status"],
                    record.get("created_at", now_iso()),
                ),
            )

    def wake_sessions(self, seat: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM wake_sessions"
        args: tuple[Any, ...] = ()
        if seat:
            query += " WHERE seat = ?"
            args = (seat,)
        query += " ORDER BY created_at"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, args).fetchall()]

    def create_branch(self, fork_id: str, tick: int, state: dict[str, Any]) -> str:
        branch_id = f"branch-{uuid.uuid4().hex[:12]}"
        stamp = now_iso()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO branches(id, fork_id, status, tick, state_json, boundary_reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (branch_id, fork_id, "active", tick, json.dumps(state, ensure_ascii=False), "", stamp, stamp),
            )
        return branch_id

    def branch_for_fork(self, fork_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM branches WHERE fork_id = ? ORDER BY created_at LIMIT 1", (fork_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["state_json"] = json.loads(item["state_json"])
        return item

    def branch(self, branch_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["state_json"] = json.loads(item["state_json"])
        return item

    def update_branch(self, branch_id: str, *, tick: int, state: dict[str, Any], status: str, boundary_reason: str = "") -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE branches SET tick = ?, state_json = ?, status = ?, boundary_reason = ?, updated_at = ? WHERE id = ?",
                (tick, json.dumps(state, ensure_ascii=False), status, boundary_reason, now_iso(), branch_id),
            )

    def add_branch_record(self, branch_id: str, tick: int, actor_seat: str, action: dict[str, Any], result: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO branch_records(id, branch_id, tick, actor_seat, action_json, result_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"branch-record-{uuid.uuid4().hex[:12]}",
                    branch_id,
                    tick,
                    actor_seat,
                    json.dumps(action, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    now_iso(),
                ),
            )

    def branch_records(self, branch_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM branch_records WHERE branch_id = ? ORDER BY tick, created_at", (branch_id,)
            ).fetchall()
        return [
            {**dict(row), "action_json": json.loads(row["action_json"]), "result_json": json.loads(row["result_json"])}
            for row in rows
        ]

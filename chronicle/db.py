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

CREATE TABLE IF NOT EXISTS worldlines (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    volume_id TEXT NOT NULL DEFAULT '',
    current_tick INTEGER NOT NULL,
    runtime_epoch TEXT NOT NULL DEFAULT '',
    runtime_mode TEXT NOT NULL DEFAULT 'fixture',
    runtime_phase TEXT NOT NULL DEFAULT 'READY',
    runtime_error_code TEXT NOT NULL DEFAULT '',
    volume_content_version INTEGER NOT NULL DEFAULT 0,
    volume_content_hash TEXT NOT NULL DEFAULT '',
    worldline_phase TEXT NOT NULL DEFAULT 'READY',
    boundary_policy_id TEXT NOT NULL DEFAULT '',
    safety_horizon_tick INTEGER,
    human_lifetime_id TEXT NOT NULL DEFAULT '',
    seal_reason TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    pending_confirmation_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS worldlines_status_idx ON worldlines(status, kind, updated_at);

CREATE UNIQUE INDEX IF NOT EXISTS active_volume_worldline_singleton_idx
ON worldlines((1))
WHERE kind = 'VOLUME' AND status = 'ACTIVE';

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

CREATE TABLE IF NOT EXISTS worldline_lifetimes (
    id TEXT PRIMARY KEY,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    seat TEXT NOT NULL,
    controller TEXT NOT NULL,
    status TEXT NOT NULL,
    genesis_parent_id TEXT NOT NULL DEFAULT '',
    profile_name TEXT NOT NULL DEFAULT '',
    profile_metadata_json TEXT NOT NULL DEFAULT '{}',
    genesis_hash TEXT NOT NULL DEFAULT '',
    memory_text TEXT NOT NULL DEFAULT '',
    memory_hash TEXT NOT NULL DEFAULT '',
    experiences_json TEXT NOT NULL DEFAULT '[]',
    knowledge_json TEXT NOT NULL DEFAULT '[]',
    belief_json TEXT NOT NULL DEFAULT '{}',
    authority_json TEXT NOT NULL DEFAULT '[]',
    role_charter_json TEXT NOT NULL DEFAULT '{}',
    plan_json TEXT NOT NULL DEFAULT '[]',
    commitments_json TEXT NOT NULL DEFAULT '[]',
    resources_json TEXT NOT NULL DEFAULT '{}',
    last_perspective_json TEXT NOT NULL DEFAULT '{}',
    revisits_json TEXT NOT NULL DEFAULT '[]',
    wake_count INTEGER NOT NULL DEFAULT 0,
    lifetime_kind TEXT NOT NULL DEFAULT 'ACTOR',
    genesis_context_json TEXT NOT NULL DEFAULT '{}',
    profile_state TEXT NOT NULL DEFAULT 'UNBOUND',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, seat)
);

CREATE TABLE IF NOT EXISTS worldline_agent_bindings (
    id TEXT PRIMARY KEY,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    role TEXT NOT NULL,
    profile_identity TEXT NOT NULL,
    distribution_version TEXT NOT NULL,
    ownership_marker TEXT NOT NULL,
    status TEXT NOT NULL,
    token_hash TEXT NOT NULL DEFAULT '',
    revoked_at TEXT NOT NULL DEFAULT '',
    lifetime_id TEXT NOT NULL DEFAULT '',
    binding_scope TEXT NOT NULL DEFAULT 'VOLUME',
    volume_id TEXT NOT NULL DEFAULT '',
    content_version INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    genesis_hash TEXT NOT NULL DEFAULT '',
    runtime_epoch TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, role)
);

CREATE UNIQUE INDEX IF NOT EXISTS worldline_agent_bindings_token_idx
ON worldline_agent_bindings(token_hash)
WHERE token_hash <> '';

CREATE UNIQUE INDEX IF NOT EXISTS worldline_agent_bindings_lifetime_idx
ON worldline_agent_bindings(worldline_id, lifetime_id)
WHERE lifetime_id <> '';

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

CREATE TABLE IF NOT EXISTS worldline_crisis_instances (
    id TEXT PRIMARY KEY,
    worldline_id TEXT NOT NULL REFERENCES worldlines(id),
    crisis_id TEXT NOT NULL,
    content_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    activation_tick INTEGER NOT NULL,
    local_origin_tick INTEGER NOT NULL,
    resolution_contract_id TEXT NOT NULL DEFAULT '',
    resolution_contract_version INTEGER NOT NULL DEFAULT 0,
    resolution_seed TEXT NOT NULL DEFAULT '',
    settled_tick INTEGER,
    outcome_json TEXT NOT NULL DEFAULT '{}',
    suppression_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(worldline_id, crisis_id)
);

CREATE INDEX IF NOT EXISTS worldline_crisis_instances_lookup_idx
ON worldline_crisis_instances(worldline_id, status, activation_tick, crisis_id);

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
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ChronicleDB:
    """Persistence for the current V6 Volume runtime."""

    CURRENT_SCHEMA_VERSION = "10"

    def __init__(self, path: Path):
        self.path = path
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
            has_meta_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_meta'"
            ).fetchone()
            row = (
                connection.execute(
                    "SELECT value FROM app_meta WHERE key = 'schema_version'"
                ).fetchone()
                if has_meta_table
                else None
            )
        if existing_before and row is None:
            raise RuntimeError(
                "unsupported Chronicle database without a V6 schema marker; "
                "recreate the database for V6"
            )
        if row is not None and str(row["value"]) != self.CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                "unsupported Chronicle database schema "
                f"{row['value']}; recreate the database for V6"
            )

        with self._connect() as connection:
            connection.executescript(SCHEMA)
            if row is not None:
                self._repair_current_v6_shape(connection)

        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO app_meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (self.CURRENT_SCHEMA_VERSION,),
            )

    @staticmethod
    def _repair_current_v6_shape(connection: sqlite3.Connection) -> None:
        """Complete the physical shape of an existing V6 schema-10 database."""

        lifetime_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(worldline_lifetimes)")
        }
        if "genesis_parent_id" not in lifetime_columns:
            connection.execute(
                "ALTER TABLE worldline_lifetimes "
                "ADD COLUMN genesis_parent_id TEXT NOT NULL DEFAULT ''"
            )
            if "parent_canon_lifetime" in lifetime_columns:
                connection.execute(
                    "UPDATE worldline_lifetimes SET genesis_parent_id = parent_canon_lifetime "
                    "WHERE genesis_parent_id = ''"
                )
        if "experiences_json" not in lifetime_columns:
            connection.execute(
                "ALTER TABLE worldline_lifetimes "
                "ADD COLUMN experiences_json TEXT NOT NULL DEFAULT '[]'"
            )

        binding_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worldline_agent_bindings)")
        }
        if "binding_scope" in binding_columns:
            connection.execute(
                "UPDATE worldline_agent_bindings SET binding_scope = 'VOLUME' "
                "WHERE worldline_id IN (SELECT id FROM worldlines WHERE kind = 'VOLUME')"
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

    def active_volume_worldline(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldlines WHERE kind = 'VOLUME' AND status = 'ACTIVE' "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def create_worldline_bundle(
        self,
        values: dict[str, Any],
        events: list[dict[str, Any]],
        lifetimes: list[dict[str, Any]],
        projection: dict[str, Any],
        instance_creates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create the initial Worldline, lifetimes, envelopes, ledger, and snapshot atomically."""

        worldline = {
            "id": values["id"],
            "scenario_id": values.get("scenario_id", "jiashen"),
            "kind": values.get("kind", "VOLUME"),
            "status": values.get("status", "ACTIVE"),
            "current_tick": values["current_tick"],
            "runtime_epoch": values.get("runtime_epoch", ""),
            "runtime_mode": values.get("runtime_mode", "fixture"),
            "runtime_phase": values.get("runtime_phase", "READY"),
            "runtime_error_code": values.get("runtime_error_code", ""),
            "volume_id": values.get("volume_id", ""),
            "volume_content_version": int(values.get("volume_content_version", 0)),
            "volume_content_hash": values.get("volume_content_hash", ""),
            "worldline_phase": values.get("worldline_phase", "READY"),
            "boundary_policy_id": values.get("boundary_policy_id", ""),
            "safety_horizon_tick": values.get("safety_horizon_tick"),
            "human_lifetime_id": values.get("human_lifetime_id", ""),
            "seal_reason": values.get("seal_reason", ""),
            "outcome": values.get("outcome", ""),
            "pending_confirmation_json": values.get("pending_confirmation_json", ""),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldlines(id, scenario_id, kind, status, current_tick, "
                "runtime_epoch, runtime_mode, runtime_phase, runtime_error_code, volume_id, volume_content_version, volume_content_hash, "
                "worldline_phase, boundary_policy_id, safety_horizon_tick, human_lifetime_id, "
                "seal_reason, outcome, pending_confirmation_json, created_at, updated_at) "
                "VALUES (:id, :scenario_id, :kind, :status, :current_tick, "
                ":runtime_epoch, :runtime_mode, :runtime_phase, :runtime_error_code, :volume_id, :volume_content_version, :volume_content_hash, "
                ":worldline_phase, :boundary_policy_id, :safety_horizon_tick, :human_lifetime_id, "
                ":seal_reason, :outcome, :pending_confirmation_json, :created_at, :updated_at)",
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
                    "provenance": event.get("provenance", "volume_derived"),
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
                    "genesis_parent_id, profile_name, profile_metadata_json, genesis_hash, memory_text, memory_hash, "
                    "experiences_json, knowledge_json, belief_json, authority_json, role_charter_json, plan_json, commitments_json, "
                    "resources_json, last_perspective_json, revisits_json, wake_count, lifetime_kind, "
                    "genesis_context_json, profile_state, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :seat, :controller, :status, :genesis_parent_id, :profile_name, "
                    ":profile_metadata_json, :genesis_hash, :memory_text, :memory_hash, :experiences_json, :knowledge_json, :belief_json, "
                    ":authority_json, :role_charter_json, :plan_json, :commitments_json, :resources_json, "
                    ":last_perspective_json, :revisits_json, :wake_count, :lifetime_kind, :genesis_context_json, "
                    ":profile_state, :created_at, :updated_at)",
                    {
                        "id": values_for_lifetime["id"],
                        "worldline_id": values["id"],
                        "seat": values_for_lifetime["seat"],
                        "controller": values_for_lifetime["controller"],
                        "status": values_for_lifetime.get("status", "ACTIVE"),
                        "genesis_parent_id": values_for_lifetime.get("genesis_parent_id", ""),
                        "profile_name": values_for_lifetime.get("profile_name", ""),
                        "profile_metadata_json": json.dumps(
                            values_for_lifetime.get("profile_metadata", {}), ensure_ascii=False
                        ),
                        "genesis_hash": values_for_lifetime.get("genesis_hash", ""),
                        "memory_text": values_for_lifetime.get("memory_text", ""),
                        "memory_hash": values_for_lifetime.get("memory_hash", ""),
                        "experiences_json": json.dumps(
                            values_for_lifetime.get("experiences", []),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "knowledge_json": json.dumps(
                            values_for_lifetime.get("knowledge", []), ensure_ascii=False, sort_keys=True
                        ),
                        "belief_json": json.dumps(
                            values_for_lifetime.get("beliefs", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "authority_json": json.dumps(
                            values_for_lifetime.get("authority", []), ensure_ascii=False, sort_keys=True
                        ),
                        "role_charter_json": json.dumps(
                            values_for_lifetime.get("role_charter", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "plan_json": json.dumps(
                            values_for_lifetime.get("plan", []), ensure_ascii=False, sort_keys=True
                        ),
                        "commitments_json": json.dumps(
                            values_for_lifetime.get("commitments", []), ensure_ascii=False, sort_keys=True
                        ),
                        "resources_json": json.dumps(
                            values_for_lifetime.get("resources", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "last_perspective_json": json.dumps(
                            values_for_lifetime.get("last_perspective", {}), ensure_ascii=False, sort_keys=True
                        ),
                        "revisits_json": json.dumps(
                            values_for_lifetime.get("revisits", []), ensure_ascii=False, sort_keys=True
                        ),
                        "wake_count": int(values_for_lifetime.get("wake_count", 0)),
                        "lifetime_kind": values_for_lifetime.get("lifetime_kind", "ACTOR"),
                        "genesis_context_json": json.dumps(
                            values_for_lifetime.get("genesis_context", {}),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "profile_state": values_for_lifetime.get("profile_state", "UNBOUND"),
                        "created_at": values_for_lifetime.get("created_at", now_iso()),
                        "updated_at": values_for_lifetime.get("updated_at", now_iso()),
                    },
                )
            for values_for_instance in instance_creates or []:
                outcome = values_for_instance.get(
                    "outcome", values_for_instance.get("outcome_json", {})
                )
                instance = {
                    "id": values_for_instance["id"],
                    "worldline_id": values["id"],
                    "crisis_id": values_for_instance["crisis_id"],
                    "content_version": int(values_for_instance.get("content_version", 0)),
                    "content_hash": values_for_instance.get("content_hash", ""),
                    "status": values_for_instance.get("status", "DORMANT"),
                    "phase": values_for_instance.get("phase", "DORMANT"),
                    "activation_tick": int(values_for_instance.get("activation_tick", 0)),
                    "local_origin_tick": int(values_for_instance.get("local_origin_tick", 0)),
                    "resolution_contract_id": values_for_instance.get(
                        "resolution_contract_id", ""
                    ),
                    "resolution_contract_version": int(
                        values_for_instance.get("resolution_contract_version", 0)
                    ),
                    "resolution_seed": values_for_instance.get("resolution_seed", ""),
                    "settled_tick": values_for_instance.get("settled_tick"),
                    "outcome_json": outcome
                    if isinstance(outcome, str)
                    else json.dumps(outcome, ensure_ascii=False, sort_keys=True),
                    "suppression_reason": values_for_instance.get("suppression_reason", ""),
                    "created_at": values_for_instance.get("created_at", now_iso()),
                    "updated_at": values_for_instance.get("updated_at", now_iso()),
                }
                connection.execute(
                    "INSERT INTO worldline_crisis_instances("
                    "id, worldline_id, crisis_id, content_version, content_hash, status, phase, "
                    "activation_tick, local_origin_tick, resolution_contract_id, resolution_contract_version, "
                    "resolution_seed, settled_tick, outcome_json, suppression_reason, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :crisis_id, :content_version, :content_hash, :status, :phase, "
                    ":activation_tick, :local_origin_tick, :resolution_contract_id, :resolution_contract_version, "
                    ":resolution_seed, :settled_tick, :outcome_json, :suppression_reason, :created_at, :updated_at)",
                    instance,
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

    def set_volume_runtime_state(
        self,
        worldline_id: str,
        phase: str,
        *,
        error_code: str = "",
    ) -> dict[str, Any]:
        """Update the live-runtime state of a V6 Volume Worldline."""

        valid = {"BOOTSTRAPPING", "READY", "RECONCILING", "FAILED", "CLEANUP_PENDING"}
        if phase not in valid:
            raise ValueError(f"unknown volume runtime phase: {phase}")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT kind, status FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if row is None or row["kind"] != "VOLUME":
                raise sqlite3.IntegrityError("VOLUME Worldline does not exist")
            if row["status"] == "ACTIVE" and phase == "CLEANUP_PENDING":
                raise sqlite3.IntegrityError("active Volume cannot enter cleanup")
            if row["status"] != "SEALED" and phase == "CLEANUP_PENDING":
                raise sqlite3.IntegrityError("only a sealed Volume can enter cleanup")
            connection.execute(
                "UPDATE worldlines SET runtime_phase = ?, runtime_error_code = ?, updated_at = ? "
                "WHERE id = ?",
                (phase, error_code, now_iso(), worldline_id),
            )
        return self.worldline(worldline_id) or {}

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
            "provenance": event.get("provenance", "volume_derived"),
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

    def commit_volume_moment(
        self,
        worldline_id: str,
        events: list[dict[str, Any]],
        *,
        current_tick: int,
        lifetime_updates: list[dict[str, Any]] | None = None,
        instance_creates: list[dict[str, Any]] | None = None,
        instance_updates: list[dict[str, Any]] | None = None,
        wake_updates: list[dict[str, Any]] | None = None,
        wake_creates: list[dict[str, Any]] | None = None,
        operation_updates: list[dict[str, Any]] | None = None,
        snapshot: dict[str, Any] | None = None,
        expected_current_tick: int | None = None,
    ) -> list[dict[str, Any]]:
        """Commit one V6 Volume moment without changing Worldline lifecycle state."""

        committed: list[dict[str, Any]] = []
        with self.transaction() as connection:
            worldline = connection.execute(
                "SELECT kind, status, current_tick, runtime_epoch FROM worldlines WHERE id = ?",
                (worldline_id,),
            ).fetchone()
            if worldline is None or worldline["kind"] != "VOLUME":
                raise sqlite3.IntegrityError("Volume moment requires a VOLUME Worldline")
            if worldline["status"] != "ACTIVE":
                raise sqlite3.IntegrityError("Volume Worldline is sealed")
            if expected_current_tick is not None and int(worldline["current_tick"]) != int(
                expected_current_tick
            ):
                raise sqlite3.IntegrityError("Volume clock changed before the moment was committed")

            for event in events:
                sequence = self._insert_worldline_event(connection, worldline_id, event)
                committed_record = dict(event)
                committed_record["sequence"] = sequence
                committed_record["worldline_id"] = worldline_id
                committed_record.setdefault("created_at", now_iso())
                committed.append(committed_record)

            update_sql = (
                "UPDATE worldlines SET current_tick = ?, updated_at = ? "
                "WHERE id = ? AND kind = 'VOLUME' AND status = 'ACTIVE'"
            )
            update_args: list[Any] = [int(current_tick), now_iso(), worldline_id]
            if expected_current_tick is not None:
                update_sql += " AND current_tick = ?"
                update_args.append(int(expected_current_tick))
            updated = connection.execute(update_sql, update_args)
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("Volume clock changed before the moment was committed")

            for values in instance_creates or []:
                outcome = values.get("outcome", values.get("outcome_json", {}))
                record = {
                    "id": values["id"],
                    "worldline_id": worldline_id,
                    "crisis_id": values["crisis_id"],
                    "content_version": int(values.get("content_version", 0)),
                    "content_hash": values.get("content_hash", ""),
                    "status": values.get("status", "DORMANT"),
                    "phase": values.get("phase", "DORMANT"),
                    "activation_tick": int(values.get("activation_tick", current_tick)),
                    "local_origin_tick": int(values.get("local_origin_tick", 0)),
                    "resolution_contract_id": values.get("resolution_contract_id", ""),
                    "resolution_contract_version": int(
                        values.get("resolution_contract_version", 0)
                    ),
                    "resolution_seed": values.get("resolution_seed", ""),
                    "settled_tick": values.get("settled_tick"),
                    "outcome_json": outcome
                    if isinstance(outcome, str)
                    else json.dumps(outcome, ensure_ascii=False, sort_keys=True),
                    "suppression_reason": values.get("suppression_reason", ""),
                    "created_at": values.get("created_at", now_iso()),
                    "updated_at": values.get("updated_at", now_iso()),
                }
                connection.execute(
                    "INSERT INTO worldline_crisis_instances("
                    "id, worldline_id, crisis_id, content_version, content_hash, status, phase, "
                    "activation_tick, local_origin_tick, resolution_contract_id, resolution_contract_version, "
                    "resolution_seed, settled_tick, outcome_json, suppression_reason, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :crisis_id, :content_version, :content_hash, :status, :phase, "
                    ":activation_tick, :local_origin_tick, :resolution_contract_id, :resolution_contract_version, "
                    ":resolution_seed, :settled_tick, :outcome_json, :suppression_reason, :created_at, :updated_at)",
                    record,
                )

            for values in instance_updates or []:
                update_values = dict(values)
                if "outcome" in update_values and "outcome_json" not in update_values:
                    outcome = update_values.pop("outcome")
                    update_values["outcome_json"] = (
                        outcome
                        if isinstance(outcome, str)
                        else json.dumps(outcome, ensure_ascii=False, sort_keys=True)
                    )
                allowed = {
                    "status",
                    "phase",
                    "activation_tick",
                    "local_origin_tick",
                    "resolution_contract_id",
                    "resolution_contract_version",
                    "resolution_seed",
                    "settled_tick",
                    "outcome_json",
                    "suppression_reason",
                }
                fields = {key: value for key, value in update_values.items() if key in allowed}
                if not fields:
                    continue
                assignments = ", ".join(f"{key} = :{key}" for key in fields)
                fields.update({"id": values["id"], "worldline_id": worldline_id, "updated_at": now_iso()})
                changed = connection.execute(
                    f"UPDATE worldline_crisis_instances SET {assignments}, updated_at = :updated_at "
                    "WHERE id = :id AND worldline_id = :worldline_id",
                    fields,
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        f"Crisis Instance is missing from Volume Worldline: {values['id']}"
                    )

            for values in lifetime_updates or []:
                update_values = dict(values)
                json_keys = {
                    "knowledge": "knowledge_json",
                    "beliefs": "belief_json",
                    "authority": "authority_json",
                    "experiences": "experiences_json",
                }
                for key, json_key in json_keys.items():
                    if key in update_values and json_key not in update_values:
                        update_values[json_key] = json.dumps(
                            update_values.pop(key), ensure_ascii=False, sort_keys=True
                        )
                allowed = {
                    "status",
                    "controller",
                    "profile_state",
                    "profile_name",
                    "profile_metadata_json",
                    "memory_text",
                    "memory_hash",
                    "experiences_json",
                    "knowledge_json",
                    "belief_json",
                    "authority_json",
                    "last_perspective_json",
                    "plan_json",
                    "commitments_json",
                    "revisits_json",
                    "resources_json",
                    "wake_count",
                }
                fields = {key: value for key, value in update_values.items() if key in allowed}
                if not fields:
                    continue
                assignments = ", ".join(f"{key} = :{key}" for key in fields)
                fields.update({"worldline_id": worldline_id, "updated_at": now_iso()})
                if values.get("id"):
                    where = "worldline_id = :worldline_id AND id = :id"
                    fields["id"] = values["id"]
                else:
                    where = "worldline_id = :worldline_id AND seat = :seat"
                    fields["seat"] = values["seat"]
                changed = connection.execute(
                    f"UPDATE worldline_lifetimes SET {assignments}, updated_at = :updated_at "
                    f"WHERE {where}",
                    fields,
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        f"Lifetime is missing from Volume Worldline: {values.get('id', values.get('seat', ''))}"
                    )

            for values in wake_updates or []:
                update_values = dict(values)
                for key in ("frozen_perspective", "result", "error"):
                    if key in update_values:
                        update_values[f"{key}_json"] = json.dumps(
                            update_values.pop(key), ensure_ascii=False, sort_keys=True
                        )
                allowed = {
                    "status",
                    "hermes_session_id",
                    "frozen_perspective_json",
                    "result_json",
                    "error_json",
                }
                fields = {key: value for key, value in update_values.items() if key in allowed}
                if not fields:
                    continue
                assignments = ", ".join(f"{key} = :{key}" for key in fields)
                fields.update(
                    {
                        "id": values["id"],
                        "worldline_id": worldline_id,
                        "updated_at": now_iso(),
                    }
                )
                changed = connection.execute(
                    f"UPDATE crisis_wakes SET {assignments}, updated_at = :updated_at "
                    "WHERE id = :id AND worldline_id = :worldline_id",
                    fields,
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        f"Wake is missing from Volume Worldline: {values['id']}"
                    )

            for values in wake_creates or []:
                record = {
                    "id": values.get("id", f"wake-{uuid.uuid4().hex[:16]}"),
                    "worldline_id": worldline_id,
                    "actor_id": values.get("actor_id", values.get("lifetime_id", "")),
                    "wake_type": values["wake_type"],
                    "tick": int(values["tick"]),
                    "status": values.get("status", "QUEUED"),
                    "source": values.get("source", "volume"),
                    "trigger_event_id": values.get("trigger_event_id", ""),
                    "hermes_session_id": values.get("hermes_session_id", ""),
                    "frozen_perspective_json": json.dumps(
                        values.get("frozen_perspective", {}), ensure_ascii=False, sort_keys=True
                    ),
                    "result_json": json.dumps(
                        values.get("result", {}), ensure_ascii=False, sort_keys=True
                    ),
                    "error_json": json.dumps(
                        values.get("error", {}), ensure_ascii=False, sort_keys=True
                    ),
                    "created_at": values.get("created_at", now_iso()),
                    "updated_at": values.get("updated_at", now_iso()),
                }
                connection.execute(
                    "INSERT OR IGNORE INTO crisis_wakes("
                    "id, worldline_id, actor_id, wake_type, tick, status, source, trigger_event_id, "
                    "hermes_session_id, frozen_perspective_json, result_json, error_json, created_at, updated_at) "
                    "VALUES (:id, :worldline_id, :actor_id, :wake_type, :tick, :status, :source, :trigger_event_id, "
                    ":hermes_session_id, :frozen_perspective_json, :result_json, :error_json, :created_at, :updated_at)",
                    record,
                )

            for values in operation_updates or []:
                fields = {key: value for key, value in values.items() if key in {"status"}}
                if "result" in values:
                    fields["result_json"] = json.dumps(
                        values["result"], ensure_ascii=False, sort_keys=True
                    )
                if not fields:
                    continue
                assignments = ", ".join(f"{key} = :{key}" for key in fields)
                fields.update({"id": values["id"], "worldline_id": worldline_id})
                changed = connection.execute(
                    f"UPDATE crisis_wake_operations SET {assignments} "
                    "WHERE id = :id AND wake_id IN "
                    "(SELECT id FROM crisis_wakes WHERE worldline_id = :worldline_id)",
                    fields,
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError(
                        f"Wake operation is missing from Volume moment: {values['id']}"
                    )

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
                        "tick": int(current_tick),
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
        worldline_phase: str | None = None,
    ) -> dict[str, Any]:
        """Seal a Volume Worldline, its event ledger, and all Lifetime rows atomically."""

        record = {
            "id": event["id"],
            "worldline_id": worldline_id,
            "tick": int(event["tick"]),
            "event_type": event["event_type"],
            "seat_id": event.get("seat_id"),
            "payload_json": json.dumps(event.get("payload", {}), ensure_ascii=False, sort_keys=True),
            "provenance": event.get("provenance", "volume_derived"),
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
            worldline_phase_sql = ", worldline_phase = ?" if worldline_phase is not None else ""
            worldline_phase_args: tuple[Any, ...] = (
                (worldline_phase,) if worldline_phase is not None else ()
            )
            updated = connection.execute(
                "UPDATE worldlines SET status = 'SEALED', seal_reason = ?, outcome = ?, "
                "pending_confirmation_json = ''"
                + worldline_phase_sql
                + runtime_sql
                + crisis_sql
                + ", updated_at = ? WHERE id = ? AND status = 'ACTIVE'",
                (
                    reason,
                    outcome,
                    *worldline_phase_args,
                    *runtime_args,
                    *crisis_args,
                    now_iso(),
                    worldline_id,
                ),
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
            return None
        item = dict(row)
        item["projection"] = json.loads(item.pop("projection_json"))
        return item

    def crisis_instance(self, instance_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldline_crisis_instances WHERE id = ?", (instance_id,)
            ).fetchone()
        return self._decode_crisis_instance(row) if row else None

    def crisis_instances(
        self, worldline_id: str, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM worldline_crisis_instances WHERE worldline_id = ?"
        args: list[Any] = [worldline_id]
        if status is not None:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY activation_tick, crisis_id"
        with self._connect() as connection:
            rows = connection.execute(query, args).fetchall()
        return [self._decode_crisis_instance(row) for row in rows]

    @staticmethod
    def _decode_crisis_instance(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        if "outcome_json" in item:
            item["outcome"] = json.loads(item["outcome_json"])
        return item

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
            "experiences_json",
            "genesis_context_json",
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
            "experiences_json",
            "knowledge_json",
            "belief_json",
            "authority_json",
            "controller",
            "lifetime_kind",
            "genesis_context_json",
            "profile_state",
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

    def worldline_lifetime_by_id(
        self, worldline_id: str, lifetime_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worldline_lifetimes WHERE worldline_id = ? AND id = ?",
                (worldline_id, lifetime_id),
            ).fetchone()
        return self._decode_worldline_lifetime(row) if row else None

    def transition_volume_controller(
        self,
        worldline_id: str,
        lifetime_id: str,
        controller: str,
        *,
        event_type: str,
        reason: str,
    ) -> dict[str, Any]:
        """Atomically hand one VOLUME Lifetime between HUMAN and AGENT control."""

        if controller not in {"HUMAN", "AGENT"}:
            raise ValueError(f"unknown controller: {controller}")
        handoff_wake_ids: list[str] = []
        event: dict[str, Any] | None = None
        idempotent = False
        with self.transaction() as connection:
            worldline = connection.execute(
                "SELECT * FROM worldlines WHERE id = ?", (worldline_id,)
            ).fetchone()
            if worldline is None:
                raise KeyError(f"worldline not found: {worldline_id}")
            if worldline["kind"] != "VOLUME":
                raise sqlite3.IntegrityError("Inhabitation requires a VOLUME Worldline")
            if worldline["status"] != "ACTIVE":
                raise sqlite3.IntegrityError("Worldline is sealed")
            lifetime = connection.execute(
                "SELECT * FROM worldline_lifetimes WHERE worldline_id = ? AND id = ?",
                (worldline_id, lifetime_id),
            ).fetchone()
            if lifetime is None:
                raise KeyError(f"Lifetime not found: {lifetime_id}")
            if lifetime["status"] != "ACTIVE":
                raise sqlite3.IntegrityError("Lifetime is not active")

            current_id = str(worldline["human_lifetime_id"] or "")
            current_controller = str(lifetime["controller"])
            if controller == "HUMAN":
                if current_id == lifetime_id and current_controller == "HUMAN":
                    idempotent = True
                elif current_id:
                    raise sqlite3.IntegrityError(
                        "another Lifetime is already inhabited; leave it first"
                    )
                elif current_controller != "AGENT":
                    raise sqlite3.IntegrityError("Lifetime controller state is inconsistent")
            elif not current_id:
                if current_controller == "AGENT":
                    idempotent = True
                else:
                    raise sqlite3.IntegrityError("Lifetime controller state is inconsistent")
            elif current_id != lifetime_id or current_controller != "HUMAN":
                raise sqlite3.IntegrityError("the requested Lifetime is not inhabited")

            if not idempotent:
                wake_rows = connection.execute(
                    "SELECT id, status FROM crisis_wakes "
                    "WHERE worldline_id = ? AND actor_id IN (?, ?) "
                    "AND status IN ('QUEUED', 'WAITING_HUMAN', 'RUNNING', 'STAGED') "
                    "ORDER BY tick, id",
                    (worldline_id, lifetime_id, lifetime["seat"]),
                ).fetchall()
                if any(row["status"] in {"RUNNING", "STAGED"} for row in wake_rows):
                    raise sqlite3.IntegrityError(
                        "cannot change controller while a Lifetime wake is running"
                    )
                desired_wake_status = "WAITING_HUMAN" if controller == "HUMAN" else "QUEUED"
                for wake in wake_rows:
                    if wake["status"] != desired_wake_status:
                        connection.execute(
                            "UPDATE crisis_wakes SET status = ?, updated_at = ? WHERE id = ?",
                            (desired_wake_status, now_iso(), wake["id"]),
                        )
                    handoff_wake_ids.append(str(wake["id"]))
                connection.execute(
                    "UPDATE worldline_lifetimes SET controller = ?, profile_state = ?, updated_at = ? "
                    "WHERE worldline_id = ? AND id = ?",
                    (
                        controller,
                        "DORMANT" if controller == "HUMAN" else "ACTIVE",
                        now_iso(),
                        worldline_id,
                        lifetime_id,
                    ),
                )
                new_human_lifetime_id = lifetime_id if controller == "HUMAN" else ""
                connection.execute(
                    "UPDATE worldlines SET human_lifetime_id = ?, updated_at = ? WHERE id = ?",
                    (new_human_lifetime_id, now_iso(), worldline_id),
                )
                event = {
                    "id": f"presence-{uuid.uuid4().hex[:16]}",
                    "worldline_id": worldline_id,
                    "tick": int(worldline["current_tick"]),
                    "event_type": event_type,
                    "seat_id": lifetime["seat"],
                    "payload": {
                        "lifetime_id": lifetime_id,
                        "seat": lifetime["seat"],
                        "controller_from": current_controller,
                        "controller_to": controller,
                        "human_lifetime_id": new_human_lifetime_id,
                        "reason": reason,
                        "handoff_wake_ids": handoff_wake_ids,
                    },
                    "provenance": "volume_derived",
                    "causal_parent_ids": [],
                    "runtime_epoch": worldline["runtime_epoch"],
                    "created_at": now_iso(),
                }
                event["sequence"] = self._insert_worldline_event(
                    connection, worldline_id, event
                )

        updated_worldline = self.worldline(worldline_id) or {}
        updated_lifetime = self.worldline_lifetime_by_id(worldline_id, lifetime_id) or {}
        return {
            "worldline": updated_worldline,
            "lifetime": updated_lifetime,
            "event": event,
            "handoff_wake_ids": handoff_wake_ids,
            "idempotent": idempotent,
        }

    def create_agent_binding(self, values: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": values.get("id", f"binding-{uuid.uuid4().hex[:16]}"),
            "worldline_id": values["worldline_id"],
            "role": values["actor_id"],
            "profile_identity": values["profile_name"],
            "distribution_version": values.get("distribution_version", "chronicle-actor-v6"),
            "ownership_marker": values["ownership_marker"],
            "status": values.get("status", "ACTIVE"),
            "token_hash": values["token_hash"],
            "revoked_at": "",
            "lifetime_id": values.get("lifetime_id", ""),
            "binding_scope": values.get("binding_scope", "VOLUME"),
            "volume_id": values.get("volume_id", ""),
            "content_version": int(values.get("content_version", 0)),
            "content_hash": values.get("content_hash", ""),
            "genesis_hash": values.get("genesis_hash", ""),
            "runtime_epoch": values.get("runtime_epoch", ""),
            "created_at": values.get("created_at", now_iso()),
            "updated_at": values.get("updated_at", now_iso()),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO worldline_agent_bindings(id, worldline_id, role, profile_identity, "
                "distribution_version, ownership_marker, status, token_hash, revoked_at, "
                "lifetime_id, binding_scope, volume_id, content_version, content_hash, genesis_hash, runtime_epoch, "
                "created_at, updated_at) VALUES (:id, :worldline_id, :role, :profile_identity, "
                ":distribution_version, :ownership_marker, :status, :token_hash, :revoked_at, "
                ":lifetime_id, :binding_scope, :volume_id, :content_version, :content_hash, :genesis_hash, "
                ":runtime_epoch, :created_at, :updated_at)",
                record,
            )
        return record

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

    def create_subject_wake(self, values: dict[str, Any]) -> dict[str, Any]:
        record = dict(values)
        if "actor_id" not in record and "lifetime_id" in record:
            record["actor_id"] = record["lifetime_id"]
        record.update(
            {
                "id": record.get("id", f"wake-{uuid.uuid4().hex[:16]}"),
                "status": record.get("status", "QUEUED"),
                "source": record.get("source", "volume"),
                "trigger_event_id": record.get("trigger_event_id", ""),
                "hermes_session_id": record.get("hermes_session_id", ""),
                "frozen_perspective_json": json.dumps(
                    record.get("frozen_perspective", {}), ensure_ascii=False, sort_keys=True
                ),
                "result_json": json.dumps(
                    record.get("result", {}), ensure_ascii=False, sort_keys=True
                ),
                "error_json": json.dumps(
                    record.get("error", {}), ensure_ascii=False, sort_keys=True
                ),
                "created_at": record.get("created_at", now_iso()),
                "updated_at": record.get("updated_at", now_iso()),
            }
        )
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
        return self.crisis_wake(str(record["id"])) or {}

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

    def subject_wakes(
        self,
        worldline_id: str,
        *,
        status: str | None = None,
        tick: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.crisis_wakes(worldline_id, status=status, tick=tick)

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

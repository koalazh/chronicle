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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

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
        if mutation_kind != "reflection":
            raise ValueError("Memory can only be mutated by a reflection")
        versions = self.memory_versions(seat)
        if versions and previous_hash != versions[-1]["memory_hash"]:
            raise ValueError("previous memory hash does not match the latest version")
        memory_hash = memory_hash or stable_hash(memory_text)
        if memory_hash not in {stable_hash(memory_text), content_hash(memory_text)}:
            raise ValueError("memory hash does not match the memory content")
        if not source_record_ids:
            raise ValueError("a memory version needs a source life record")
        record = {
            "id": f"memory-{uuid.uuid4().hex[:12]}",
            "seat": seat,
            "memory_text": memory_text,
            "previous_hash": previous_hash,
            "memory_hash": memory_hash,
            "mutation_kind": mutation_kind,
            "source_record_ids": json.dumps(source_record_ids, ensure_ascii=False),
            "created_at": now_iso(),
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO memory_versions(id, seat, memory_text, previous_hash, memory_hash, mutation_kind, source_record_ids, created_at) VALUES (:id, :seat, :memory_text, :previous_hash, :memory_hash, :mutation_kind, :source_record_ids, :created_at)",
                record,
            )
        return record

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

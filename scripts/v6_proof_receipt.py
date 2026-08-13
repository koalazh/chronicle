#!/usr/bin/env python3
"""Emit a secret-free V6 proof receipt from one Volume SQLite ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_COGNITION_EVENTS = frozenset(
    {
        "ATTENTION_EVALUATED",
        "BELIEF_UPDATED",
        "DECISION_HORIZON_ESTABLISHED",
        "DECISION_HORIZON_HELD",
        "DECISION_HORIZON_REVISED",
        "DELIBERATION_COMMITTED",
        "INTENT_COMMITTED",
        "INTENT_REJECTED",
        "LIFETIME_INHABITED",
        "LIFETIME_LEFT",
        "MOMENT_COMMITTED",
        "MOMENT_FROZEN",
        "PLAN_UPDATED",
    }
)


def _digest(values: list[str]) -> list[str]:
    return [hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] for value in values]


def _load_json(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def audit(database: Path, worldline_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        events = connection.execute(
            """
            SELECT id, tick, event_type, seat_id, payload_json, causal_parent_ids
            FROM worldline_events
            WHERE worldline_id = ?
            ORDER BY sequence
            """,
            (worldline_id,),
        ).fetchall()
        lifetimes = connection.execute(
            """
            SELECT seat, knowledge_json
            FROM worldline_lifetimes
            WHERE worldline_id = ?
            ORDER BY seat
            """,
            (worldline_id,),
        ).fetchall()
    finally:
        connection.close()

    event_ids = {str(row["id"]) for row in events}
    event_counts: dict[str, int] = {}
    world_event_ids: list[str] = []
    attention: list[dict[str, Any]] = []
    deliberations: list[dict[str, Any]] = []
    causal_links: list[dict[str, Any]] = []
    for row in events:
        event_type = str(row["event_type"])
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type not in _COGNITION_EVENTS:
            world_event_ids.append(str(row["id"]))
        payload = _load_json(str(row["payload_json"]), {})
        if event_type == "ATTENTION_EVALUATED" and isinstance(payload, dict):
            attention.append(
                {
                    "tick": int(row["tick"]),
                    "seat_hash": _digest([str(row["seat_id"] or payload.get("seat", ""))])[0],
                    "decision": str(payload.get("decision", "")),
                    "reason_code": str(payload.get("reason_code", "")),
                    "trigger_event_hashes": _digest(
                        [str(item) for item in payload.get("trigger_event_ids", [])]
                    ),
                }
            )
        if event_type == "DELIBERATION_COMMITTED":
            deliberations.append(
                {
                    "tick": int(row["tick"]),
                    "seat_hash": _digest([str(row["seat_id"] or "")])[0],
                    "event_hash": _digest([str(row["id"])])[0],
                }
            )
        if event_type in {
            "CRISIS_RESOLVED",
            "CRISIS_SETTLED",
            "DECISION_HORIZON_ESTABLISHED",
            "DECISION_HORIZON_HELD",
            "DECISION_HORIZON_REVISED",
            "DELIBERATION_COMMITTED",
        }:
            parents = _load_json(str(row["causal_parent_ids"]), [])
            causal_links.append(
                {
                    "event_hash": _digest([str(row["id"])])[0],
                    "event_type": event_type,
                    "parent_count": len(parents) if isinstance(parents, list) else 0,
                    "parents_exist": all(str(parent) in event_ids for parent in parents)
                    if isinstance(parents, list)
                    else False,
                }
            )

    actor_known: dict[str, list[str]] = {}
    for row in lifetimes:
        known_ids: list[str] = []
        knowledge = _load_json(str(row["knowledge_json"]), [])
        if isinstance(knowledge, list):
            for item in knowledge:
                if isinstance(item, dict) and str(item.get("event_id", "")) in event_ids:
                    known_ids.append(str(item["event_id"]))
        actor_known[str(row["seat"])] = sorted(set(known_ids))

    reopen = [item for item in attention if item["decision"] == "REOPEN"]
    background = [item for item in attention if item["decision"] == "BACKGROUND"]
    return {
        "worldline_hash": _digest([worldline_id])[0],
        "event_counts": dict(sorted(event_counts.items())),
        "world_event_count": len(world_event_ids),
        "world_event_hashes": _digest(world_event_ids),
        "actor_known_event_counts": {
            seat: len(ids) for seat, ids in actor_known.items()
        },
        "actor_known_event_hashes": {
            seat: _digest(ids) for seat, ids in actor_known.items()
        },
        "attention": {
            "count": len(attention),
            "reopen_count": len(reopen),
            "background_count": len(background),
            "records": attention,
        },
        "deliberations": {
            "count": len(deliberations),
            "records": deliberations,
        },
        "causal_links": causal_links,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: v6_proof_receipt.py DATABASE WORLDLINE_ID", file=sys.stderr)
        return 2
    try:
        receipt = audit(Path(sys.argv[1]), sys.argv[2])
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(json.dumps({"verdict": "NEEDS_WORK", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export a controller-blind trace from public SQLite event fields only."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_PUBLIC_EVENTS = {
    "AGREEMENT_CREATED",
    "CRISIS_SETTLED",
    "ENTITY_STATE_CHANGED",
    "FIELD_EVENT_APPLIED",
    "INVESTIGATION_COMPLETED",
    "MESSAGE_DELIVERED",
    "MESSAGE_DISPATCHED",
    "OFFER_ACCEPTED",
    "OFFER_PROPOSED",
    "OPERATION_COMPLETED",
}


def _public_event(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(str(row["payload_json"]))
    target = (
        payload.get("entity_id")
        or payload.get("message_id")
        or payload.get("operation_id")
        or payload.get("crisis_id")
        or payload.get("offer_id")
        or "world"
    )
    return {
        "tick": int(row["tick"]),
        "subject": str(payload.get("recipient") or payload.get("from") or "world"),
        "action": str(row["event_type"]),
        "target": str(target),
        "outcome": str(payload.get("after") or payload.get("status") or "public"),
        "public_state": str(payload.get("phase") or payload.get("delivery_tick") or "changed"),
        "public_evidence": [
            {
                "id": str(row["id"]),
                "kind": str(row["event_type"]),
                "tick": int(row["tick"]),
            }
        ],
    }


def export(database: Path, worldline_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, tick, event_type, payload_json
            FROM worldline_events
            WHERE worldline_id = ? AND event_type IN ({placeholders})
            ORDER BY sequence
            """.format(placeholders=", ".join("?" for _ in _PUBLIC_EVENTS)),
            [worldline_id, *_PUBLIC_EVENTS],
        ).fetchall()
    finally:
        connection.close()
    return {"worldline_id": worldline_id, "trace": [_public_event(row) for row in rows]}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: v6_export_public_trace.py DATABASE WORLDLINE_ID", file=sys.stderr)
        return 2
    try:
        payload = export(Path(sys.argv[1]), sys.argv[2])
    except (OSError, sqlite3.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"verdict": "NEEDS_WORK", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

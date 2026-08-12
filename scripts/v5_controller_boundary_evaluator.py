#!/usr/bin/env python3
"""Blind evaluator for the public behavioral trace around a controller boundary.

The evaluator intentionally has no Chronicle imports and receives no controller
labels.  It only checks whether adjacent public behavior changes without a
public cause.  The harness can keep the Human/Hermes labels out of the input
and compare the result with those labels after the process exits.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_FORBIDDEN_LABELS = {
    "agent",
    "controller",
    "hermes",
    "human",
    "profile",
    "session",
    "switch",
}
_BEHAVIOR_KEYS = ("action", "subject", "target", "outcome", "public_state")


def _contains_hidden_label(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(label in str(key).lower() for label in _FORBIDDEN_LABELS):
                return True
            if _contains_hidden_label(child):
                return True
    elif isinstance(value, list):
        return any(_contains_hidden_label(child) for child in value)
    elif isinstance(value, str):
        lowered = value.lower()
        return any(label in lowered for label in _FORBIDDEN_LABELS)
    return False


def _behavior_fingerprint(event: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(event.get(key) for key in _BEHAVIOR_KEYS)


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    trace = payload.get("trace")
    if not isinstance(trace, list) or not trace:
        return {"verdict": "NEEDS_WORK", "reason": "trace_required"}
    if _contains_hidden_label(payload):
        return {"verdict": "NEEDS_WORK", "reason": "hidden_controller_label_exposed"}
    if any(not isinstance(event, dict) for event in trace):
        return {"verdict": "NEEDS_WORK", "reason": "trace_events_must_be_objects"}

    unexplained: list[dict[str, Any]] = []
    for index, (previous, current) in enumerate(zip(trace, trace[1:], strict=False), start=1):
        if _behavior_fingerprint(previous) == _behavior_fingerprint(current):
            continue
        has_public_cause = bool(
            current.get("cause")
            or current.get("public_evidence")
            or current.get("deterministic_transition")
        )
        if not has_public_cause:
            unexplained.append(
                {
                    "from_index": index - 1,
                    "to_index": index,
                    "from_tick": previous.get("tick"),
                    "to_tick": current.get("tick"),
                }
            )

    return {
        "verdict": "PASS" if not unexplained else "NEEDS_WORK",
        "trace_events": len(trace),
        "unexplained_discontinuities": unexplained,
    }


def main() -> int:
    raw = sys.stdin.read() if len(sys.argv) == 1 or sys.argv[1] == "-" else open(sys.argv[1], encoding="utf-8").read()
    try:
        result = evaluate(json.loads(raw))
    except (OSError, json.JSONDecodeError, TypeError):
        result = {"verdict": "NEEDS_WORK", "reason": "invalid_json"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from chronicle.config import write_runtime_env
from chronicle.db import stable_hash
from chronicle.hermes import HermesClient
from chronicle.host import ChronicleHost


def test_memory_version_rejects_broken_hash_chain(host):
    first = host.db.add_memory_version("A", "first", stable_hash(""), ["life-1"], "reflection")
    with pytest.raises(ValueError, match="previous memory hash"):
        host.db.add_memory_version("A", "first", "wrong", ["life-1"], "reflection")

    with pytest.raises(ValueError, match="memory hash"):
        host.db.add_memory_version(
            "A", "second", first["memory_hash"], ["life-2"], "reflection", memory_hash="wrong"
        )


def test_ordinary_live_wake_rolls_back_native_memory_mutation(host, app_config, monkeypatch):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    write_runtime_env(
        configured,
        {"CHRONICLE_CHRONICLE_SEAT_A_API_SERVER_KEY": "profile-key"},
    )
    live_host = ChronicleHost(configured, db=host.db, pack=host.pack)
    memory_path = live_host._native_memory_path("A")
    ready = SimpleNamespace(ready_for=lambda _profile: True)
    monkeypatch.setattr("chronicle.host.probe", lambda *_args, **_kwargs: ready)
    monkeypatch.setattr(HermesClient, "create_fresh_session", lambda *_args, **_kwargs: "session-a")

    def fake_chat(*_args, **_kwargs):
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("unauthorized mutation\n", encoding="utf-8")
        response = {
            "assessment": "The report remains partial.",
            "belief_updates": [],
            "intentions": [],
            "uncertainties": [],
            "memory_action": "NO_CHANGE",
            "memory_text": "",
        }
        return json.dumps(response), "session-a"

    monkeypatch.setattr(HermesClient, "chat", fake_chat)

    result = live_host.wake("A", tick=4, live=True)

    assert result["source"] == "hermes"
    assert result["memory"]["changed"] is False
    assert memory_path.exists() is False
    violations = live_host.db.protocol_violations("A")
    assert len(violations) == 1
    assert violations[0]["action"] == "rollback"
    assert "unauthorized mutation" in violations[0]["memory_diff"]


def test_memory_audit_tables_are_append_only(host):
    version = host.db.add_memory_version("A", "first", stable_hash(""), ["life-1"], "reflection")
    host.db.add_protocol_violation(
        {
            "seat": "A",
            "tick": 4,
            "wake_type": "observation",
            "reason": "test",
            "action": "blocked",
            "runtime_epoch": "epoch-test",
        }
    )
    violation = host.db.protocol_violations("A")[0]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with host.db.transaction() as connection:
            connection.execute("UPDATE memory_versions SET memory_text = 'changed' WHERE id = ?", (version["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with host.db.transaction() as connection:
            connection.execute("DELETE FROM protocol_violations WHERE id = ?", (violation["id"],))

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.db import SCHEMA, ChronicleDB
from chronicle.models import ActionValidation, WorldlineKind, WorldlineStatus
from chronicle.runtime import WorldlineConflict, WorldlineRuntime
from chronicle.worldline import project_worldline


def test_worldline_keeps_seat_context_separate_from_branch_truth(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    entered = runtime.create("jiangnan-prince-command")
    worldline_id = entered["worldline"]["id"]

    assert entered["worldline"]["kind"] == WorldlineKind.BRANCH.value
    assert entered["context"]["seat"] == "A"
    assert "capital_status" not in entered["context"]["known_world"]
    assert "projection" not in entered["context"]
    assert all(item["received_at"] <= 44 for item in entered["context"]["what_reached_you"])
    assert project_worldline(host.db.worldline_events(worldline_id))["court_decision"]["southern_command_proposal"] == "accepted"

    with pytest.raises(ValueError, match="locked"):
        host.set_tick(45)

    interaction = runtime.input(worldline_id, "给东部传信，请尽快确认关口")
    assert interaction["interaction"]["status"] == ActionValidation.ACCEPTED.value
    first = runtime.advance(worldline_id)
    assert first["advanced_to"] == 45
    assert first["agent_wakes"] == []
    second = runtime.advance(worldline_id)
    assert second["advanced_to"] == 47
    assert second["agent_wakes"] == []
    advanced = runtime.advance(worldline_id)
    assert advanced["advanced_to"] == 49
    assert any(item["event_type"] == "MESSAGE_DELIVERED" for item in host.db.worldline_events(worldline_id))
    dispatch = next(
        event for event in host.db.worldline_events(worldline_id)
        if event["event_type"] == "MESSAGE_DISPATCHED"
    )
    assert dispatch["payload"]["causal_envelope"] == "message_propagation"
    c_lifetime = host.db.worldline_lifetime(worldline_id, "C")
    assert c_lifetime is not None
    assert c_lifetime["profile_name"].endswith("-seat-c")
    assert c_lifetime["profile_metadata"]["mode"] == "fixture"

    sealed = runtime.seal(worldline_id)
    assert sealed["worldline"]["status"] == WorldlineStatus.SEALED.value
    report = runtime.debrief(worldline_id)
    assert report["what_you_saw"]["contexts"]
    assert report["what_was_true"]["branch_projection"]["messages"][0]["status"] == "delivered"
    assert report["what_you_changed"]
    assert "score" not in json.dumps(report, ensure_ascii=False).lower()


def test_worldline_input_statuses_and_confirmation(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    inquiry = runtime.input(worldline_id, "我现在有什么消息？")
    assert inquiry["interaction"]["kind"] == "inquiry"
    assert inquiry["interaction"]["status"] is None

    unsupported = runtime.input(worldline_id, "发动大战并改写历史")
    assert unsupported["interaction"]["status"] == ActionValidation.UNSUPPORTED.value

    impossible = runtime.input(worldline_id, "给西部传信")
    assert impossible["interaction"]["status"] == ActionValidation.IMPOSSIBLE.value

    pending = runtime.input(worldline_id, "任命南方指挥")
    assert pending["interaction"]["requires_confirmation"] is True
    confirmation_id = pending["interaction"]["confirmation_id"]
    confirmed = runtime.confirm(worldline_id, confirmation_id)
    assert confirmed["interaction"]["status"] == ActionValidation.ACCEPTED.value
    repeated_confirm = runtime.confirm(worldline_id, confirmation_id)
    assert repeated_confirm["interaction"]["result"]["idempotent"] is True
    assert host.db.worldline(worldline_id)["pending_confirmation_json"] == ""
    action_events = [
        event for event in host.db.worldline_events(worldline_id) if event["event_type"] == "AUTHORITY_APPOINTED"
    ]
    confirmation_event = next(
        event
        for event in host.db.worldline_events(worldline_id)
        if event["event_type"] == "INTENT_CONFIRMED"
        and event["payload"]["confirmation_id"] == confirmation_id
    )
    assert action_events
    assert confirmation_event["id"] in action_events[0]["causal_parent_ids"]


def test_api_worldline_lock_and_refresh_resume(app_config):
    client = TestClient(create_app(app_config))
    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 200
    created = client.post("/api/worldlines", json={"entry_id": "jiangnan-prince-command"})
    assert created.status_code == 200
    worldline_id = created.json()["worldline"]["id"]

    assert client.get("/api/worldlines/active").status_code == 200
    assert client.get("/api/worldlines/active").json()["active"]["worldline"]["id"] == worldline_id
    assert client.get("/api/scenario").status_code == 423
    assert client.get("/api/timeline").status_code == 423
    assert client.post("/api/canon/advance-next").status_code == 423
    assert client.get("/api/entries").status_code == 423
    assert client.get("/api/lifetimes/A").status_code == 423
    assert client.get("/api/sources/a019").status_code == 200
    assert client.get("/api/sources/a020").status_code == 404
    assert client.get(f"/api/worldlines/{worldline_id}/context").status_code == 200

    assert client.post(f"/api/worldlines/{worldline_id}/seal", json={}).status_code == 200
    assert client.get("/api/scenario").status_code == 200
    assert client.get(f"/api/worldlines/{worldline_id}/debrief").status_code == 200
    assert client.get("/api/worldlines").json()["worldlines"][0]["id"] == worldline_id


def test_http_fixture_observe_enter_delivery_refresh_seal_debrief(app_config):
    client = TestClient(create_app(app_config))

    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 200
    created = client.post(
        "/api/worldlines",
        json={"entry_id": "jiangnan-prince-command", "seat": "A", "live": False},
    )
    assert created.status_code == 200
    worldline_id = created.json()["worldline"]["id"]

    input_response = client.post(
        f"/api/worldlines/{worldline_id}/input",
        json={"text": "给东部传信，请尽快确认关口"},
    )
    assert input_response.status_code == 200
    assert input_response.json()["interaction"]["status"] == ActionValidation.ACCEPTED.value

    delivery_response = None
    for expected_tick in (45, 47, 49):
        delivery_response = client.post(
            f"/api/worldlines/{worldline_id}/advance",
            json={"live": False},
        )
        assert delivery_response.status_code == 200
        assert delivery_response.json()["worldline"]["current_tick"] == expected_tick
    assert delivery_response is not None
    assert delivery_response.json()["deliveries"]

    refreshed = client.get("/api/worldlines/active")
    assert refreshed.status_code == 200
    assert refreshed.json()["active"]["worldline"]["id"] == worldline_id
    assert refreshed.json()["active"]["worldline"]["current_tick"] == 49
    assert not any(
        item.get("message_id")
        for item in refreshed.json()["active"]["context"]["what_reached_you"]
    )

    branch_lifetime = client.get(f"/api/worldlines/{worldline_id}/lifetimes/A")
    assert branch_lifetime.status_code == 200
    assert branch_lifetime.json()["lifetime"]["records"]
    assert branch_lifetime.json()["lifetime"]["stats"]["observations"] >= 1

    assert client.post(f"/api/worldlines/{worldline_id}/seal", json={}).status_code == 200
    assert client.get("/api/worldlines/active").json()["active"] is None

    c_lifetime = client.get(f"/api/worldlines/{worldline_id}/lifetimes/C")
    assert c_lifetime.status_code == 200
    assert any(
        record["wake_type"] == "OBSERVATION"
        for record in c_lifetime.json()["lifetime"]["records"]
    )
    debrief = client.get(f"/api/worldlines/{worldline_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["what_you_saw"]["contexts"]
    assert debrief.json()["what_was_true"]["branch_projection"]["messages"]


def test_v2_branch_lifetime_and_ledger_endpoints_are_branch_scoped(app_config):
    client = TestClient(create_app(app_config))
    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 200
    created = client.post("/api/worldlines", json={"entry_id": "jiangnan-prince-command"})
    worldline_id = created.json()["worldline"]["id"]

    lifetimes = client.get(f"/api/worldlines/{worldline_id}/lifetimes")
    assert lifetimes.status_code == 200
    assert len(lifetimes.json()["lifetimes"]) == 3
    assert {item["status"] for item in lifetimes.json()["lifetimes"]} == {"ACTIVE"}
    assert "knowledge" not in next(item for item in lifetimes.json()["lifetimes"] if item["seat"] == "C")
    current_lifetime = client.get(f"/api/worldlines/{worldline_id}/lifetimes/A").json()["lifetime"]
    assert current_lifetime["seat"] == "A"
    assert current_lifetime["records"]
    assert current_lifetime["stats"]["observations"] == sum(
        record["wake_type"] == "OBSERVATION" for record in current_lifetime["records"]
    )
    assert client.get(f"/api/worldlines/{worldline_id}/lifetimes/C").status_code == 409
    assert "runtime_alias" not in next(
        item["actor"] for item in lifetimes.json()["lifetimes"] if item["seat"] == "C"
    )

    ledger = client.get(f"/api/worldlines/{worldline_id}/ledger")
    assert ledger.status_code == 200
    assert ledger.json()["cursor"] == ledger.json()["events"][-1]["sequence"]
    assert ledger.json()["events"][0]["event_type"] == "WORLDLINE_CREATED"
    assert client.get("/api/lifetimes/A").status_code == 423

    assert client.post(f"/api/worldlines/{worldline_id}/seal", json={}).status_code == 200
    sealed_lifetime = client.get(f"/api/worldlines/{worldline_id}/lifetimes/A")
    assert sealed_lifetime.status_code == 200
    assert sealed_lifetime.json()["lifetime"]["status"] == "SEALED"
    assert "knowledge" in client.get(f"/api/worldlines/{worldline_id}/lifetimes/C").json()["lifetime"]


def test_active_worldline_responses_do_not_leak_other_seat_context(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")
    runtime.advance(worldline_id)
    runtime.advance(worldline_id)
    advanced = runtime.advance(worldline_id)

    assert advanced["deliveries"][0]["message_id"]
    assert advanced["canon_events"] == []
    assert all("context" not in wake and "response" not in wake for wake in advanced["agent_wakes"])
    ledger = runtime.ledger(worldline_id)
    assert not any(event["event_type"] == "AGENT_WAKE" for event in ledger["events"])
    assert not any(
        event["payload"].get("seat") == "C" and "what_reached_you" in event["payload"]
        for event in ledger["events"]
    )


def test_v2_migration_backups_and_imports_legacy_branch(tmp_path):
    path = tmp_path / "chronicle.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO branches(id, fork_id, status, tick, state_json, boundary_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("branch-old", "jiangnan-prince-command", "active", 45, json.dumps({"tick": 45}), "", "2026-01-01", "2026-01-01"),
        )
        connection.execute(
            "INSERT INTO branch_records(id, branch_id, tick, actor_seat, action_json, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("record-old", "branch-old", 45, "A", json.dumps({"type": "WAIT"}), json.dumps({"status": "accepted"}), "2026-01-01"),
        )

    db = ChronicleDB(path)
    assert db.migration_backup_path is not None
    assert db.migration_backup_path.exists()
    assert db.get_meta("schema_version") == "7"
    imported = db.worldline("legacy-branch-old")
    assert imported is not None
    assert imported["status"] == WorldlineStatus.SEALED.value
    assert db.worldline_events("legacy-branch-old")[0]["event_type"] == "LEGACY_IMPORT"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with db.transaction() as connection:
            connection.execute("UPDATE worldline_events SET tick = 1 WHERE id = ?", (db.worldline_events("legacy-branch-old")[0]["id"],))


def test_agent_context_is_frozen_after_new_delivery(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    runtime.input(worldline_id, "给东部传信，请尽快确认关口")
    first = runtime.advance(worldline_id)
    assert first["advanced_to"] == 45
    assert runtime.advance(worldline_id)["advanced_to"] == 47
    advanced = runtime.advance(worldline_id)

    assert advanced["advanced_to"] == 49
    events = host.db.worldline_events(worldline_id)
    c_contexts = [
        event["payload"]
        for event in events
        if event["event_type"] == "CONTEXT_FROZEN" and event.get("seat_id") == "C"
    ]
    assert c_contexts
    assert c_contexts[-1]["tick"] == 49
    assert any(item.get("message_id") for item in c_contexts[-1]["what_reached_you"])


def test_failed_agent_wake_does_not_commit_the_moment(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")

    def fail_wake(*args, **kwargs):
        raise RuntimeError("simulated Hermes failure")

    monkeypatch.setattr(runtime, "_wake_agents_for_deliveries", fail_wake)

    with pytest.raises(RuntimeError, match="simulated Hermes failure"):
        runtime.advance(worldline_id)

    row = host.db.worldline(worldline_id)
    assert row["current_tick"] == 44
    event_types = [event["event_type"] for event in host.db.worldline_events(worldline_id)]
    assert "TIME_ADVANCED" not in event_types
    assert "MESSAGE_DELIVERED" not in event_types


def test_failed_input_compilation_does_not_commit_partial_events(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    before_event_ids = {event["id"] for event in host.db.worldline_events(worldline_id)}

    def fail_compile(*args, **kwargs):
        raise RuntimeError("simulated compiler failure")

    monkeypatch.setattr(runtime.compiler, "compile", fail_compile)
    with pytest.raises(RuntimeError, match="simulated compiler failure"):
        runtime.input(worldline_id, "给东部传信，请尽快确认关口")

    new_events = [
        event
        for event in host.db.worldline_events(worldline_id)
        if event["id"] not in before_event_ids
    ]
    assert new_events == []


def test_moment_state_conflict_rolls_back_prepared_events(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    event = {
        "id": "prepared-but-conflicted",
        "tick": 45,
        "event_type": "TIME_ADVANCED",
        "seat_id": "A",
        "payload": {"from_tick": 44, "to_tick": 45},
        "provenance": "branch_derived",
        "causal_parent_ids": [],
        "runtime_epoch": "test",
    }

    with pytest.raises(sqlite3.IntegrityError, match="state changed"):
        host.db.commit_worldline_moment(
            worldline_id,
            [event],
            current_tick=45,
            expected_current_tick=999,
        )

    assert host.db.worldline(worldline_id)["current_tick"] == 44
    assert not any(item["id"] == event["id"] for item in host.db.worldline_events(worldline_id))


def test_initial_worldline_bundle_rolls_back_on_lifetime_failure(host):
    values = {
        "id": "wl-initialization-failure",
        "scenario_id": "jiashen",
        "kind": "BRANCH",
        "status": "ACTIVE",
        "entry_id": "jiangnan-prince-command",
        "controller_seat": "A",
        "current_tick": 44,
    }
    event = {
        "id": "initial-event-that-must-rollback",
        "tick": 44,
        "event_type": "WORLDLINE_CREATED",
        "payload": {},
        "provenance": "branch_derived",
        "causal_parent_ids": [],
    }
    lifetime = {
        "id": "initial-lifetime-a",
        "seat": "A",
        "controller": "HUMAN",
    }

    with pytest.raises(sqlite3.IntegrityError):
        host.db.create_worldline_bundle(
            values,
            [event],
            [lifetime, {**lifetime, "id": "initial-lifetime-a-duplicate"}],
            {},
        )

    assert host.db.worldline(values["id"]) is None
    assert host.db.worldline_events(values["id"]) == []
    assert host.db.worldline_lifetimes(values["id"]) == []


def test_same_tick_snapshot_tracks_latest_ledger_cursor(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")
    runtime.seal(worldline_id)

    snapshot = host.db.worldline_snapshot(worldline_id, 44)
    events = host.db.worldline_events(worldline_id)
    assert snapshot["ledger_cursor"] == events[-1]["sequence"]
    assert snapshot["projection"]["messages"]


def test_seal_closes_branch_lifetimes(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.seal(worldline_id)

    assert {item["status"] for item in host.db.worldline_lifetimes(worldline_id)} == {
        WorldlineStatus.SEALED.value
    }


def test_active_worldline_locks_runtime_configuration(app_config):
    client = TestClient(create_app(app_config))
    assert client.post("/api/canon/advance", json={"tick": 44}).status_code == 200
    assert client.post("/api/worldlines", json={"entry_id": "jiangnan-prince-command"}).status_code == 200

    response = client.post(
        "/api/setup/configure",
        json={"base_url": "https://provider.example/v1", "api_key": "test-key", "model": "test-model"},
    )
    assert response.status_code == 423
    assert client.post("/api/bootstrap").status_code == 423


def test_pending_confirmation_cannot_be_overwritten_and_can_be_cancelled(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    pending = runtime.input(worldline_id, "任命南方指挥")
    with pytest.raises(WorldlineConflict, match="confirm or cancel"):
        runtime.input(worldline_id, "任命另一位指挥")

    cancelled = runtime.cancel(worldline_id, pending["interaction"]["confirmation_id"])
    assert cancelled["interaction"]["status"] == ActionValidation.AMBIGUOUS.value
    repeated_cancel = runtime.cancel(worldline_id, pending["interaction"]["confirmation_id"])
    assert repeated_cancel["interaction"]["result"]["idempotent"] is True
    assert host.db.worldline(worldline_id)["pending_confirmation_json"] == ""
    assert any(
        event["event_type"] == "INTENT_CANCELLED"
        for event in host.db.worldline_events(worldline_id)
    )


def test_pending_confirmation_cannot_be_discarded_by_seal(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "任命南方指挥")

    with pytest.raises(WorldlineConflict, match="confirm or cancel"):
        runtime.seal(worldline_id)


def test_worldline_runtime_mode_is_immutable(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    monkeypatch.setattr(runtime, "_assert_live_ready", lambda: None)
    worldline_id = runtime.create("jiangnan-prince-command", live=True)["worldline"]["id"]

    with pytest.raises(WorldlineConflict, match="runtime mode"):
        runtime.advance(worldline_id, live=False)


def test_database_enforces_one_active_human_worldline(host):
    host.db.create_worldline(
        {
            "id": "wl-first",
            "scenario_id": "jiashen",
            "entry_id": "jiangnan-prince-command",
            "controller_seat": "A",
            "current_tick": 44,
        }
    )
    with pytest.raises(sqlite3.IntegrityError):
        host.db.create_worldline(
            {
                "id": "wl-second",
                "scenario_id": "jiashen",
                "entry_id": "jiangnan-prince-command",
                "controller_seat": "B",
                "current_tick": 44,
            }
        )


def test_agent_response_is_durable_in_branch_events_and_lifetime(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")

    runtime.advance(worldline_id)
    runtime.advance(worldline_id)
    advanced = runtime.advance(worldline_id)
    events = host.db.worldline_events(worldline_id)
    c_lifetime = host.db.worldline_lifetime(worldline_id, "C")

    assert advanced["agent_wakes"]
    assert any(event["event_type"] == "AGENT_INTENT_ACCEPTED" for event in events)
    assert any(
        event["event_type"] == "MESSAGE_DISPATCHED" and event.get("seat_id") == "C"
        for event in events
    )
    assert any(event["event_type"] == "WAIT_COMMITTED" for event in events)
    assert any(
        item.get("message_id")
        for item in c_lifetime["knowledge"]
        if isinstance(item, dict)
    )


def test_invalid_agent_intention_is_durable_rejection(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")
    runtime.advance(worldline_id)
    runtime.advance(worldline_id)
    original_wake = runtime._wake_agents_for_deliveries

    def invalid_wake(*args, **kwargs):
        wakes = original_wake(*args, **kwargs)
        wakes[0]["payload"]["response"]["intentions"] = [
            {"action": "ISSUE_ORDER", "target": "capital", "reason": "未经授权的命令", "payload": {}}
        ]
        return wakes

    monkeypatch.setattr(runtime, "_wake_agents_for_deliveries", invalid_wake)
    runtime.advance(worldline_id)

    events = host.db.worldline_events(worldline_id)
    rejections = [event for event in events if event["event_type"] == "AGENT_INTENT_REJECTED"]
    assert rejections
    assert not any(event["event_type"] == "ORDER_ISSUED" for event in events if event.get("seat_id") == "C")


def test_compound_intent_is_explicitly_preserved_for_clarification(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    result = runtime.input(
        worldline_id,
        "接受太子南下，但暂不公开，同时再催东部兵力入援。",
    )

    interaction = result["interaction"]
    assert interaction["status"] == ActionValidation.AMBIGUOUS.value
    assert len(interaction["interpreted_actions"]) == 2
    assert {item["action"]["type"] for item in interaction["result"]["action_results"]} == {
        "SEND_MESSAGE",
        "SET_DISCLOSURE",
    }
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        for event in host.db.worldline_events(worldline_id)
    )


def test_observation_delivery_is_durable_without_unnecessary_agent_wake(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")

    reply = None
    for expected_tick in (45, 47, 49, 51, 52, 53, 54, 55, 56):
        advanced = runtime.advance(worldline_id)
        assert advanced["advanced_to"] == expected_tick
        if expected_tick == 54:
            reply = advanced
    assert reply is not None
    assert any(item.get("from") == "C" for item in reply["deliveries"])

    result = runtime.advance(worldline_id)
    assert result["advanced_to"] == 57
    assert result["agent_wakes"] == []
    events = host.db.worldline_events(worldline_id)
    assert any(
        event["event_type"] == "OBSERVATION_DELIVERED"
        and event["payload"].get("observation_id") == "o019-c"
        for event in events
    )
    assert not any(
        event["event_type"] == "AGENT_WAKE" and event["tick"] == 57 and event.get("seat_id") == "C"
        for event in events
    )
    c_lifetime = host.db.worldline_lifetime(worldline_id, "C")
    assert any(item.get("observation_id") == "o019-c" for item in c_lifetime["knowledge"])

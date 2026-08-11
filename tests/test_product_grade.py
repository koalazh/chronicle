from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import chronicle.app as app_module
import chronicle.cli as cli_module
import chronicle.hermes as hermes_module
from chronicle.app import create_app
from chronicle.config import write_runtime_env
from chronicle.db import SCHEMA, ChronicleDB
from chronicle.interaction import IntentCompiler
from chronicle.models import ActionType, ActionValidation, BranchAction
from chronicle.runtime import WorldlineRuntime
from chronicle.worldline import project_worldline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_rejects_non_loopback_host_override(app_config, monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "load_config", lambda: app_config)

    assert cli_module.main(["serve", "--host", "0.0.0.0"]) == 1
    assert "loopback" in capsys.readouterr().err


def test_cli_start_uses_the_product_runtime_entry(app_config, monkeypatch):
    created: dict[str, object] = {}
    served: dict[str, object] = {}

    def fake_create(config, *, manage_live_runtime_on_startup=False):
        created.update(
            {
                "config": config,
                "manage_live_runtime_on_startup": manage_live_runtime_on_startup,
            }
        )
        return "chronicle-app"

    def fake_run(app, **kwargs):
        served.update({"app": app, **kwargs})

    monkeypatch.setattr(cli_module, "load_config", lambda: app_config)
    monkeypatch.setattr(cli_module, "create_app", fake_create)
    monkeypatch.setattr(cli_module.uvicorn, "run", fake_run)

    assert cli_module.main(["start"]) == 0
    assert created == {"config": app_config, "manage_live_runtime_on_startup": True}
    assert served["app"] == "chronicle-app"
    assert served["reload"] is False


def test_cli_serve_uses_an_import_string_when_development_reload_is_enabled(
    app_config, monkeypatch
):
    served: dict[str, object] = {}

    monkeypatch.setattr(cli_module, "load_config", lambda: replace(app_config, dev=True))
    monkeypatch.setattr(
        cli_module.uvicorn,
        "run",
        lambda app, **kwargs: served.update({"app": app, **kwargs}),
    )

    assert cli_module.main(["serve"]) == 0
    assert served["app"] == "chronicle.app:app"
    assert served["reload"] is True


def test_app_rejects_non_loopback_binding(app_config):
    with pytest.raises(ValueError, match="loopback"):
        create_app(replace(app_config, host="0.0.0.0"))


def test_runtime_env_rejects_newline_injection(app_config):
    with pytest.raises(ValueError, match="newlines"):
        write_runtime_env(app_config, {"CHRONICLE_LLM_MODEL": "safe\nINJECTED=value"})


def test_setup_test_rejects_private_provider_and_unknown_model(app_config, monkeypatch):
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": [{"id": "other-model"}]},
        )

    monkeypatch.setattr(app_module.httpx, "get", fake_get)
    monkeypatch.setattr(
        app_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    client = TestClient(create_app(app_config))

    private = client.post(
        "/api/setup/test",
        json={
            "base_url": "http://169.254.169.254/latest/meta-data",
            "api_key": "secret-probe",
            "model": "requested-model",
        },
    )
    assert private.status_code == 200
    assert private.json()["ok"] is False
    assert calls == []

    unknown = client.post(
        "/api/setup/test",
        json={
            "base_url": "https://provider.example/v1",
            "api_key": "secret-probe",
            "model": "requested-model",
        },
    )
    assert unknown.status_code == 200
    assert unknown.json()["ok"] is False
    assert "requested-model" in unknown.json()["message"]


def test_legacy_import_projection_preserves_state(tmp_path):
    path = tmp_path / "legacy.db"
    state = {"tick": 45, "locations": {"A": "capital"}, "messages": [{"id": "old-message"}]}
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO branches(id, fork_id, status, tick, state_json, boundary_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("old", "jiangnan-prince-command", "active", 45, json.dumps(state), "", "2026-01-01", "2026-01-01"),
        )

    db = ChronicleDB(path)
    projection = project_worldline(db.worldline_events("legacy-old"))

    assert projection["locations"] == {"A": "capital"}
    assert projection["messages"] == [{"id": "old-message"}]


def test_agent_actions_require_valid_targets_and_routes(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    row = host.db.worldline(worldline_id)
    agent_row = {**row, "controller_seat": "C"}

    invalid_move = runtime._validate_action(
        agent_row,
        BranchAction(type=ActionType.MOVE_PRINCIPAL, target="western_front"),
    )
    invalid_prepare = runtime._validate_action(
        agent_row,
        BranchAction(type=ActionType.PREPARE_MOVEMENT, target="not-a-location"),
    )
    unroutable_prepare = runtime._validate_action(
        agent_row,
        BranchAction(type=ActionType.PREPARE_MOVEMENT, target="western_front"),
    )

    assert invalid_move[0] == ActionValidation.IMPOSSIBLE
    assert "route" in invalid_move[1]
    assert invalid_prepare[0] == ActionValidation.IMPOSSIBLE
    assert unroutable_prepare[0] == ActionValidation.IMPOSSIBLE
    assert "route" in unroutable_prepare[1]


def test_mixed_input_does_not_silently_drop_unknown_segment(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    result = runtime.input(worldline_id, "给东部传信，并且执行一项当前无法识别的安排")

    assert result["interaction"]["status"] == ActionValidation.AMBIGUOUS.value
    assert "无法识别" in result["interaction"]["result"]["reason"]
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        for event in host.db.worldline_events(worldline_id)
    )


@pytest.mark.parametrize(
    ("text", "expected_kind", "expected_action"),
    [
        ("我现在收到过哪些消息？", "inquiry", None),
        ("我知道哪些消息？", "inquiry", None),
        ("请给东部发消息，请尽快确认关口", "intent", ActionType.SEND_MESSAGE),
        ("请给东部写信", "intent", ActionType.SEND_MESSAGE),
        ("请把消息发给东部", "intent", ActionType.SEND_MESSAGE),
    ],
)
def test_common_natural_language_phrasings_are_compiled(host, text, expected_kind, expected_action):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    compiled = runtime.compiler.compile(text, runtime.seat_context(worldline_id), runtime.pack)

    assert compiled.kind == expected_kind
    if expected_action is None:
        assert compiled.actions == ()
    else:
        assert compiled.actions[0].type == expected_action


def test_natural_language_inquiry_round_trips_through_api(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    client = TestClient(create_app(host.config))

    response = client.post(
        f"/api/worldlines/{worldline_id}/input",
        json={"text": "我现在收到过哪些消息？"},
    )

    assert response.status_code == 200
    interaction = response.json()["interaction"]
    assert interaction["kind"] == "inquiry"
    assert interaction["status"] is None
    assert interaction["answer"]
    assert interaction["result"]["reason"] == ""


def test_negated_disclosure_is_compiled_as_private(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    context = runtime.seat_context(worldline_id)

    compiled = IntentCompiler().compile("不要公开", context, runtime.pack)

    assert compiled.actions[0].type == ActionType.SET_DISCLOSURE
    assert compiled.actions[0].payload == "private"


def test_final_human_context_is_available_in_debrief(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.input(worldline_id, "给东部传信，请尽快确认关口")

    while host.db.worldline(worldline_id)["status"] == "ACTIVE":
        runtime.advance(worldline_id)
        if any(item.get("message_id") for item in runtime.seat_context(worldline_id).what_reached_you):
            break

    assert any(item.get("message_id") for item in runtime.seat_context(worldline_id).what_reached_you)
    runtime.seal(worldline_id)
    report = runtime.debrief(worldline_id)

    assert any(
        item.get("message_id")
        for context in report["what_you_saw"]["contexts"]
        for item in context.get("what_reached_you", [])
    )


def test_snapshot_failure_rolls_back_the_moment(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot sink failed")

    monkeypatch.setattr(host.db, "_insert_snapshot", fail_snapshot, raising=False)
    with pytest.raises(RuntimeError, match="snapshot sink failed"):
        runtime.advance(worldline_id)

    assert host.db.worldline(worldline_id)["current_tick"] == 44
    assert not any(
        event["event_type"] == "TIME_ADVANCED"
        for event in host.db.worldline_events(worldline_id)
    )


def test_boundary_seal_failure_does_not_leave_horizon_event(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]

    def fail_seal(*args, **kwargs):
        raise RuntimeError("seal sink failed")

    monkeypatch.setattr(host.db, "commit_worldline_seal", fail_seal)
    with pytest.raises(RuntimeError, match="seal sink failed"):
        runtime._seal_at_boundary(host.db.worldline(worldline_id), "horizon_reached")

    assert not any(
        event["event_type"] == "HORIZON_REACHED"
        for event in host.db.worldline_events(worldline_id)
    )


def test_sealed_worldline_rejects_low_level_event_append(host):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    runtime.seal(worldline_id)

    with pytest.raises(sqlite3.IntegrityError, match="sealed"):
        host.db.append_worldline_event(worldline_id, 44, "ILLEGAL_WRITE", {})


def test_frontend_exposes_real_result_and_accessibility_contract():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "web" / "app.js",
            PROJECT_ROOT / "web" / "api.js",
            PROJECT_ROOT / "web" / "state.js",
            PROJECT_ROOT / "web" / "router.js",
        )
    )
    index = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "此刻哪里值得我去活？" in source
    assert "active_knots" in source
    assert "data-action=\"inhabit\"" in source
    assert "data-action=\"leave-life\"" in source
    assert "AbortController" in source
    assert "aria-live" in source or "aria-live" in index
    assert "/api/worldlines" in source
    assert "Watch" not in source
    assert "Takeover" not in source


def test_lazy_profile_compensates_partial_install(app_config, monkeypatch):
    monkeypatch.setattr(
        hermes_module,
        "_run_cli",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    def fail_sync(*_args, **_kwargs):
        raise RuntimeError("config sync failed")

    monkeypatch.setattr(hermes_module, "_sync_profile_config", fail_sync)
    profile = app_config.hermes_home / "profiles" / "chronicle-12345678-seat-b"

    with pytest.raises(RuntimeError, match="config sync failed"):
        hermes_module.create_lazy_profile(app_config, "B", "wl-12345678", memory_text="seed")

    assert not profile.exists()


def test_existing_lazy_profile_seed_failure_is_compensated(app_config, monkeypatch):
    profile = "chronicle-12345678-seat-b"
    profile_home = app_config.hermes_home / "profiles" / profile
    profile_home.mkdir(parents=True, exist_ok=True)
    (profile_home / "chronicle-genesis.json").write_text(
        json.dumps({"profile": profile, "seat": "B", "worldline_id": "wl-12345678"}),
        encoding="utf-8",
    )
    def fail_seed(*_args, **_kwargs):
        raise RuntimeError("memory seed failed")

    monkeypatch.setattr(hermes_module, "seed_profile_memory", fail_seed)

    with pytest.raises(RuntimeError, match="memory seed failed"):
        hermes_module.create_lazy_profile(
            app_config,
            "B",
            "wl-12345678",
            memory_text="seed",
        )

    assert not profile_home.exists()


def test_lazy_profile_memory_mutation_is_rolled_back(host):
    runtime = WorldlineRuntime(host)
    profile = "chronicle-12345678-seat-b"
    path = hermes_module.profile_memory_path(host.config, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before\n", encoding="utf-8")
    before_text, before_hash = hermes_module.read_profile_memory(host.config, profile)
    path.write_text("unauthorized mutation\n", encoding="utf-8")

    violation = runtime._guard_lazy_profile_memory(
        {"id": "wl-12345678", "current_tick": 4},
        "B",
        profile,
        before_text,
        before_hash,
        True,
        "epoch-test",
        "ordinary lazy Agent Wake mutated Hermes Memory",
    )

    assert violation["memory_hash_restored"] == before_hash
    assert path.read_text(encoding="utf-8") == "before\n"
    assert host.db.protocol_violations("B")[0]["action"] == "rollback"


def test_lazy_wake_failure_removes_uncommitted_profile(host, monkeypatch):
    host.set_tick(44)
    runtime = WorldlineRuntime(host)
    worldline_id = runtime.create("jiangnan-prince-command")["worldline"]["id"]
    row = host.db.worldline(worldline_id)
    delivery = {
        "id": f"{worldline_id}:message-delivered:test",
        "worldline_id": worldline_id,
        "tick": 49,
        "event_type": "MESSAGE_DELIVERED",
        "seat_id": "C",
        "payload": {
            "message_id": "message-test",
            "from": "A",
            "recipient": "C",
            "payload": "请确认关口",
            "origin": "capital",
            "destination": "eastern-command",
        },
    }

    def fake_create(config, seat, branch_id, *, memory_text=None):
        profile = f"chronicle-{branch_id[-8:]}-seat-{seat.lower()}"
        profile_home = config.hermes_home / "profiles" / profile
        profile_home.mkdir(parents=True, exist_ok=True)
        (profile_home / "chronicle-genesis.json").write_text(
            json.dumps({"profile": profile, "seat": seat, "worldline_id": branch_id}),
            encoding="utf-8",
        )
        return profile, {"mode": "live", "worldline_id": branch_id, "seat": seat}

    monkeypatch.setattr(hermes_module, "create_lazy_profile", fake_create)
    monkeypatch.setattr(hermes_module, "profile_api_key", lambda *_args, **_kwargs: "profile-key")
    monkeypatch.setattr(
        hermes_module,
        "probe",
        lambda *_args, **_kwargs: SimpleNamespace(ready_for=lambda _profile: True),
    )
    monkeypatch.setattr(
        hermes_module.HermesClient,
        "create_fresh_session",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(hermes_module.HermesRuntimeError, match="lazy Seat wake failed"):
        runtime._wake_agents_for_deliveries(row, [delivery], live=True, epoch="epoch-test")

    profile = host.config.hermes_home / "profiles" / f"chronicle-{worldline_id[-8:]}-seat-c"
    assert not profile.exists()
    assert host.db.worldline(worldline_id)["current_tick"] == 44

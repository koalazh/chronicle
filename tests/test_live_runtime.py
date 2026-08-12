from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from chronicle.crisis_runtime import (
    CrisisRunConflict,
    CrisisRunEngine,
    FixtureActorDriver,
    RunMode,
)
from chronicle.gateway import GatewayController, GatewayRuntimeError
from chronicle.live_runtime import LiveRuntimeManager


class FakeGatewayController:
    def __init__(self, *, error: str = ""):
        self.error = error
        self.ensured: list[tuple[str, str]] = []
        self.stopped: list[tuple[str, str]] = []

    def ensure(self, run_id: str, runtime_epoch: str) -> dict[str, str]:
        self.ensured.append((run_id, runtime_epoch))
        if self.error:
            raise GatewayRuntimeError(self.error)
        return {"run_id": run_id}

    def stop(self, run_id: str, runtime_epoch: str) -> None:
        self.stopped.append((run_id, runtime_epoch))
        if self.error:
            raise GatewayRuntimeError(self.error)


def _runtime(config, controller):
    return LiveRuntimeManager(
        config,
        controller=controller,
        engine_factory=lambda active: CrisisRunEngine(active, actor_driver=FixtureActorDriver()),
    )


def _install_fake_profiles(monkeypatch):
    records_by_run: dict[str, dict[str, dict[str, str]]] = {}

    def materialize(_config, run_id, actors, **_identity):
        records = records_by_run.setdefault(
            run_id,
            {
                actor["id"]: {
                    "profile": actor["profile"],
                    "profile_key": f"profile-key-{actor['id']}",
                    "world_token": f"world-token-{actor['id']}-{run_id}",
                    "ownership_marker": actor["ownership_marker"],
                    "world_server_name": actor["world_server_name"],
                }
                for actor in actors
            },
        )
        return records

    def load(_config, run_id, _actors, **_identity):
        return records_by_run[run_id]

    monkeypatch.setattr("chronicle.live_runtime.materialize_crisis_profiles", materialize)
    monkeypatch.setattr("chronicle.live_runtime.load_crisis_profile_records", load)
    return records_by_run


def test_live_runtime_bootstraps_reconciles_and_seals_without_manual_gateway(
    app_config, tmp_path, monkeypatch
):
    config = replace(app_config, database_path=tmp_path / "live.db")
    _install_fake_profiles(monkeypatch)
    gateway = FakeGatewayController()
    runtime = _runtime(config, gateway)

    ready = runtime.create(RunMode.WATCH)
    run_id = ready["id"]
    engine = CrisisRunEngine(config)

    assert ready["runtime_phase"] == "READY"
    assert gateway.ensured == [(run_id, engine.db.worldline(run_id)["runtime_epoch"])]
    assert len(engine.db.agent_bindings(run_id)) == 3
    orient = [
        wake for wake in engine.db.crisis_wakes(run_id) if wake["wake_type"] == "ORIENT"
    ]
    assert len(orient) == 3
    assert all(wake["status"] == "COMPLETED" for wake in orient)

    restarted = _runtime(config, gateway).reconcile(run_id)

    assert restarted["runtime_phase"] == "READY"
    assert len(engine.db.agent_bindings(run_id)) == 3
    assert len([wake for wake in engine.db.crisis_wakes(run_id) if wake["wake_type"] == "ORIENT"]) == 3

    sealed = runtime.seal(run_id, "test")

    assert sealed["status"] == "SEALED"
    assert sealed["runtime_phase"] == "CLEANUP_PENDING"
    assert not sealed["runtime_error_code"]
    assert {item["status"] for item in engine.db.agent_bindings(run_id)} == {"REVOKED"}
    assert gateway.stopped == [(run_id, engine.db.worldline(run_id)["runtime_epoch"])]

    assert _runtime(config, gateway).reconcile_active() is None
    assert gateway.stopped == [(run_id, engine.db.worldline(run_id)["runtime_epoch"])]


def test_live_runtime_retries_the_same_bootstrap_run_after_gateway_failure(
    app_config, tmp_path, monkeypatch
):
    config = replace(app_config, database_path=tmp_path / "retry.db")
    _install_fake_profiles(monkeypatch)
    gateway = FakeGatewayController(error="runtime_port_occupied")
    runtime = _runtime(config, gateway)

    failed = runtime.create(RunMode.TAKEOVER)
    run_id = failed["id"]

    assert failed["runtime_phase"] == "FAILED"
    assert failed["runtime_error_code"] == "runtime_port_occupied"
    assert CrisisRunEngine(config).db.crisis_wakes(run_id) == []

    gateway.error = ""
    recovered = runtime.retry(run_id)
    engine = CrisisRunEngine(config)

    assert recovered["id"] == run_id
    assert recovered["runtime_phase"] == "READY"
    assert len(engine.db.agent_bindings(run_id)) == 2
    assert len([wake for wake in engine.db.crisis_wakes(run_id) if wake["wake_type"] == "ORIENT"]) == 2


@pytest.mark.parametrize("human_actor_id", ["li-zicheng", "wu-sangui", "dorgon"])
def test_live_runtime_materializes_every_agent_except_the_selected_human(
    app_config, tmp_path, monkeypatch, human_actor_id
):
    config = replace(app_config, database_path=tmp_path / f"{human_actor_id}-takeover.db")
    records = _install_fake_profiles(monkeypatch)
    runtime = _runtime(config, FakeGatewayController())

    ready = runtime.create(RunMode.TAKEOVER, human_actor_id=human_actor_id)
    engine = CrisisRunEngine(config)

    expected_agents = {"li-zicheng", "wu-sangui", "dorgon"} - {human_actor_id}
    assert ready["human_actor"] == human_actor_id
    assert {binding["role"] for binding in engine.db.agent_bindings(ready["id"])} == expected_agents
    assert set(records[ready["id"]]) == expected_agents
    assert engine.db.worldline_lifetime(ready["id"], human_actor_id)["profile_name"] == ""


def test_live_runtime_marks_interrupted_running_wake_unresolved(app_config, tmp_path, monkeypatch):
    config = replace(app_config, database_path=tmp_path / "interrupted.db")
    _install_fake_profiles(monkeypatch)
    gateway = FakeGatewayController()
    runtime = _runtime(config, gateway)
    ready = runtime.create(RunMode.WATCH)
    engine = CrisisRunEngine(config)
    wake = engine.db.create_crisis_wake(
        {
            "worldline_id": ready["id"],
            "actor_id": "li-zicheng",
            "wake_type": "MESSAGE",
            "tick": 1,
            "status": "RUNNING",
            "source": "hermes",
        }
    )

    reconciled = _runtime(config, gateway).reconcile(ready["id"])

    assert reconciled["runtime_phase"] == "FAILED"
    assert reconciled["runtime_error_code"] == "runtime_wake_unresolved"
    assert engine.db.crisis_wake(wake["id"])["status"] == "FAILED"
    assert engine.db.crisis_wake(wake["id"])["error"]["code"] == "runtime_wake_unresolved"

    still_failed = _runtime(config, gateway).retry(ready["id"])
    assert still_failed["runtime_phase"] == "FAILED"
    sealed = _runtime(config, gateway).seal(ready["id"], "test")
    assert sealed["status"] == "SEALED"


def test_live_runtime_reconcile_rejects_binding_token_drift(app_config, tmp_path, monkeypatch):
    config = replace(app_config, database_path=tmp_path / "binding-drift.db")
    _install_fake_profiles(monkeypatch)
    gateway = FakeGatewayController()
    runtime = _runtime(config, gateway)
    ready = runtime.create(RunMode.WATCH)
    engine = CrisisRunEngine(config)
    binding = engine.db.agent_bindings(ready["id"])[0]
    with engine.db.transaction() as connection:
        connection.execute(
            "UPDATE worldline_agent_bindings SET token_hash = ? WHERE id = ?",
            ("tampered", binding["id"]),
        )

    reconciled = _runtime(config, gateway).reconcile(ready["id"])

    assert reconciled["runtime_phase"] == "FAILED"
    assert reconciled["runtime_error_code"] == "runtime_binding_mismatch"


def test_live_takeover_decision_is_rejected_until_runtime_is_ready(
    app_config, tmp_path, monkeypatch
):
    config = replace(app_config, database_path=tmp_path / "decision-lock.db")
    _install_fake_profiles(monkeypatch)
    runtime = _runtime(config, FakeGatewayController())
    ready = runtime.create(RunMode.TAKEOVER)
    engine = CrisisRunEngine(config)

    engine.db.set_crisis_runtime_state(ready["id"], "FAILED", error_code="runtime_wake_failed")

    with pytest.raises(CrisisRunConflict) as error:
        runtime.submit_human_decision(ready["id"], "")

    assert error.value.code == "runtime_not_ready"
    assert error.value.state == "FAILED"
    assert engine.run_summary(ready["id"])["runtime_phase"] == "FAILED"


def test_live_seal_revokes_bindings_in_the_same_commit(app_config, tmp_path, monkeypatch):
    config = replace(app_config, database_path=tmp_path / "atomic-seal.db")
    _install_fake_profiles(monkeypatch)
    runtime = _runtime(config, FakeGatewayController())
    ready = runtime.create(RunMode.WATCH)
    engine = CrisisRunEngine(config)

    def forbidden_separate_revocation(_run_id):
        raise AssertionError("seal must not rely on a second binding transaction")

    monkeypatch.setattr(engine.db, "revoke_agent_bindings", forbidden_separate_revocation)
    sealed = engine.seal(ready["id"], "test")

    assert sealed["status"] == "SEALED"
    assert sealed["runtime_phase"] == "CLEANUP_PENDING"
    assert sealed["runtime_error_code"] == "runtime_cleanup_pending"
    assert {item["status"] for item in engine.db.agent_bindings(ready["id"])} == {"REVOKED"}


def test_sealed_cleanup_retries_before_a_new_run_is_born(app_config, tmp_path, monkeypatch):
    config = replace(app_config, database_path=tmp_path / "cleanup-retry.db")
    _install_fake_profiles(monkeypatch)
    gateway = FakeGatewayController()
    runtime = _runtime(config, gateway)
    first = runtime.create(RunMode.WATCH)

    gateway.error = "runtime_owner_unknown"
    pending = runtime.seal(first["id"], "test")

    assert pending["status"] == "SEALED"
    assert pending["runtime_error_code"] == "runtime_owner_unknown"

    gateway.error = ""
    assert runtime.reconcile_active() is None
    cleaned = CrisisRunEngine(config).run_summary(first["id"])
    second = runtime.create(RunMode.TAKEOVER)

    assert cleaned["runtime_phase"] == "CLEANUP_PENDING"
    assert cleaned["runtime_error_code"] == ""
    assert second["id"] != first["id"]
    assert second["runtime_phase"] == "READY"


def test_gateway_controller_requires_owner_pid_start_time_and_fingerprint(
    app_config, tmp_path, monkeypatch
):
    config = replace(app_config, runtime_dir=tmp_path / ".chronicle", hermes_home=tmp_path / "home")
    config.hermes_home.mkdir(parents=True)
    spawned: list[int] = []

    def spawn(_args, **_kwargs):
        pid = 7123
        spawned.append(pid)
        (config.hermes_home / "gateway.pid").write_text(
            json.dumps(
                {
                    "pid": pid,
                    "kind": "hermes-gateway",
                    "start_time": 17,
                    "hermes_home": str(config.hermes_home.resolve()),
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(pid=pid)

    monkeypatch.setattr(
        "chronicle.gateway.HermesClient",
        lambda _config: SimpleNamespace(get_json=lambda _path: (200, {})),
    )
    controller = GatewayController(config, spawn=spawn, start_timeout=0.1)
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: True)
    monkeypatch.setattr(controller, "_process_start_marker", lambda _pid: "started-17")
    monkeypatch.setattr(controller, "_port_is_occupied", lambda: False)

    owner = controller.ensure("run-owned", "epoch-owned")

    assert spawned == [7123]
    assert owner["pid"] == 7123
    assert owner["process_start_marker"] == "started-17"
    assert "API_SERVER_KEY" not in controller.owner_path.read_text(encoding="utf-8")
    assert controller.ensure("run-owned", "epoch-owned")["pid"] == 7123
    assert spawned == [7123]

    (config.hermes_home / "config.yaml").write_text("mcp_servers: {}\n", encoding="utf-8")
    with pytest.raises(GatewayRuntimeError, match="runtime_config_mismatch"):
        controller.ensure("run-owned", "epoch-owned")


def test_gateway_controller_fails_closed_for_pid_reuse_and_unknown_port(
    app_config, tmp_path, monkeypatch
):
    config = replace(app_config, runtime_dir=tmp_path / ".chronicle", hermes_home=tmp_path / "home")
    config.hermes_home.mkdir(parents=True)
    controller = GatewayController(config)
    controller.owner_path.parent.mkdir(parents=True)
    controller.owner_path.write_text(
        json.dumps(
            {
                "version": 1,
                "root": str(config.root.resolve()),
                "hermes_home": str(config.hermes_home.resolve()),
                "run_id": "run-owned",
                "runtime_epoch": "epoch-owned",
                "pid": 71,
                "gateway_start_time": 17,
                "process_start_marker": "old-start",
                "config_fingerprint": controller.config_fingerprint(),
            }
        ),
        encoding="utf-8",
    )
    (config.hermes_home / "gateway.pid").write_text(
        json.dumps(
            {
                "pid": 71,
                "kind": "hermes-gateway",
                "start_time": 17,
                "hermes_home": str(config.hermes_home.resolve()),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: True)
    monkeypatch.setattr(controller, "_process_start_marker", lambda _pid: "new-start")
    monkeypatch.setattr(controller, "_port_is_occupied", lambda: False)

    with pytest.raises(GatewayRuntimeError, match="runtime_owner_unknown"):
        controller.ensure("run-owned", "epoch-owned")

    monkeypatch.setattr(controller, "_process_alive", lambda _pid: False)
    monkeypatch.setattr(controller, "_gateway_pid_is_live", lambda: False)
    monkeypatch.setattr(controller, "_port_is_occupied", lambda: False)
    controller.stop("run-owned", "epoch-owned")
    assert not controller.owner_path.exists()

    other = GatewayController(replace(config, runtime_dir=tmp_path / ".other"))
    monkeypatch.setattr(other, "_gateway_pid_is_live", lambda: False)
    monkeypatch.setattr(other, "_port_is_occupied", lambda: True)
    with pytest.raises(GatewayRuntimeError, match="runtime_port_occupied"):
        other.ensure("run-any", "epoch-any")


def test_gateway_controller_does_not_kill_a_reused_pid_after_start_failure(
    app_config, tmp_path, monkeypatch
):
    config = replace(
        app_config,
        runtime_dir=tmp_path / ".chronicle",
        hermes_home=tmp_path / "home",
    )
    controller = GatewayController(config, spawn=lambda *_args, **_kwargs: SimpleNamespace(pid=7124))
    monkeypatch.setattr(controller, "_gateway_pid_is_live", lambda: False)
    monkeypatch.setattr(controller, "_port_is_occupied", lambda: False)
    monkeypatch.setattr(controller, "_wait_for_owned_start", lambda *_args: None)
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: True)
    markers = iter(("spawned", "reused"))
    monkeypatch.setattr(controller, "_process_start_marker", lambda _pid: next(markers))
    terminated: list[int] = []
    monkeypatch.setattr(controller, "_terminate", lambda pid: terminated.append(pid))

    with pytest.raises(GatewayRuntimeError, match="runtime_gateway_unavailable"):
        controller.ensure("run-owned", "epoch-owned")

    assert terminated == []


def test_gateway_controller_does_not_stop_a_reused_pid(
    app_config, tmp_path, monkeypatch
):
    config = replace(
        app_config,
        runtime_dir=tmp_path / ".chronicle-stop",
        hermes_home=tmp_path / "home-stop",
    )
    controller = GatewayController(config)
    controller.owner_path.parent.mkdir(parents=True)
    owner = {
        "version": 1,
        "root": str(config.root.resolve()),
        "hermes_home": str(config.hermes_home.resolve()),
        "run_id": "run-owned",
        "runtime_epoch": "epoch-owned",
        "pid": 7125,
        "process_start_marker": "old-start",
    }
    controller.owner_path.write_text(json.dumps(owner), encoding="utf-8")
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: True)
    monkeypatch.setattr(controller, "_process_start_marker", lambda _pid: "new-start")
    terminated: list[int] = []
    monkeypatch.setattr(controller, "_terminate", lambda pid: terminated.append(pid))

    with pytest.raises(GatewayRuntimeError, match="runtime_owner_unknown"):
        controller._stop_verified(owner)

    assert terminated == []


def test_gateway_controller_normalizes_owned_state_after_stop(app_config, tmp_path, monkeypatch):
    config = replace(
        app_config,
        runtime_dir=tmp_path / ".chronicle-state",
        hermes_home=tmp_path / "home-state",
    )
    config.hermes_home.mkdir(parents=True)
    controller = GatewayController(config)
    controller.owner_path.parent.mkdir(parents=True)
    owner = {
        "version": 1,
        "root": str(config.root.resolve()),
        "hermes_home": str(config.hermes_home.resolve()),
        "run_id": "run-owned",
        "runtime_epoch": "epoch-owned",
        "pid": 7126,
        "process_start_marker": "started-17",
    }
    controller.owner_path.write_text(json.dumps(owner), encoding="utf-8")
    (config.hermes_home / "gateway_state.json").write_text(
        json.dumps(
            {
                "kind": "hermes-gateway",
                "hermes_home": str(config.hermes_home.resolve()),
                "pid": 7126,
                "gateway_state": "running",
                "active_agents": 2,
            }
        ),
        encoding="utf-8",
    )
    alive = iter((True, False, False, False))
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: next(alive))
    monkeypatch.setattr(controller, "_process_start_marker", lambda _pid: "started-17")
    monkeypatch.setattr(controller, "_terminate", lambda _pid: None)

    controller._stop_verified(owner)

    state = json.loads((config.hermes_home / "gateway_state.json").read_text(encoding="utf-8"))
    assert state["gateway_state"] == "exited"
    assert state["active_agents"] == 0
    assert state["exit_reason"] == "chronicle_cleanup"


def test_gateway_controller_normalizes_state_when_child_already_exited(
    app_config, tmp_path, monkeypatch
):
    config = replace(
        app_config,
        runtime_dir=tmp_path / ".chronicle-state-exited",
        hermes_home=tmp_path / "home-state-exited",
    )
    config.hermes_home.mkdir(parents=True)
    controller = GatewayController(config)
    controller.owner_path.parent.mkdir(parents=True)
    owner = {
        "version": 1,
        "root": str(config.root.resolve()),
        "hermes_home": str(config.hermes_home.resolve()),
        "run_id": "run-owned",
        "runtime_epoch": "epoch-owned",
        "pid": 7127,
        "process_start_marker": "started-17",
    }
    controller.owner_path.write_text(json.dumps(owner), encoding="utf-8")
    (config.hermes_home / "gateway_state.json").write_text(
        json.dumps(
            {
                "kind": "hermes-gateway",
                "hermes_home": str(config.hermes_home.resolve()),
                "pid": 7127,
                "gateway_state": "running",
                "active_agents": 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(controller, "_process_alive", lambda _pid: False)

    controller._stop_verified(owner)

    state = json.loads((config.hermes_home / "gateway_state.json").read_text(encoding="utf-8"))
    assert state["gateway_state"] == "exited"
    assert state["active_agents"] == 0
    assert state["exit_reason"] == "chronicle_cleanup"

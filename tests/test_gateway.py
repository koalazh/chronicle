from __future__ import annotations

import pytest

from chronicle.gateway import GatewayController, GatewayRuntimeError


def _owner(config, *, root=None, run_id="old-run", runtime_epoch="old-epoch"):
    return {
        "version": 1,
        "root": str(root or config.root),
        "hermes_home": str(config.hermes_home),
        "run_id": run_id,
        "runtime_epoch": runtime_epoch,
        "pid": 123,
        "gateway_start_time": 7,
        "process_start_marker": "started",
        "config_fingerprint": "old-fingerprint",
    }


def test_ensure_restarts_a_verified_project_gateway_after_config_change(app_config, monkeypatch):
    controller = GatewayController(app_config)
    owner = _owner(app_config)
    stopped = []
    started = []

    monkeypatch.setattr(controller, "_read_owner", lambda: owner)
    monkeypatch.setattr(controller, "_process_alive", lambda pid: pid == 123)
    monkeypatch.setattr(controller, "_process_start_marker", lambda pid: "started")
    monkeypatch.setattr(
        controller,
        "_read_gateway_pid",
        lambda: {
            "kind": "hermes-gateway",
            "pid": 123,
            "start_time": 7,
            "hermes_home": str(app_config.hermes_home),
        },
    )
    monkeypatch.setattr(controller, "config_fingerprint", lambda: "new-fingerprint")
    monkeypatch.setattr(controller, "_stop_verified", lambda value: stopped.append(value))
    monkeypatch.setattr(
        controller,
        "_start",
        lambda run_id, runtime_epoch: started.append((run_id, runtime_epoch)) or {"run_id": run_id},
    )

    result = controller.ensure("new-run", "new-epoch")

    assert result == {"run_id": "new-run"}
    assert stopped == [owner]
    assert started == [("new-run", "new-epoch")]


def test_ensure_does_not_restart_a_foreign_gateway(app_config, monkeypatch, tmp_path):
    controller = GatewayController(app_config)
    owner = _owner(app_config, root=tmp_path / "other-project")
    monkeypatch.setattr(controller, "_read_owner", lambda: owner)
    monkeypatch.setattr(controller, "_owner_process_is_live", lambda value: True)
    monkeypatch.setattr(controller, "config_fingerprint", lambda: "new-fingerprint")

    with pytest.raises(GatewayRuntimeError, match="runtime_config_mismatch"):
        controller.ensure("new-run", "new-epoch")

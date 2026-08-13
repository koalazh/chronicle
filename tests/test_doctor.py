from __future__ import annotations

from chronicle.doctor import doctor


def _checks(result: dict) -> dict:
    return {item["name"]: item for item in result["checks"]}


def test_doctor_inspects_the_active_v6_volume(host, app_config):
    created = host.volume_runtime.create()

    result = doctor(app_config)
    checks = _checks(result)

    assert result["config"]["active_volume"] == created["worldline"]["id"]
    assert checks["volume_pack"]["ok"] is True
    assert checks["volume_lifetimes"]["ok"] is True
    assert checks["ledger_snapshot_integrity"]["ok"] is True
    assert checks["memory_lineage"]["ok"] is True
    assert checks["pending_moment_integrity"]["ok"] is True
    assert checks["volume_runtime_phase"]["ok"] is True


def test_doctor_rejects_a_running_wake_in_a_pending_v6_moment(host, app_config):
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    lifetime_id = created["lifetimes"][0]["seat"]
    wake = host.db.create_subject_wake(
        {
            "id": "doctor-pending-wake",
            "worldline_id": worldline_id,
            "lifetime_id": lifetime_id,
            "wake_type": "OBSERVATION",
            "tick": 0,
            "status": "QUEUED",
            "source": "doctor-test",
            "trigger_event_id": "",
        }
    )
    host.volume_runtime.freeze_pending_moment(worldline_id)
    host.db.update_crisis_wake(wake["id"], status="RUNNING")

    checks = _checks(doctor(app_config))

    assert checks["pending_moment_integrity"]["ok"] is False


def test_doctor_rejects_a_snapshot_cursor_drift(host, app_config):
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    snapshot = host.db.worldline_snapshot(worldline_id)
    events = host.db.worldline_events(worldline_id)
    assert snapshot is not None and events
    host.db.append_worldline_snapshot(
        worldline_id,
        snapshot["tick"],
        int(events[-1]["sequence"]) + 1,
        snapshot["projection"],
    )

    checks = _checks(doctor(app_config))

    assert checks["ledger_snapshot_integrity"]["ok"] is False

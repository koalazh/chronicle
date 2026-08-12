from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.db import ChronicleDB
from chronicle.models import Controller, WorldlineKind, WorldlineStatus
from chronicle.runtime import WorldlineConflict, WorldlineRuntime


def _create_volume(db: ChronicleDB) -> str:
    volume_id = "volume-inhabitation"
    db.create_worldline(
        {
            "id": volume_id,
            "scenario_id": "jiashen",
            "kind": WorldlineKind.VOLUME.value,
            "status": WorldlineStatus.ACTIVE.value,
            "current_tick": 100,
            "runtime_epoch": "epoch-inhabitation",
            "volume_id": "jiashen",
            "volume_content_version": 1,
            "volume_content_hash": "volume-hash",
            "worldline_phase": "READY",
            "human_lifetime_id": "",
        }
    )
    for lifetime_id, seat in (("lifetime-wu", "wu-sangui"), ("lifetime-dorgon", "dorgon")):
        db.create_worldline_lifetime(
            {
                "id": lifetime_id,
                "worldline_id": volume_id,
                "seat": seat,
                "controller": Controller.AGENT.value,
                "profile_name": f"chronicle-volume-inhabitation-{lifetime_id}",
                "profile_state": "ACTIVE",
                "genesis_hash": f"genesis-{lifetime_id}",
            }
        )
    return volume_id


def test_inhabit_and_leave_preserve_one_trigger_and_do_not_advance_time(host):
    volume_id = _create_volume(host.db)
    wake = host.db.create_subject_wake(
        {
            "id": "wake-pending-dorgon",
            "worldline_id": volume_id,
            "lifetime_id": "lifetime-dorgon",
            "wake_type": "OBSERVATION",
            "tick": 100,
            "status": "QUEUED",
            "source": "world_event",
            "trigger_event_id": "event-message-arrived",
        }
    )
    runtime = WorldlineRuntime(host)

    inhabited = runtime.inhabit(volume_id, "lifetime-dorgon")
    assert inhabited["worldline"]["human_lifetime_id"] == "lifetime-dorgon"
    assert inhabited["worldline"]["current_tick"] == 100
    assert inhabited["lifetime"]["controller"] == Controller.HUMAN.value
    assert inhabited["lifetime"]["profile_state"] == "DORMANT"
    assert inhabited["handoff_wake_ids"] == [wake["id"]]
    assert inhabited["event"]["event_type"] == "LIFETIME_INHABITED"
    assert host.db.crisis_wake(wake["id"])["status"] == "WAITING_HUMAN"
    assert host.db.crisis_wake(wake["id"])["trigger_event_id"] == "event-message-arrived"

    repeated = runtime.inhabit(volume_id, "lifetime-dorgon")
    assert repeated["idempotent"] is True
    assert repeated["event"] is None
    assert len(host.db.worldline_events(volume_id)) == 1

    with pytest.raises(WorldlineConflict, match="leave it first"):
        runtime.inhabit(volume_id, "lifetime-wu")

    left = runtime.leave(volume_id)
    assert left["worldline"]["human_lifetime_id"] == ""
    assert left["worldline"]["current_tick"] == 100
    assert left["lifetime"]["controller"] == Controller.AGENT.value
    assert left["lifetime"]["profile_state"] == "ACTIVE"
    assert left["handoff_wake_ids"] == [wake["id"]]
    assert left["event"]["event_type"] == "LIFETIME_LEFT"
    assert host.db.crisis_wake(wake["id"])["status"] == "QUEUED"
    assert host.db.crisis_wake(wake["id"])["trigger_event_id"] == "event-message-arrived"
    assert len(host.db.worldline_events(volume_id)) == 2
    assert all(event["event_type"] != "TIME_ADVANCED" for event in host.db.worldline_events(volume_id))

    repeated_leave = runtime.leave(volume_id)
    assert repeated_leave["idempotent"] is True
    assert repeated_leave["event"] is None
    assert len(host.db.worldline_events(volume_id)) == 2


def test_controller_boundary_ablation_preserves_subject_state_and_trigger(host):
    volume_id = _create_volume(host.db)
    wake = host.db.create_subject_wake(
        {
            "id": "wake-ablation-dorgon",
            "worldline_id": volume_id,
            "lifetime_id": "lifetime-dorgon",
            "wake_type": "OBSERVATION",
            "tick": 100,
            "status": "QUEUED",
            "source": "world_event",
            "trigger_event_id": "event-ablation-message",
        }
    )
    plan = [{"version": "plan-1", "objective": "保留关口选择", "steps": ["等待核验"]}]
    beliefs = {"peer": {"assessment": "尚待验证", "confidence": "medium"}}
    commitments = [{"id": "commitment-1", "value": "不先做不可逆决定"}]
    revisits = [{"id": "revisit-1", "reason": "复核来报", "due_tick": 102, "status": "PENDING"}]
    host.db.update_worldline_lifetime(
        volume_id,
        "dorgon",
        plan_json=json.dumps(plan, ensure_ascii=False),
        belief_json=json.dumps(beliefs, ensure_ascii=False),
        commitments_json=json.dumps(commitments, ensure_ascii=False),
        revisits_json=json.dumps(revisits, ensure_ascii=False),
    )
    before = host.db.worldline_lifetime(volume_id, "dorgon")
    before_wake = host.db.crisis_wake(wake["id"])
    assert before is not None and before_wake is not None

    runtime = WorldlineRuntime(host)
    runtime.inhabit(volume_id, "lifetime-dorgon")
    runtime.leave(volume_id)

    after = host.db.worldline_lifetime(volume_id, "dorgon")
    after_wake = host.db.crisis_wake(wake["id"])
    assert after is not None and after_wake is not None
    assert host.db.worldline(volume_id)["current_tick"] == 100
    assert after["plan"] == before["plan"]
    assert after["beliefs"] == before["beliefs"]
    assert after["commitments"] == before["commitments"]
    assert after["revisits"] == before["revisits"]
    assert after_wake["id"] == before_wake["id"]
    assert after_wake["trigger_event_id"] == before_wake["trigger_event_id"]
    assert after_wake["status"] == "QUEUED"
    assert [event["event_type"] for event in host.db.worldline_events(volume_id)] == [
        "LIFETIME_INHABITED",
        "LIFETIME_LEFT",
    ]


def test_inhabitation_endpoints_use_the_same_volume_transition(app_config):
    db = ChronicleDB(app_config.database_path)
    volume_id = _create_volume(db)
    client = TestClient(create_app(app_config))

    inhabited = client.post(
        f"/api/worldlines/{volume_id}/inhabit",
        json={"lifetime_id": "lifetime-wu"},
    )
    assert inhabited.status_code == 200
    assert inhabited.json()["worldline"]["human_lifetime_id"] == "lifetime-wu"

    left = client.post(f"/api/worldlines/{volume_id}/leave")
    assert left.status_code == 200
    assert left.json()["worldline"]["human_lifetime_id"] == ""

    branch = db.create_worldline(
        {
            "id": "legacy-branch-for-inhabit",
            "kind": WorldlineKind.BRANCH.value,
            "status": WorldlineStatus.ACTIVE.value,
            "current_tick": 100,
            "controller_seat": "A",
        }
    )
    assert branch["kind"] == WorldlineKind.BRANCH.value
    rejected = client.post(
        f"/api/worldlines/{branch['id']}/inhabit",
        json={"lifetime_id": "lifetime-wu"},
    )
    assert rejected.status_code == 409

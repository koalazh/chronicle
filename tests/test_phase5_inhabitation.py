from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost
from chronicle.models import Controller
from chronicle.volume_runtime import VolumeRuntimeConflict


def _create_volume(host) -> str:
    return str(host.volume_runtime.create()["worldline"]["id"])


def test_inhabit_and_leave_preserve_one_trigger_and_do_not_advance_time(host):
    volume_id = _create_volume(host)
    baseline_event_count = len(host.db.worldline_events(volume_id))
    wake = host.db.create_subject_wake(
        {
            "id": "wake-pending-dorgon",
            "worldline_id": volume_id,
            "lifetime_id": "dorgon",
            "wake_type": "OBSERVATION",
            "tick": 100,
            "status": "QUEUED",
            "source": "world_event",
            "trigger_event_id": "event-message-arrived",
        }
    )
    runtime = host.volume_runtime

    inhabited = runtime.inhabit(volume_id, "dorgon")
    assert inhabited["worldline"]["human_lifetime_id"] == volume_id + ":lifetime:dorgon"
    assert inhabited["worldline"]["current_tick"] == 0
    assert inhabited["lifetime"]["controller"] == Controller.HUMAN.value
    assert inhabited["lifetime"]["profile_state"] == "DORMANT"
    assert inhabited["handoff_wake_ids"] == [wake["id"]]
    assert inhabited["event"]["event_type"] == "LIFETIME_INHABITED"
    assert host.db.crisis_wake(wake["id"])["status"] == "WAITING_HUMAN"
    assert host.db.crisis_wake(wake["id"])["trigger_event_id"] == "event-message-arrived"

    repeated = runtime.inhabit(volume_id, "dorgon")
    assert repeated["idempotent"] is True
    assert repeated["event"] is None
    assert len(host.db.worldline_events(volume_id)) == baseline_event_count + 1

    with pytest.raises(VolumeRuntimeConflict, match="leave it first"):
        runtime.inhabit(volume_id, "wu-sangui")

    left = runtime.leave(volume_id)
    assert left["worldline"]["human_lifetime_id"] == ""
    assert left["worldline"]["current_tick"] == 0
    assert left["lifetime"]["controller"] == Controller.AGENT.value
    assert left["lifetime"]["profile_state"] == "ACTIVE"
    assert left["handoff_wake_ids"] == [wake["id"]]
    assert left["event"]["event_type"] == "LIFETIME_LEFT"
    assert host.db.crisis_wake(wake["id"])["status"] == "QUEUED"
    assert host.db.crisis_wake(wake["id"])["trigger_event_id"] == "event-message-arrived"
    assert len(host.db.worldline_events(volume_id)) == baseline_event_count + 2
    assert [event["event_type"] for event in host.db.worldline_events(volume_id)][-2:] == [
        "LIFETIME_INHABITED",
        "LIFETIME_LEFT",
    ]
    assert all(event["event_type"] != "TIME_ADVANCED" for event in host.db.worldline_events(volume_id))

    repeated_leave = runtime.leave(volume_id)
    assert repeated_leave["idempotent"] is True
    assert repeated_leave["event"] is None
    assert len(host.db.worldline_events(volume_id)) == baseline_event_count + 2


def test_controller_boundary_ablation_preserves_subject_state_and_trigger(host):
    volume_id = _create_volume(host)
    wake = host.db.create_subject_wake(
        {
            "id": "wake-ablation-dorgon",
            "worldline_id": volume_id,
            "lifetime_id": "dorgon",
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

    runtime = host.volume_runtime
    runtime.inhabit(volume_id, "dorgon")
    runtime.leave(volume_id)

    after = host.db.worldline_lifetime(volume_id, "dorgon")
    after_wake = host.db.crisis_wake(wake["id"])
    assert after is not None and after_wake is not None
    assert host.db.worldline(volume_id)["current_tick"] == 0
    assert after["plan"] == before["plan"]
    assert after["beliefs"] == before["beliefs"]
    assert after["commitments"] == before["commitments"]
    assert after["revisits"] == before["revisits"]
    assert after_wake["id"] == before_wake["id"]
    assert after_wake["trigger_event_id"] == before_wake["trigger_event_id"]
    assert after_wake["status"] == "QUEUED"
    assert [event["event_type"] for event in host.db.worldline_events(volume_id)][-2:] == [
        "LIFETIME_INHABITED",
        "LIFETIME_LEFT",
    ]


def test_inhabitation_endpoints_use_the_same_volume_transition(app_config):
    host = ChronicleHost(app_config)
    volume_id = _create_volume(host)
    client = TestClient(create_app(app_config))

    inhabited = client.post(
        f"/api/worldlines/{volume_id}/inhabit",
        json={"lifetime_id": "wu-sangui"},
    )
    assert inhabited.status_code == 200
    assert inhabited.json()["worldline"]["inhabited_lifetime_id"] == "wu-sangui"

    left = client.post(f"/api/worldlines/{volume_id}/leave")
    assert left.status_code == 200
    assert left.json()["worldline"]["inhabited_lifetime_id"] == ""

    rejected = client.post(
        "/api/worldlines/not-a-volume/inhabit",
        json={"lifetime_id": "wu-sangui"},
    )
    assert rejected.status_code == 404

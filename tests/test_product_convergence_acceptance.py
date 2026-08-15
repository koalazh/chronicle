from __future__ import annotations

import copy
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import chronicle.product_api as product_api
from chronicle.app import create_app
from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntime, VolumeRuntimeConflict


def _draft_response(payload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=200,
        json=lambda: {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                }
            ]
        },
    )


@pytest.mark.skip(reason="历史南京快照投影；当前世界没有南京政治中心实体")
def test_product_read_uses_the_stored_snapshot_without_runtime_replay(app_config, monkeypatch):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        host = ChronicleHost(config)
        snapshot = host.db.worldline_snapshot(worldline_id, 0)
        assert snapshot is not None
        projection = copy.deepcopy(snapshot["projection"])
        projection["entities"]["nanjing-political-center"]["state"] = "FU_RECOGNIZED"
        host.db.append_worldline_snapshot(
            worldline_id,
            0,
            int(snapshot["ledger_cursor"]) + 1,
            projection,
        )

        def fail_if_runtime_replays(*_args, **_kwargs):
            raise AssertionError("Product read must not replay Runtime state")

        monkeypatch.setattr(VolumeRuntime, "worldline", fail_if_runtime_replays)
        world = client.get(f"/api/worldlines/{worldline_id}/world")

    assert world.status_code == 200
    assert world.json()["present_reality"] == [
        {
            "id": "nanjing-political-center",
            "title": "南京政治中心",
            "state": "FU_RECOGNIZED",
            "text": "南京已经形成福王承认的政治中心",
        }
    ]


@pytest.mark.skip(reason="历史全局 field 投影；当前单危机产品没有该历史 field")
def test_world_hides_applied_field_and_silence_instead_of_making_a_fake_fact(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        host = ChronicleHost(config)
        snapshot = host.db.worldline_snapshot(worldline_id, 0)
        assert snapshot is not None
        projection = copy.deepcopy(snapshot["projection"])
        projection["field_events"][0]["status"] = "APPLIED"
        host.db.append_worldline_snapshot(
            worldline_id,
            0,
            int(snapshot["ledger_cursor"]) + 1,
            projection,
        )

        world = client.get(f"/api/worldlines/{worldline_id}/world")

    assert world.status_code == 200
    payload = world.json()
    assert payload["present_reality"] == []
    assert "field_events" not in payload
    assert "messages" not in payload
    assert "north-south-recognition-bridge" not in str(payload)
    assert "north-affairs-public-record" not in str(payload)


def test_drafting_aid_is_read_only_and_rejects_invalid_basis(app_config, monkeypatch):
    config = replace(
        app_config,
        dev=True,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-secret",
        llm_model="draft-model",
    )
    responses = iter(
        [
            _draft_response(
                {
                    "recommendation": "WAIT",
                    "draft": "先等待一条可以核验的消息。",
                    "basis_event_ids": [],
                }
            ),
            _draft_response(
                {
                    "recommendation": "WAIT",
                    "draft": "这份依据并不在当前所知范围。",
                    "basis_event_ids": ["not-visible"],
                }
            ),
        ]
    )
    monkeypatch.setattr("chronicle.product_assist.httpx.post", lambda *_args, **_kwargs: next(responses))

    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        host = ChronicleHost(config)
        before_events = host.db.worldline_events(worldline_id)
        before_lifetime = host.db.worldline_lifetime(worldline_id, "wu-sangui")
        assert before_lifetime is not None

        available = client.post(f"/api/worldlines/{worldline_id}/assist/draft")
        rejected = client.post(f"/api/worldlines/{worldline_id}/assist/draft")
        desk = client.get(f"/api/worldlines/{worldline_id}/desk")

        after_events = host.db.worldline_events(worldline_id)
        after_lifetime = host.db.worldline_lifetime(worldline_id, "wu-sangui")
        assert after_lifetime is not None

    assert available.json() == {
        "available": True,
        "suggestion": {
            "recommendation": "WAIT",
            "draft": "先等待一条可以核验的消息。",
            "basis_event_ids": [],
        },
    }
    assert rejected.json() == {"available": False}
    assert desk.json()["desk"]["current_course"] == []
    assert after_events == before_events
    assert after_lifetime["plan"] == before_lifetime["plan"]
    assert after_lifetime["beliefs"] == before_lifetime["beliefs"]


def test_execution_assist_timeout_still_saves_the_human_judgment(app_config, monkeypatch):
    config = replace(
        app_config,
        dev=True,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-secret",
        llm_model="execution-model",
    )

    def provider_timeout(*_args, **_kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("chronicle.product_assist.httpx.post", provider_timeout)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        host = ChronicleHost(config)
        before_events = host.db.worldline_events(worldline_id)

        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        )
        events = host.db.worldline_events(worldline_id)[len(before_events) :]

    assert decided.status_code == 200
    assert any(event["event_type"] == "DELIBERATION_COMMITTED" for event in events)
    assert not any(event["event_type"] == "MESSAGE_DISPATCHED" for event in events)
    assert decided.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
        "先守住关口"
    )


def test_slow_optional_action_assist_does_not_hold_human_judgment(app_config, monkeypatch):
    config = replace(app_config, dev=True)

    def slow_execution(*_args, **_kwargs):
        time.sleep(0.05)
        return {
            "tool": "communicate",
            "arguments": {
                "recipient": "dorgon",
                "content": "请提交可核验的通行边界。",
            },
        }

    monkeypatch.setattr(product_api, "execution_action_candidate", slow_execution)
    monkeypatch.setattr(
        product_api,
        "HUMAN_ACTION_ASSIST_TIMEOUT_SECONDS",
        0.001,
        raising=False,
    )
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        before_events = ChronicleHost(config).db.worldline_events(worldline_id)

        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        )
        events = ChronicleHost(config).db.worldline_events(worldline_id)[len(before_events) :]

    assert decided.status_code == 200
    assert not any(event["event_type"] == "MESSAGE_DISPATCHED" for event in events)
    assert decided.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
        "先守住关口"
    )


def test_late_action_conflict_does_not_roll_back_the_confirmed_course(monkeypatch, app_config):
    config = replace(app_config, dev=True)
    monkeypatch.setattr(
        product_api,
        "execution_action_candidate",
        lambda *_args: {
            "tool": "communicate",
            "arguments": {
                "recipient": "dorgon",
                "content": "请提交可核验的通行边界。",
            },
        },
    )
    original_stage = VolumeRuntime.stage_deliberation
    conflicts: list[bool] = []

    def fail_once_on_action(self, worldline_id, lifetime_id, proposal, **kwargs):
        if proposal.get("world_actions") and not conflicts:
            conflicts.append(True)
            raise VolumeRuntimeConflict("late action conflict")
        return original_stage(self, worldline_id, lifetime_id, proposal, **kwargs)

    monkeypatch.setattr(VolumeRuntime, "stage_deliberation", fail_once_on_action)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        host = ChronicleHost(config)
        before_events = host.db.worldline_events(worldline_id)
        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，继续等待"},
        )
        events = host.db.worldline_events(worldline_id)[len(before_events) :]

    assert decided.status_code == 200
    assert conflicts == [True]
    assert not any(event["event_type"] == "MESSAGE_DISPATCHED" for event in events)
    assert decided.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
        "先守住关口"
    )


def test_staged_human_judgment_can_be_retried_after_transient_resolution_failure(
    app_config, monkeypatch
):
    config = replace(app_config, dev=True)
    calls = {"count": 0}

    original_commit = VolumeRuntime.commit_pending_moment

    def commit_once(self, worldline_id):
        if calls["count"] == 0:
            calls["count"] += 1
            raise product_api.RetryableVolumeActorDriverError("provider timed out")
        return original_commit(self, worldline_id)

    monkeypatch.setattr(
        VolumeRuntime,
        "commit_pending_moment",
        commit_once,
    )

    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]

        first = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        )
        pending_desk = client.get(f"/api/worldlines/{worldline_id}/desk")
        retried = client.post(f"/api/worldlines/{worldline_id}/decision/retry")

    assert first.status_code == 503
    assert pending_desk.status_code == 200
    assert pending_desk.json()["desk"]["decision_state"] == "AWAITING_CONFIRMATION"
    assert retried.status_code == 200
    assert retried.json()["desk"]["desk"]["decision_state"] == "COURSE_IN_FORCE"


def test_terminal_agent_failure_is_explicit_and_user_retry_resolves_once(
    app_config, monkeypatch
):
    config = replace(app_config, dev=True)
    calls: list[str] = []

    monkeypatch.setattr(
        VolumeRuntime,
        "ensure_live_runtime",
        lambda self, worldline_id: self.db.worldline(worldline_id),
    )

    def fake_run_wake(driver, wake, _perspective):
        calls.append(str(wake["actor_id"]))
        if len(calls) == 1:
            driver.db.update_crisis_wake(
                str(wake["id"]),
                status="FAILED",
                error={
                    "actor_id": str(wake["actor_id"]),
                    "code": "missing_logical_intent",
                },
            )
            raise product_api.VolumeActorDriverError("missing logical intent")
        host = ChronicleHost(config)
        return host.volume_runtime.stage_intent(
            str(wake["worldline_id"]),
            str(wake["actor_id"]),
            {"type": "wait"},
            source="agent",
            wake_id=str(wake["id"]),
        )

    monkeypatch.setattr(
        "chronicle.volume_live.HermesVolumeActorDriver.run_wake", fake_run_wake
    )

    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        host = ChronicleHost(config)
        with host.db.transaction() as connection:
            connection.execute(
                "UPDATE worldlines SET runtime_mode = 'live', runtime_phase = 'READY' WHERE id = ?",
                (worldline_id,),
            )
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        assert client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/leave").status_code == 200
        failed = client.post(f"/api/worldlines/{worldline_id}/continue")
        retried = client.post(f"/api/worldlines/{worldline_id}/continue")

    assert failed.status_code == 200
    assert failed.json()["continue_status"] == "agent_failed"
    assert retried.status_code == 200
    assert retried.json()["continue_status"] != "agent_failed"
    assert calls[:2] == ["dorgon", "dorgon"]


def test_handoff_requeues_the_same_wake_without_creating_another_one(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        pending = client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        host = ChronicleHost(config)
        before = host.db.subject_wakes(worldline_id)

        left = client.post(f"/api/worldlines/{worldline_id}/leave")
        after = host.db.subject_wakes(worldline_id)

    assert left.status_code == 200
    assert {wake["id"] for wake in after} == {wake["id"] for wake in before}
    human_wake = next(wake for wake in after if wake["id"] in pending["wake_ids"] and wake["actor_id"] == "wu-sangui")
    assert human_wake["status"] == "QUEUED"


def test_completed_judgment_then_leave_does_not_create_a_new_wake(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/continue").json()[
            "pending_moment"
        ]
        decided = client.post(
            f"/api/worldlines/{worldline_id}/decision",
            json={"action": "CHANGE", "text": "先守住关口，等待明确回复"},
        )
        assert decided.status_code == 200
        host = ChronicleHost(config)
        before = host.db.subject_wakes(worldline_id)

        left = client.post(f"/api/worldlines/{worldline_id}/leave")
        after = host.db.subject_wakes(worldline_id)

    assert left.status_code == 200
    assert {wake["id"] for wake in after} == {wake["id"] for wake in before}

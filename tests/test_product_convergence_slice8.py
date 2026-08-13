from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

import chronicle.product_api as product_api
from chronicle.app import create_app
from chronicle.config import AppConfig
from chronicle.host import ChronicleHost
from chronicle.product_assist import execution_action_candidate


def _execution_context() -> dict:
    return {
        "worldline_id": "private-worldline",
        "lifetime_id": "wu-sangui",
        "tick": 1,
        "position": {"id": "shanhaiguan", "display_name": "山海关"},
        "role": {"display_name": "吴三桂", "authority": ["communicate"]},
        "affordances": {"operations": [{"tool": "operate", "id": "private-operation"}]},
    }


def test_execution_assist_returns_only_one_action_candidate(monkeypatch, app_config: AppConfig):
    config = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-secret",
        llm_model="execution-model",
    )

    def fake_post(_url, **_kwargs):
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "world_action": {
                                        "tool": "communicate",
                                        "arguments": {
                                            "recipient": "dorgon",
                                            "content": "请提交可核验的通行边界。",
                                        },
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("chronicle.product_assist.httpx.post", fake_post)
    candidate = execution_action_candidate(
        config,
        _execution_context(),
        {"summary": "先守住关口", "steps": ["等待明确回复"]},
    )

    assert candidate == {
        "tool": "communicate",
        "arguments": {
            "recipient": "dorgon",
            "content": "请提交可核验的通行边界。",
        },
    }


def test_host_action_candidate_validation_is_read_only(app_config):
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
        host = ChronicleHost(config)
        pending = host.volume_runtime.worldline(worldline_id)["projection"]["pending_moment"]
        before_events = host.db.worldline_events(worldline_id)
        before_operations = host.db.crisis_wake_operations(pending["wake_ids"][0])

        accepted = host.volume_runtime.validate_world_action_candidate(
            worldline_id,
            "wu-sangui",
            {
                "tool": "communicate",
                "arguments": {
                    "recipient": "dorgon",
                    "content": "请提交可核验的通行边界。",
                },
            },
            wake_id=pending["wake_ids"][0],
        )
        rejected = host.volume_runtime.validate_world_action_candidate(
            worldline_id,
            "wu-sangui",
            {"tool": "communicate", "arguments": {"recipient": "missing", "content": "无效"}},
            wake_id=pending["wake_ids"][0],
        )

        assert accepted is not None
        assert rejected is None
        assert host.db.worldline_events(worldline_id) == before_events
        assert host.db.crisis_wake_operations(pending["wake_ids"][0]) == before_operations


def test_human_judgment_and_execution_action_commit_as_one_moment(monkeypatch, app_config):
    config = replace(app_config, dev=True)
    calls: list[dict] = []

    def fake_execution(_config, context, course):
        calls.append({"context": context, "course": course})
        return {
            "tool": "communicate",
            "arguments": {
                "recipient": "dorgon",
                "content": "请提交可核验的通行边界。",
            },
        }

    monkeypatch.setattr(product_api, "execution_action_candidate", fake_execution)
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

        assert decided.status_code == 200
        assert calls and calls[0]["course"] == {
            "summary": "先守住关口，等待明确回复",
            "steps": ["先守住关口，等待明确回复"],
        }
        host = ChronicleHost(config)
        events = host.db.worldline_events(worldline_id)[len(before_events) :]
        event_types = [event["event_type"] for event in events]
        assert event_types.count("DELIBERATION_COMMITTED") == 1
        assert event_types.count("MESSAGE_DISPATCHED") == 1
        assert event_types.count("MOMENT_COMMITTED") == 1
        assert decided.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
            "先守住关口"
        )


def test_invalid_execution_action_does_not_lose_human_course(monkeypatch, app_config):
    config = replace(app_config, dev=True)
    monkeypatch.setattr(
        product_api,
        "execution_action_candidate",
        lambda *_args: {
            "tool": "communicate",
            "arguments": {"recipient": "missing", "content": "无效动作"},
        },
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
            json={"action": "CHANGE", "text": "先守住关口，继续等待"},
        )

        assert decided.status_code == 200
        host = ChronicleHost(config)
        events = host.db.worldline_events(worldline_id)[len(before_events) :]
        assert not any(event["event_type"] == "MESSAGE_DISPATCHED" for event in events)
        assert decided.json()["desk"]["desk"]["current_course"][0]["text"].startswith(
            "先守住关口"
        )

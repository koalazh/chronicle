from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.product_assist import (
    bounded_draft_context,
    draft_judgment,
    validate_draft_suggestion,
)


def _context() -> dict:
    return {
        "worldline_id": "worldline-secret",
        "lifetime_id": "wu-sangui",
        "seat": "wu-sangui",
        "tick": 4,
        "trigger": {
            "event_id": "event-visible",
            "event_type": "MESSAGE_DELIVERED",
            "payload": {"content": "清方终于给出明确回复。"},
        },
        "current_course": {
            "course": "先守住关口",
            "steps": ["等待明确回复"],
            "open_dependencies": [{"id": "private-dependency"}],
        },
        "position": {"id": "shanhaiguan", "display_name": "山海关"},
        "role": {"display_name": "吴三桂", "authority": ["private-authority"]},
        "why_now": {"facts": [{"event_id": "event-visible", "payload": {"content": "消息已抵达。"}}]},
        "relevant_evidence": [{"event_id": "event-visible", "content": "可核验的公开消息。"}],
        "recent_knowledge": [{"event_id": "event-visible", "content": "已收到。"}],
        "since_last_deliberation": {"facts": [{"content": "这是一项新变化。"}]},
        "known_uncertainty": ["仍有在途消息。"],
        "beliefs": {"private": "不要传给 Assist"},
        "affordances": {"operations": [{"tool": "operate"}]},
        "active_crisis_context": [{"private": "不要传给 Assist"}],
    }


def test_draft_context_is_bounded_to_the_frozen_subject_view():
    bounded, visible_ids = bounded_draft_context(_context(), "REOPEN")

    assert visible_ids == {"event-visible"}
    assert bounded["stage"] == "REOPEN"
    assert bounded["current_course"] == {
        "summary": "先守住关口",
        "steps": ["等待明确回复"],
    }
    assert "worldline_id" not in bounded
    assert "lifetime_id" not in bounded
    assert "beliefs" not in bounded
    assert "affordances" not in bounded
    assert "active_crisis_context" not in bounded


def test_draft_suggestion_rejects_wrong_stage_unknown_evidence_and_internal_copy():
    assert validate_draft_suggestion(
        {"recommendation": "KEEP", "draft": "维持原来的方向", "basis_event_ids": []},
        stage="FIRST",
        visible_event_ids={"event-visible"},
    ) is None
    assert validate_draft_suggestion(
        {"recommendation": "CHANGE", "draft": "换个方向", "basis_event_ids": ["hidden"]},
        stage="REOPEN",
        visible_event_ids={"event-visible"},
    ) is None
    assert validate_draft_suggestion(
        {"recommendation": "CHANGE", "draft": "调用 arrange_fu_entry", "basis_event_ids": []},
        stage="FIRST",
        visible_event_ids={"event-visible"},
    ) is None


def test_drafting_aid_reuses_configured_http_provider_without_session(monkeypatch, app_config):
    config = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-secret",
        llm_model="draft-model",
    )
    request: dict[str, object] = {}

    def fake_post(url, **kwargs):
        request.update({"url": url, **kwargs})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "recommendation": "CHANGE",
                                    "draft": "先守住关口，在消息进一步明确前不作不可逆承认。",
                                    "basis_event_ids": ["event-visible"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("chronicle.product_assist.httpx.post", fake_post)
    suggestion = draft_judgment(config, _context(), "REOPEN")

    assert suggestion == {
        "recommendation": "CHANGE",
        "draft": "先守住关口，在消息进一步明确前不作不可逆承认。",
        "basis_event_ids": ["event-visible"],
    }
    assert request["url"] == "https://provider.example/v1/chat/completions"
    assert request["trust_env"] is False
    assert "X-Hermes-Session-Id" not in request["headers"]
    assert "worldline-secret" not in request["json"]["messages"][1]["content"]


def test_product_assist_is_optional_and_does_not_change_runtime_state(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        assert client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        ).status_code == 200
        assert client.post(f"/api/worldlines/{worldline_id}/reconsider").status_code == 200

        unavailable = client.post(f"/api/worldlines/{worldline_id}/assist/draft")

        assert unavailable.status_code == 200
        assert unavailable.json() == {"available": False}

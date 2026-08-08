from __future__ import annotations

import pytest

from chronicle.hermes import actor_protocol_prompt, parse_actor_response, wake_messages


def test_actor_response_accepts_fenced_json():
    response = parse_actor_response(
        """```json
        {"assessment":"partial report","belief_updates":[],"intentions":[],"uncertainties":[],"memory_action":"NO_CHANGE","memory_text":""}
        ```"""
    )
    assert response.assessment == "partial report"
    assert response.memory_action == "NO_CHANGE"


def test_actor_response_rejects_non_protocol_text():
    with pytest.raises(ValueError, match="not valid Chronicle JSON"):
        parse_actor_response("I know the outcome.")


def test_wake_prompt_contains_protocol_without_world_names():
    prompt = actor_protocol_prompt()
    messages = wake_messages(
        {
            "seat": "Seat A",
            "tick": 4,
            "observations": [{"id": "o1", "payload": "A partial report."}],
            "current_beliefs": {},
            "subjective_memory": "",
            "allowed_intents": ["WAIT"],
        },
        "observation",
    )
    assert "omniscient" in prompt
    assert "崇祯" not in messages[-1]["content"]
    assert "capital" not in messages[-1]["content"]

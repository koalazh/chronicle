from __future__ import annotations

from pathlib import Path

import pytest

from chronicle.config import OPENAI_CODEX_BASE_URL, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_config_supports_api_key_and_oauth_modes():
    api_key = load_config(
        PROJECT_ROOT,
        environ={
            "CHRONICLE_LLM_AUTH_MODE": "api_key",
            "CHRONICLE_LLM_BASE_URL": "https://provider.example/v1",
            "CHRONICLE_LLM_API_KEY": "secret",
            "CHRONICLE_LLM_MODEL": "model-a",
        },
    )
    assert api_key.llm_provider == "chronicle-openai"
    assert api_key.llm_configured is True
    assert api_key.llm_api_mode == "chat_completions"

    oauth = load_config(
        PROJECT_ROOT,
        environ={
            "CHRONICLE_LLM_AUTH_MODE": "oauth",
            "CHRONICLE_LLM_BASE_URL": "https://ignored.example/v1",
            "CHRONICLE_LLM_API_KEY": "stale-key-must-not-be-used",
            "CHRONICLE_LLM_MODEL": "gpt-5.6-luna",
            "CHRONICLE_LLM_API_MODE": "chat_completions",
        },
    )
    assert oauth.llm_provider == "openai-codex"
    assert oauth.llm_configured is True
    assert oauth.llm_base_url == OPENAI_CODEX_BASE_URL
    assert oauth.llm_api_key == ""
    assert oauth.llm_api_mode == "responses"


def test_load_config_rejects_unknown_auth_mode():
    with pytest.raises(ValueError, match="CHRONICLE_LLM_AUTH_MODE"):
        load_config(PROJECT_ROOT, environ={"CHRONICLE_LLM_AUTH_MODE": "magic"})

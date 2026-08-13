from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from chronicle.config import OPENAI_CODEX_BASE_URL
from chronicle.hermes import (
    _python_executable,
    _sync_profile_config,
    _sync_profile_env,
    _write_gateway_env,
)
from chronicle.world_mcp import mcp


def test_actor_distribution_declines_recent_builtin_toolset():
    root = Path(__file__).parents[1]
    config = yaml.safe_load(
        (root / "hermes" / "chronicle-actor" / "config.yaml").read_text(encoding="utf-8")
    )

    assert config["platform_toolsets"]["api_server"] == ["memory"]
    assert config["known_builtin_toolsets"]["api_server"] == ["bfl"]


def test_private_gateway_uses_the_configured_base_url_port(app_config):
    config = replace(app_config, hermes_base_url="http://127.0.0.1:18642")
    config.hermes_home.mkdir()

    _write_gateway_env(config, "gateway-key")

    values = dict(
        line.split("=", 1)
        for line in (config.hermes_home / ".env").read_text(encoding="utf-8").splitlines()
    )
    assert values["API_SERVER_HOST"] == "127.0.0.1"
    assert values["API_SERVER_PORT"] == "18642"


def test_mcp_commands_use_canonical_interpreter_path(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    target = tmp_path / "python-real"
    target.touch()
    canonical = bin_dir / "python"
    canonical.symlink_to(target)
    alias = bin_dir / "python3"
    alias.symlink_to(target)
    monkeypatch.setattr(sys, "executable", str(alias))

    assert _python_executable() == str(canonical)


def test_oauth_profile_config_uses_codex_provider_without_api_key(app_config):
    profile_home = app_config.hermes_home / "profiles" / "oauth-profile"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text("{}\n", encoding="utf-8")
    oauth_config = replace(
        app_config,
        llm_auth_mode="oauth",
        llm_base_url=OPENAI_CODEX_BASE_URL,
        llm_api_key="",
        llm_model="gpt-5.6-luna",
        llm_api_mode="responses",
    )

    _sync_profile_env(profile_home, "profile-key", oauth_config)
    _sync_profile_config(
        profile_home,
        oauth_config,
        Path(__file__).parents[1] / "hermes" / "chronicle-actor" / "config.yaml",
    )

    profile = yaml.safe_load((profile_home / "config.yaml").read_text(encoding="utf-8"))
    assert profile["model"]["provider"] == "openai-codex"
    assert profile["providers"] == {
        "openai-codex": {
            "base_url": OPENAI_CODEX_BASE_URL,
            "model": "gpt-5.6-luna",
            "api_mode": "codex_responses",
        }
    }
    profile_env = (profile_home / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" not in profile_env
    assert "CHRONICLE_LLM_API_KEY=" not in profile_env


@pytest.mark.asyncio
async def test_world_mcp_exposes_identity_free_v6_tools():
    tools = {tool.name: tool.inputSchema for tool in await mcp.list_tools()}

    assert set(tools) == {
        "communicate",
        "commit_deliberation",
        "investigate",
        "logical_intent",
        "manage_offer",
        "operate",
        "update_plan",
        "schedule_revisit",
    }
    for schema in tools.values():
        assert not {"actor_id", "profile", "run_id"}.intersection(
            schema.get("properties", {})
        )
        assert "wake_id" in schema.get("properties", {})

    assert "anyOf" in tools["communicate"]["properties"]["recipient"]
    assert "anyOf" in tools["investigate"]["properties"]["target"]
    assert "anyOf" in tools["operate"]["properties"]["targets"]["items"]
    assert "anyOf" in tools["manage_offer"]["properties"]["recipient"]
    assert "anyOf" in tools["update_plan"]["properties"]["belief_updates"]["anyOf"][0]["items"]
    assert set(tools["logical_intent"]["required"]) == {"intent", "idempotency_key"}
    assert set(tools["commit_deliberation"]["required"]) == {"outcome", "idempotency_key"}

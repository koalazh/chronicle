from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from chronicle.db import content_hash
from chronicle.hermes import (
    _write_gateway_env,
    actor_protocol_prompt,
    cleanup_crisis_runtime,
    load_crisis_profile_records,
    materialize_crisis_profiles,
    parse_actor_response,
    remove_crisis_profiles,
    wake_messages,
)
from chronicle.world_mcp import mcp


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


def test_actor_distribution_declines_recent_builtin_toolset():
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "hermes" / "chronicle-actor" / "config.yaml").read_text(encoding="utf-8"))

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


@pytest.mark.asyncio
async def test_world_mcp_exposes_only_identity_free_crisis_tools():
    tools = {tool.name: tool.inputSchema for tool in await mcp.list_tools()}

    assert set(tools) == {
        "communicate",
        "investigate",
        "manage_offer",
        "operate",
        "update_plan",
        "schedule_revisit",
    }
    for schema in tools.values():
        assert not {"actor_id", "profile", "run_id", "wake_id"}.intersection(
            schema.get("properties", {})
        )

    assert "anyOf" in tools["communicate"]["properties"]["recipient"]
    assert "anyOf" in tools["investigate"]["properties"]["target"]
    assert "anyOf" in tools["operate"]["properties"]["targets"]["items"]
    assert "anyOf" in tools["manage_offer"]["properties"]["recipient"]
    assert "anyOf" in tools["update_plan"]["properties"]["belief_updates"]["anyOf"][0]["items"]


def test_eager_crisis_profiles_are_owned_and_world_tool_only(
    app_config, monkeypatch
):
    app_config.hermes_home.mkdir(parents=True)
    (app_config.hermes_home / ".env").write_text(
        "API_SERVER_KEY=stable-gateway-key\n", encoding="utf-8"
    )

    def fake_install(config, args, timeout=30):
        profile = args[args.index("--name") + 1]
        shutil.copytree(
            config.root / "hermes" / "chronicle-actor",
            config.hermes_home / "profiles" / profile,
        )
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("chronicle.hermes._run_cli", fake_install)
    records = materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [
            {
                "id": "li-zicheng",
                "role_charter": {
                    "who": "危局中的李自成",
                    "responsibility": ["维持秩序"],
                    "authority": ["作出有限行动"],
                    "tensions": ["等待与行动"],
                },
                "genesis_hash": "genesis-hash-test",
                "initial_memory_snapshot": {
                    "memory_text": "",
                    "memory_hash": content_hash(""),
                },
            }
        ],
        crisis_id="before-shanhaiguan",
        runtime_epoch="hermes-epoch-test",
    )
    record = records["li-zicheng"]
    profile_home = app_config.hermes_home / "profiles" / record["profile"]
    config = yaml.safe_load((profile_home / "config.yaml").read_text(encoding="utf-8"))
    marker = json.loads((profile_home / "chronicle-genesis.json").read_text(encoding="utf-8"))
    profile_env = (profile_home / ".env").read_text(encoding="utf-8")
    gateway_env = (app_config.hermes_home / ".env").read_text(encoding="utf-8")

    world_server = record["world_server_name"]
    assert config["platform_toolsets"]["api_server"] == ["memory", world_server]
    assert config["agent"]["max_turns"] == 8
    assert set(config["mcp_servers"]) == {world_server}
    assert config["mcp_servers"][world_server]["env"]["CHRONICLE_WORLD_TOKEN"] == "${CHRONICLE_WORLD_TOKEN}"
    assert marker["worldline_id"] == "run-12345678abcdefgh"
    assert "API_SERVER_KEY=stable-gateway-key" in gateway_env
    assert marker["crisis_id"] == "before-shanhaiguan"
    assert marker["genesis_hash"] == "genesis-hash-test"
    assert marker["initial_memory_snapshot"]["memory_hash"] == content_hash("")
    assert marker["runtime_epoch"] == "hermes-epoch-test"
    assert record["world_token"] not in json.dumps(marker)
    assert f"CHRONICLE_WORLD_TOKEN={record['world_token']}" in profile_env
    assert "危局中的李自成" in (profile_home / "SOUL.md").read_text(encoding="utf-8")
    gateway_config = yaml.safe_load(
        (app_config.hermes_home / "config.yaml").read_text(encoding="utf-8")
    )
    assert set(gateway_config["mcp_servers"]) == {world_server}
    assert record["world_token"] not in json.dumps(gateway_config)
    assert record["world_token"] in (app_config.hermes_home / ".env").read_text(
        encoding="utf-8"
    )

    marker["genesis_hash"] = "mismatched-genesis"
    (profile_home / "chronicle-genesis.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="does not belong"):
        materialize_crisis_profiles(
            app_config,
            "run-12345678abcdefgh",
            [
                {
                    "id": "li-zicheng",
                    "role_charter": {
                        "who": "危局中的李自成",
                        "responsibility": ["维持秩序"],
                        "authority": ["作出有限行动"],
                        "tensions": ["等待与行动"],
                    },
                    "genesis_hash": "genesis-hash-test",
                    "initial_memory_snapshot": {
                        "memory_text": "",
                        "memory_hash": content_hash(""),
                    },
                }
            ],
            crisis_id="before-shanhaiguan",
            runtime_epoch="hermes-epoch-test",
        )

    remove_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [record["profile"]],
    )
    assert not profile_home.exists()


def test_crisis_profile_materialization_is_idempotent_and_replaces_the_root_allowlist(
    app_config, monkeypatch
):
    app_config.hermes_home.mkdir(parents=True)
    installs: list[str] = []

    def fake_install(config, args, timeout=30):
        profile = args[args.index("--name") + 1]
        installs.append(profile)
        shutil.copytree(
            config.root / "hermes" / "chronicle-actor",
            config.hermes_home / "profiles" / profile,
        )
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("chronicle.hermes._run_cli", fake_install)

    def actor() -> dict[str, object]:
        return {
            "id": "li-zicheng",
            "role_charter": {
                "who": "危局中的李自成",
                "responsibility": ["维持秩序"],
                "authority": ["作出有限行动"],
                "tensions": ["等待与行动"],
            },
            "genesis_hash": "genesis-hash-test",
            "initial_memory_snapshot": {
                "memory_text": "",
                "memory_hash": content_hash(""),
            },
        }

    first = materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )["li-zicheng"]
    repeated = materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )["li-zicheng"]

    assert installs == [first["profile"]]
    assert repeated["profile"] == first["profile"]
    assert repeated["world_token"] == first["world_token"]

    (app_config.hermes_home / "profiles" / first["profile"] / "chronicle-genesis.json").unlink()
    pending = app_config.runtime_dir / "profile-pending" / f"{first['profile']}.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps(
            {
                "profile": first["profile"],
                "actor_id": "li-zicheng",
                "run_id": "run-12345678abcdefgh",
                "crisis_id": "before-shanhaiguan",
                "runtime_epoch": "epoch-first",
                "ownership_marker": first["ownership_marker"],
            }
        ),
        encoding="utf-8",
    )
    recovered = materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )["li-zicheng"]
    assert installs == [first["profile"], first["profile"]]
    assert recovered["profile"] == first["profile"]
    assert (app_config.hermes_home / "profiles" / first["profile"] / "chronicle-genesis.json").exists()

    gateway_path = app_config.hermes_home / "config.yaml"
    gateway_values = yaml.safe_load(gateway_path.read_text(encoding="utf-8"))
    gateway_values["mcp_servers"] = {}
    gateway_path.write_text(yaml.safe_dump(gateway_values), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Gateway MCP allowlist"):
        load_crisis_profile_records(
            app_config,
            "run-12345678abcdefgh",
            [actor()],
            crisis_id="before-shanhaiguan",
            runtime_epoch="epoch-first",
        )
    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )

    profile_config_path = app_config.hermes_home / "profiles" / first["profile"] / "config.yaml"
    profile_values = yaml.safe_load(profile_config_path.read_text(encoding="utf-8"))
    profile_values["mcp_servers"] = {}
    profile_config_path.write_text(yaml.safe_dump(profile_values), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete Profile tool configuration"):
        load_crisis_profile_records(
            app_config,
            "run-12345678abcdefgh",
            [actor()],
            crisis_id="before-shanhaiguan",
            runtime_epoch="epoch-first",
        )
    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )

    profile_values = yaml.safe_load(profile_config_path.read_text(encoding="utf-8"))
    profile_values["mcp_servers"][first["world_server_name"]]["command"] = "/tmp/UNKNOWN"
    profile_config_path.write_text(yaml.safe_dump(profile_values), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete Profile tool configuration"):
        load_crisis_profile_records(
            app_config,
            "run-12345678abcdefgh",
            [actor()],
            crisis_id="before-shanhaiguan",
            runtime_epoch="epoch-first",
        )
    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )

    profile_env_path = app_config.hermes_home / "profiles" / first["profile"] / ".env"
    profile_env = profile_env_path.read_text(encoding="utf-8").replace(
        f"CHRONICLE_DATABASE_URL=sqlite:///{app_config.database_path}",
        "CHRONICLE_DATABASE_URL=sqlite:///WRONG",
    )
    profile_env_path.write_text(profile_env, encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete Profile tool configuration"):
        load_crisis_profile_records(
            app_config,
            "run-12345678abcdefgh",
            [actor()],
            crisis_id="before-shanhaiguan",
            runtime_epoch="epoch-first",
        )
    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )

    second = materialize_crisis_profiles(
        app_config,
        "run-87654321ijklmnop",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-second",
    )["li-zicheng"]
    gateway_config = yaml.safe_load(
        (app_config.hermes_home / "config.yaml").read_text(encoding="utf-8")
    )
    gateway_env = (app_config.hermes_home / ".env").read_text(encoding="utf-8")

    assert set(gateway_config["mcp_servers"]) == {second["world_server_name"]}
    assert first["world_token"] not in gateway_env
    assert second["world_token"] in gateway_env
    assert (app_config.hermes_home / "profiles" / first["profile"]).exists()

    cleanup_crisis_runtime(
        app_config,
        "run-87654321ijklmnop",
        [second["profile"]],
    )

    assert not (app_config.hermes_home / "profiles" / second["profile"]).exists()
    assert (app_config.hermes_home / "profiles" / first["profile"]).exists()
    assert yaml.safe_load((app_config.hermes_home / "config.yaml").read_text(encoding="utf-8"))["mcp_servers"] == {}

    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )
    marker_path = app_config.hermes_home / "profiles" / first["profile"] / "chronicle-genesis.json"
    marker_path.unlink()
    pending_path = app_config.runtime_dir / "profile-pending" / f"{first['profile']}.json"
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(
        json.dumps(
            {
                "profile": first["profile"],
                "actor_id": "li-zicheng",
                "run_id": "run-12345678abcdefgh",
                "ownership_marker": first["ownership_marker"],
            }
        ),
        encoding="utf-8",
    )
    cleanup_crisis_runtime(
        app_config,
        "run-12345678abcdefgh",
        [first["profile"]],
        server_names=[first["world_server_name"]],
    )
    assert not (app_config.hermes_home / "profiles" / first["profile"]).exists()

    materialize_crisis_profiles(
        app_config,
        "run-12345678abcdefgh",
        [actor()],
        crisis_id="before-shanhaiguan",
        runtime_epoch="epoch-first",
    )
    shutil.rmtree(app_config.hermes_home / "profiles" / first["profile"])
    cleanup_crisis_runtime(
        app_config,
        "run-12345678abcdefgh",
        [first["profile"]],
        server_names=[first["world_server_name"]],
    )
    cleaned_config = yaml.safe_load(
        (app_config.hermes_home / "config.yaml").read_text(encoding="utf-8")
    )
    assert cleaned_config["mcp_servers"] == {}
    assert first["world_token"] not in (app_config.hermes_home / ".env").read_text(
        encoding="utf-8"
    )

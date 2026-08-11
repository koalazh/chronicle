from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import pytest
import yaml

from chronicle.db import content_hash
from chronicle.hermes import (
    cleanup_volume_runtime,
    lifetime_profile_name,
    load_lifetime_profile_records,
    materialize_lifetime_profiles,
)


def _lifetime(lifetime_id: str, controller: str, display_name: str) -> dict[str, object]:
    return {
        "id": lifetime_id,
        "seat": lifetime_id,
        "controller": controller,
        "display_name": display_name,
        "genesis_context": {"origin": f"{display_name}的持久人生"},
        "stable_authority": ["communicate"],
        "genesis_hash": f"genesis-{lifetime_id}",
        "profile_state": "DORMANT" if controller == "HUMAN" else "ACTIVE",
        "initial_memory_snapshot": {
            "memory_text": "",
            "memory_hash": content_hash(""),
        },
    }


def test_v5_materializes_every_lifetime_without_orient_or_crisis_soul(
    app_config, monkeypatch
):
    app_config.hermes_home.mkdir(parents=True)
    (app_config.hermes_home / ".env").write_text(
        "API_SERVER_KEY=stable-gateway-key\nKEEP_ME=yes\n", encoding="utf-8"
    )
    (app_config.hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "mcp_servers": {
                    "chronicle-world-v4": {"owned_by": "legacy-crisis"},
                    "unrelated-server": {"owned_by": "other"},
                }
            }
        ),
        encoding="utf-8",
    )
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
    lifetimes = [
        _lifetime("human-life", "HUMAN", "Human Life"),
        _lifetime("agent-life", "AGENT", "Agent Life"),
    ]

    records = materialize_lifetime_profiles(
        app_config,
        "volume-jiashen",
        lifetimes,
        volume_id="jiashen",
        content_version=3,
        content_hash="content-hash-v5",
        runtime_epoch="epoch-v5",
    )

    assert set(installs) == {
        lifetime_profile_name("volume-jiashen", "human-life"),
        lifetime_profile_name("volume-jiashen", "agent-life"),
    }
    assert records["human-life"]["profile_state"] == "DORMANT"
    assert records["human-life"]["controller"] == "HUMAN"
    assert records["agent-life"]["profile_state"] == "ACTIVE"

    for lifetime in lifetimes:
        lifetime_id = str(lifetime["id"])
        record = records[lifetime_id]
        profile_home = app_config.hermes_home / "profiles" / record["profile"]
        marker = json.loads((profile_home / "chronicle-genesis.json").read_text(encoding="utf-8"))
        soul = (profile_home / "SOUL.md").read_text(encoding="utf-8")

        assert marker == {
            "profile_scope": "LIFETIME",
            "profile": record["profile"],
            "worldline_id": "volume-jiashen",
            "volume_id": "jiashen",
            "volume_content_version": 3,
            "volume_content_hash": "content-hash-v5",
            "lifetime_id": lifetime_id,
            "genesis_hash": lifetime["genesis_hash"],
            "runtime_epoch": "epoch-v5",
            "ownership_marker": record["ownership_marker"],
            "distribution": "chronicle-actor",
            "toolsets": ["memory", record["world_server_name"]],
        }
        assert "crisis_id" not in marker
        assert "## Persistent Lifetime Genesis" in soul
        assert "本次危局角色章程" not in soul

    human_profile = app_config.hermes_home / "profiles" / records["human-life"]["profile"]
    soul_path = human_profile / "SOUL.md"
    soul_path.write_text(soul_path.read_text(encoding="utf-8") + "\nCustom continuity.\n", encoding="utf-8")
    repeated = materialize_lifetime_profiles(
        app_config,
        "volume-jiashen",
        lifetimes,
        volume_id="jiashen",
        content_version=3,
        content_hash="content-hash-v5",
        runtime_epoch="epoch-v5",
    )
    assert installs == [
        lifetime_profile_name("volume-jiashen", "human-life"),
        lifetime_profile_name("volume-jiashen", "agent-life"),
    ]
    assert repeated["human-life"]["profile_key"] == records["human-life"]["profile_key"]
    assert "Custom continuity." in soul_path.read_text(encoding="utf-8")

    loaded = load_lifetime_profile_records(
        app_config,
        "volume-jiashen",
        lifetimes,
        volume_id="jiashen",
        content_version=3,
        content_hash="content-hash-v5",
        runtime_epoch="epoch-v5",
    )
    assert set(loaded) == set(records)
    assert all(
        (app_config.hermes_home / "profiles" / record["profile"]).exists()
        for record in records.values()
    )

    gateway_path = app_config.hermes_home / "config.yaml"
    gateway_values = yaml.safe_load(gateway_path.read_text(encoding="utf-8"))
    gateway_values["mcp_servers"].pop(records["agent-life"]["world_server_name"])
    gateway_path.write_text(yaml.safe_dump(gateway_values), encoding="utf-8")
    with pytest.raises(RuntimeError, match="allowlist"):
        load_lifetime_profile_records(
            app_config,
            "volume-jiashen",
            lifetimes,
            volume_id="jiashen",
            content_version=3,
            content_hash="content-hash-v5",
            runtime_epoch="epoch-v5",
        )
    materialize_lifetime_profiles(
        app_config,
        "volume-jiashen",
        lifetimes,
        volume_id="jiashen",
        content_version=3,
        content_hash="content-hash-v5",
        runtime_epoch="epoch-v5",
    )

    marker_path = human_profile / "chronicle-genesis.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["worldline_id"] = "other-volume"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not belong"):
        materialize_lifetime_profiles(
            app_config,
            "volume-jiashen",
            lifetimes,
            volume_id="jiashen",
            content_version=3,
            content_hash="content-hash-v5",
            runtime_epoch="epoch-v5",
        )
    marker["worldline_id"] = "volume-jiashen"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    cleanup_volume_runtime(
        app_config,
        "volume-jiashen",
        [record["profile"] for record in records.values()],
    )
    assert not any(
        (app_config.hermes_home / "profiles" / record["profile"]).exists()
        for record in records.values()
    )
    gateway = yaml.safe_load((app_config.hermes_home / "config.yaml").read_text(encoding="utf-8"))
    assert set(gateway["mcp_servers"]) == {"chronicle-world-v4", "unrelated-server"}
    gateway_env = (app_config.hermes_home / ".env").read_text(encoding="utf-8")
    assert "KEEP_ME=yes" in gateway_env
    assert all(record["world_token"] not in gateway_env for record in records.values())

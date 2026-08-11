from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from chronicle.host import ChronicleHost
from chronicle.volume_live import HermesVolumeActorDriver, VolumeActorDriverError
from chronicle.world import token_hash


def test_live_volume_binding_owns_each_materialized_world_token(app_config, monkeypatch):
    config = replace(app_config, hermes_home=app_config.runtime_dir / "hermes-home")
    tokens: dict[str, str] = {}

    def fake_materialize(_config, worldline_id, lifetimes, **_kwargs):
        result = {}
        for lifetime in lifetimes:
            seat = str(lifetime["id"])
            token = f"token-{seat}"
            tokens[seat] = token
            result[seat] = {
                "profile": f"chronicle-{worldline_id}-{seat}",
                "world_token": token,
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{seat}",
            }
        return result

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    created = ChronicleHost(config).volume_runtime.create(runtime_mode="live")
    bindings = {
        str(binding["role"]): binding
        for binding in ChronicleHost(config).db.agent_bindings(created["worldline"]["id"])
    }

    assert {seat for seat, binding in bindings.items() if binding["token_hash"]} == set(tokens)
    assert all(binding["token_hash"] == token_hash(tokens[seat]) for seat, binding in bindings.items())


def test_live_driver_stages_explicit_model_intent_without_default_wait(
    app_config, monkeypatch, tmp_path: Path
):
    config = replace(app_config, hermes_home=tmp_path / "hermes-home")
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake = host.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    seat = str(wake["actor_id"])
    profile = f"chronicle-{worldline_id}-{seat}"
    host.db.update_worldline_lifetime(worldline_id, seat, profile_name=profile)
    memory = config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("", encoding="utf-8")

    class FakeClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "fresh-session"

        def chat(self, _profile, _key, _messages, session_id, _memory_key):
            return '{"type":"update_plan","objective":"先确认来信约束","steps":["核对来信内容"]}', session_id

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    result = HermesVolumeActorDriver(config, host.db).run_wake(
        wake, wake["frozen_perspective"]
    )

    operations = host.db.crisis_wake_operations(wake["id"])
    assert result["session_id"] == "fresh-session"
    assert len(operations) == 1
    assert operations[0]["tool_name"] == "logical_intent"
    assert operations[0]["payload"]["intent"]["type"] == "update_plan"
    assert host.db.crisis_wake(wake["id"])["status"] == "STAGED"


def test_live_driver_rejects_unstructured_model_output(app_config, monkeypatch, tmp_path: Path):
    config = replace(app_config, hermes_home=tmp_path / "hermes-home")
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake = host.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    seat = str(wake["actor_id"])
    profile = f"chronicle-{worldline_id}-{seat}"
    host.db.update_worldline_lifetime(worldline_id, seat, profile_name=profile)
    memory = config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("", encoding="utf-8")

    class FakeClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "fresh-session"

        def chat(self, _profile, _key, _messages, session_id, _memory_key):
            return "我会继续观察。", session_id

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    with pytest.raises(VolumeActorDriverError, match="logical_intent"):
        HermesVolumeActorDriver(config, host.db).run_wake(
            wake, wake["frozen_perspective"]
        )

    assert host.db.crisis_wake(wake["id"])["status"] == "FAILED"
    assert host.db.crisis_wake_operations(wake["id"]) == []

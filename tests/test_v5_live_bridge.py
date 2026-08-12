from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from chronicle import world_mcp
from chronicle.host import ChronicleHost
from chronicle.volume_live import HermesVolumeActorDriver, VolumeActorDriverError
from chronicle.world import WorldAccessError, token_hash


def test_update_plan_mcp_schema_allows_evidence_event_ids():
    annotation = inspect.signature(world_mcp.update_plan).parameters["belief_updates"].annotation

    assert "Any" in str(annotation)


def test_live_wake_prompt_declares_required_logical_intent_arguments(app_config):
    messages = HermesVolumeActorDriver(app_config, object())._messages(
        {"id": "wake-1", "wake_type": "OBSERVATION", "worldline_id": "worldline-1", "actor_id": "wu-sangui"},
        {"moment_id": "moment-1"},
    )
    message = messages[1]
    system_message = messages[0]
    payload = json.loads(message["content"])

    assert payload["logical_intent_tool_call"] == {
        "name": "logical_intent",
        "arguments": {
            "intent": {"type": "wait"},
            "idempotency_key": "wake-1:logical-intent",
            "wake_id": "wake-1",
        },
    }
    assert "顶层 wake_id" in payload["tool_call_rule"]
    assert "subject_affordances" in system_message["content"]
    assert "targets 的 options 的实体 id" in system_message["content"]
    assert "terms 必须是" in system_message["content"]
    assert "wake_id" in system_message["content"]
    assert "立即结束本次回答" in system_message["content"]


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


def test_volume_mcp_requires_exact_wake_when_one_lifetime_has_duplicate_wakes(
    app_config, monkeypatch, tmp_path: Path
):
    config = replace(
        app_config,
        database_path=tmp_path / "chronicle.db",
        hermes_home=tmp_path / "hermes-home",
        runtime_dir=tmp_path / "runtime",
    )
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    lifetime = host.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert lifetime is not None
    token = "volume-token-wu"
    with host.db.transaction() as connection:
        connection.execute(
            "UPDATE worldline_agent_bindings SET token_hash = ?, profile_identity = ? "
            "WHERE worldline_id = ? AND role = ?",
            (token_hash(token), "profile-wu", worldline_id, "wu-sangui"),
        )
    for wake_id in ("wake-a", "wake-b"):
        host.db.create_crisis_wake(
            {
                "id": wake_id,
                "worldline_id": worldline_id,
                "actor_id": "wu-sangui",
                "wake_type": "OBSERVATION",
                "tick": 1,
                "status": "RUNNING",
                "trigger_event_id": f"trigger-{wake_id}",
                "frozen_perspective": {"moment_id": "moment-1"},
            }
        )

    monkeypatch.setenv("CHRONICLE_WORLD_TOKEN", token)
    monkeypatch.setattr(world_mcp, "load_config", lambda environ=None: config)

    with pytest.raises(WorldAccessError, match="wake identity is required"):
        world_mcp._volume_context()

    assert world_mcp._volume_context("wake-a")[-1]["id"] == "wake-a"
    assert world_mcp._volume_context("wake-b")[-1]["id"] == "wake-b"
    host.db.update_crisis_wake("wake-b", status="STAGED")
    with pytest.raises(WorldAccessError, match="wake identity is required"):
        world_mcp._volume_context()
    with pytest.raises(WorldAccessError, match="wake identity is not active"):
        world_mcp._volume_context("wake-missing")


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


def test_live_driver_repairs_one_missing_tool_call_in_same_session(
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
        calls = 0

        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "fresh-session"

        def chat(self, _profile, _key, messages, session_id, _memory_key):
            self.calls += 1
            if len(messages) == 1 and messages[0]["role"] == "user":
                return '{"type":"wait"}', session_id
            return "未提交协议意图。", session_id

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    HermesVolumeActorDriver(config, host.db).run_wake(wake, wake["frozen_perspective"])

    operations = host.db.crisis_wake_operations(wake["id"])
    assert len(operations) == 1
    assert operations[0]["idempotency_key"] == f"{wake['id']}:model-response"
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


def test_live_driver_fail_closes_malformed_structured_intent(
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
            return '{"type":"update_plan"}', session_id

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    with pytest.raises(VolumeActorDriverError, match="invalid structured logical intent"):
        HermesVolumeActorDriver(config, host.db).run_wake(wake, wake["frozen_perspective"])

    assert host.db.crisis_wake(wake["id"])["status"] == "FAILED"


def test_live_driver_rejects_multiple_proposed_operations(
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
    moment_id = str(wake["frozen_perspective"]["moment_id"])
    for index, tool_name in enumerate(("update_plan", "communicate")):
        host.db.add_crisis_wake_operation(
            {
                "wake_id": wake["id"],
                "tool_name": tool_name,
                "payload": {"moment_id": moment_id, "seat": seat},
                "result": {"status": "accepted"},
                "idempotency_key": f"seeded-operation-{index}",
            }
        )

    class FakeClient:
        def __init__(self, _config):
            pass

        def create_fresh_session(self, _profile, _key, _wake_id):
            return "fresh-session"

        def chat(self, _profile, _key, _messages, session_id, _memory_key):
            return '{"type":"wait"}', session_id

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    with pytest.raises(VolumeActorDriverError, match="multiple logical intents"):
        HermesVolumeActorDriver(config, host.db).run_wake(wake, wake["frozen_perspective"])

    assert host.db.crisis_wake(wake["id"])["status"] == "FAILED"
    operations = host.db.crisis_wake_operations(wake["id"])
    assert [operation["status"] for operation in operations] == ["REJECTED", "REJECTED"]
    assert all(operation["result"]["code"] == "multiple_logical_intents" for operation in operations)

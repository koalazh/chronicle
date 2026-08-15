from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chronicle import hermes, world_mcp
from chronicle.app import create_app
from chronicle.host import ChronicleHost
from chronicle.volume_live import (
    HermesVolumeActorDriver,
    RetryableVolumeActorDriverError,
    VolumeActorDriverError,
)
from chronicle.volume_runtime import VolumeRuntimeConflict
from chronicle.world import WorldAccessError, token_hash


def test_update_plan_mcp_schema_allows_evidence_event_ids():
    annotation = inspect.signature(world_mcp.update_plan).parameters["belief_updates"].annotation

    assert "Any" in str(annotation)


def test_live_wake_prompt_declares_required_logical_intent_arguments(app_config):
    messages = HermesVolumeActorDriver(app_config, object())._messages(
        {
            "id": "wake-1",
            "wake_type": "OBSERVATION",
            "worldline_id": "worldline-1",
            "actor_id": "wu-sangui",
            "trigger_event_id": "event-1",
        },
        {"moment_id": "moment-1", "context": {"current_course": {"course": "保持关口秩序"}}},
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
    assert "subject、assessment、confidence、evidence_event_ids" in system_message["content"]
    assert "禁止使用 belief、text 或其他别名" in system_message["content"]
    assert "只有 frozen_perspective.context.current_course 非空时才允许 HOLD" in system_message[
        "content"
    ]
    assert "禁止使用 OFFER" in system_message["content"]
    assert "禁止使用 c001 等猜测或场景编号" in system_message["content"]
    assert payload["deliberation_schema"]["belief_updates"][0] == {
        "subject": "事实或判断对象",
        "assessment": "基于当前证据的判断",
        "confidence": "low|medium|high 或 0..1",
        "evidence_event_ids": ["冻结视角中的 event_id"],
    }
    assert "wake_id" in system_message["content"]
    assert "立即结束本次回答" in system_message["content"]


def test_live_wake_prompt_demonstrates_revise_without_a_current_course(app_config):
    messages = HermesVolumeActorDriver(app_config, object())._messages(
        {
            "id": "wake-2",
            "wake_type": "CHECKPOINT_DECISION",
            "worldline_id": "worldline-1",
            "actor_id": "wu-sangui",
            "trigger_event_id": "event-2",
        },
        {"moment_id": "moment-2", "context": {"current_course": None}},
    )
    payload = json.loads(messages[1]["content"])
    assert payload["commit_deliberation_tool_call"]["arguments"]["outcome"] == "REVISE"
    assert payload["commit_deliberation_tool_call"]["arguments"]["course"] == {
        "summary": "先记录当前冻结触发，再依据后续可见证据决定下一步。",
        "steps": ["记录当前冻结触发"],
        "evidence_event_ids": ["event-2"],
    }
    assert "首次判断" in messages[0]["content"]
    assert "DEADLINE" in messages[0]["content"]


def test_live_wake_prompt_requires_experience_reference_on_later_wu_cognition(app_config):
    messages = HermesVolumeActorDriver(app_config, object())._messages(
        {
            "id": "wake-3",
            "wake_type": "REVISIT_DUE",
            "worldline_id": "worldline-1",
            "actor_id": "wu-sangui",
            "trigger_event_id": "event-3",
        },
        {
            "moment_id": "moment-3",
            "context": {
                "current_course": {"course": "保留关口选择"},
                "relevant_experience": {
                    "experiences": [{"id": "experience-wu-3"}],
                },
            },
        },
    )
    assert "experience_refs" in messages[0]["content"]
    assert "逐字引用相关 experience id" in messages[0]["content"]


def test_live_driver_rejects_direct_intent_after_wu_experience(app_config, tmp_path: Path):
    config = replace(app_config, hermes_home=tmp_path / "hermes-home")
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute("UPDATE worldlines SET runtime_mode = 'live' WHERE id = ?", (worldline_id,))
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake = host.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    moment_id = str(wake["frozen_perspective"]["moment_id"])
    operation = host.db.add_crisis_wake_operation(
        {
            "wake_id": wake["id"],
            "tool_name": "logical_intent",
            "payload": {
                "moment_id": moment_id,
                "intent": {"type": "wait"},
            },
            "result": {"status": "accepted"},
            "idempotency_key": "direct-wait",
        }
    )
    perspective = {
        "moment_id": moment_id,
        "context": {
            "current_course": {"course": "保留当前判断"},
            "relevant_experience": {"experiences": [{"id": "experience-wu-3"}]}
        },
    }

    result = HermesVolumeActorDriver(config, host.db)._logical_operation_or_fail(
        wake, perspective, "wu-sangui"
    )

    assert result is None
    rejected = host.db.crisis_wake_operations(wake["id"])[0]
    assert rejected["id"] == operation["id"]
    assert rejected["status"] == "REJECTED"
    assert rejected["result"]["code"] == "experience_reference_required"


def test_live_driver_rejects_direct_intent_at_wu_dependency_match(app_config, tmp_path: Path):
    config = replace(app_config, hermes_home=tmp_path / "hermes-home")
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute("UPDATE worldlines SET runtime_mode = 'live' WHERE id = ?", (worldline_id,))
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake = host.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    moment_id = str(wake["frozen_perspective"]["moment_id"])
    operation = host.db.add_crisis_wake_operation(
        {
            "wake_id": wake["id"],
            "tool_name": "logical_intent",
            "payload": {
                "moment_id": moment_id,
                "intent": {"type": "wait"},
            },
            "result": {"status": "accepted"},
            "idempotency_key": "direct-wait-at-dependency",
        }
    )
    perspective = {
        "moment_id": moment_id,
        "context": {
            "current_course": {"course": "保留当前判断"},
            "why_now": {"matched_dependency_ids": ["bounded-reconsideration"]},
        },
    }

    result = HermesVolumeActorDriver(config, host.db)._logical_operation_or_fail(
        wake, perspective, "wu-sangui"
    )

    assert result is None
    rejected = host.db.crisis_wake_operations(wake["id"])[0]
    assert rejected["id"] == operation["id"]
    assert rejected["status"] == "REJECTED"
    assert rejected["result"]["code"] == "dependency_revision_required"


def test_live_driver_rejects_direct_intent_for_initial_wu_course(app_config, tmp_path: Path):
    config = replace(app_config, hermes_home=tmp_path / "hermes-home")
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute("UPDATE worldlines SET runtime_mode = 'live' WHERE id = ?", (worldline_id,))
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake = host.db.crisis_wake(frozen["pending_moment"]["wake_ids"][0])
    assert wake is not None
    moment_id = str(wake["frozen_perspective"]["moment_id"])
    operation = host.db.add_crisis_wake_operation(
        {
            "wake_id": wake["id"],
            "tool_name": "logical_intent",
            "payload": {
                "moment_id": moment_id,
                "intent": {"type": "update_plan", "objective": "等待", "steps": ["等待"]},
            },
            "result": {"status": "accepted"},
            "idempotency_key": "direct-course",
        }
    )
    perspective = {"moment_id": moment_id, "context": {"current_course": None}}

    result = HermesVolumeActorDriver(config, host.db)._logical_operation_or_fail(
        wake, perspective, "wu-sangui"
    )

    assert result is None
    rejected = host.db.crisis_wake_operations(wake["id"])[0]
    assert rejected["id"] == operation["id"]
    assert rejected["status"] == "REJECTED"
    assert rejected["result"]["code"] == "initial_deliberation_required"


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


def test_live_crisis_activation_creates_checkpoint_wakes(app_config, monkeypatch):
    config = replace(app_config, hermes_home=app_config.runtime_dir / "hermes-home-checkpoint")

    def fake_materialize(_config, worldline_id, lifetimes, **_kwargs):
        return {
            str(lifetime["id"]): {
                "profile": f"chronicle-{worldline_id}-{lifetime['id']}",
                "world_token": f"token-{lifetime['id']}",
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{lifetime['id']}",
            }
            for lifetime in lifetimes
        }

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    host = ChronicleHost(config)
    created = host.volume_runtime.create(runtime_mode="live")
    worldline_id = created["worldline"]["id"]

    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    wakes = host.db.subject_wakes(worldline_id, tick=0)

    assert {wake["actor_id"] for wake in wakes} == {"li-zicheng", "wu-sangui", "dorgon"}
    assert {wake["wake_type"] for wake in wakes} == {"CHECKPOINT_DECISION"}
    assert all(wake["source"] == "v6-checkpoint" for wake in wakes)


def test_live_volume_startup_reconciles_profiles_bindings_and_gateway(
    app_config, monkeypatch
):
    config = replace(app_config, dev=True)
    records: dict[str, dict[str, dict[str, str]]] = {}
    ensured: list[tuple[str, str]] = []

    def fake_materialize(_config, worldline_id, lifetimes, **_kwargs):
        result = {}
        for lifetime in lifetimes:
            seat = str(lifetime["id"])
            profile = hermes.lifetime_profile_name(worldline_id, seat)
            result[seat] = {
                "profile": profile,
                "profile_key": f"key-{seat}",
                "world_token": f"token-{seat}",
                "ownership_marker": hermes.stable_lifetime_profile_marker(
                    worldline_id, seat, profile
                ),
                "world_server_name": hermes.lifetime_world_server_name(worldline_id, seat),
            }
        records[worldline_id] = result
        return result

    def fake_load(_config, worldline_id, lifetimes, **_kwargs):
        assert all(str(item["id"]).startswith(f"{worldline_id}:lifetime:") for item in lifetimes)
        return {
            seat: {
                **record,
                "lifetime_id": seat,
            }
            for seat, record in records[worldline_id].items()
        }

    def fake_ensure(_controller, worldline_id, runtime_epoch):
        ensured.append((worldline_id, runtime_epoch))

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.hermes.load_lifetime_profile_records", fake_load)
    monkeypatch.setattr("chronicle.gateway.GatewayController.ensure", fake_ensure)

    created = ChronicleHost(config).volume_runtime.create(runtime_mode="live")
    worldline_id = created["worldline"]["id"]
    assert created["worldline"]["runtime_phase"] == "BOOTSTRAPPING"

    with TestClient(create_app(config)):
        pass

    reconciled = ChronicleHost(config).db.worldline(worldline_id)
    assert reconciled is not None
    assert reconciled["runtime_phase"] == "READY"
    assert ensured == [(worldline_id, reconciled["runtime_epoch"])]


def test_live_volume_reconcile_fails_closed_on_binding_identity_drift(
    app_config, monkeypatch
):
    config = replace(app_config, dev=True)
    records: dict[str, dict[str, dict[str, str]]] = {}

    def fake_materialize(_config, worldline_id, lifetimes, **_kwargs):
        result = {}
        for lifetime in lifetimes:
            seat = str(lifetime["id"])
            profile = f"chronicle-{worldline_id}-{seat}"
            result[seat] = {
                "profile": profile,
                "world_token": f"token-{seat}",
                "ownership_marker": hermes.stable_lifetime_profile_marker(
                    worldline_id, seat, profile
                ),
                "world_server_name": hermes.lifetime_world_server_name(worldline_id, seat),
            }
        records[worldline_id] = result
        return result

    def fake_load(_config, worldline_id, _lifetimes, **_kwargs):
        return {
            seat: {
                **record,
                "lifetime_id": seat,
            }
            for seat, record in records[worldline_id].items()
        }

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.hermes.load_lifetime_profile_records", fake_load)
    monkeypatch.setattr("chronicle.gateway.GatewayController.ensure", lambda *_args: None)

    host = ChronicleHost(config)
    created = host.volume_runtime.create(runtime_mode="live")
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute(
            "UPDATE worldline_agent_bindings SET token_hash = ? WHERE worldline_id = ? AND role = ?",
            ("drifted", worldline_id, "wu-sangui"),
        )

    with pytest.raises(ValueError, match="identity is inconsistent"):
        host.volume_runtime.reconcile_live_runtime(worldline_id)
    failed = host.db.worldline(worldline_id)
    assert failed is not None
    assert failed["runtime_phase"] == "FAILED"
    assert failed["runtime_error_code"] == "volume_reconcile_failed"


def test_pending_reconcile_requeues_transient_live_wake_failure(app_config):
    host = ChronicleHost(app_config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake_id = frozen["pending_moment"]["wake_ids"][0]
    host.db.update_crisis_wake(
        wake_id,
        status="FAILED",
        error={"actor_id": "wu-sangui", "code": "live_wake_failed"},
    )

    host.volume_runtime._validate_pending_reconcile(worldline_id)

    wake = host.db.crisis_wake(wake_id)
    assert wake is not None
    assert wake["status"] == "QUEUED"
    assert wake["error"] == {
        "actor_id": "wu-sangui",
        "code": "live_wake_failed",
        "retryable": True,
    }


def test_pending_reconcile_keeps_terminal_live_wake_failure_recoverable(app_config):
    host = ChronicleHost(app_config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    host.volume_runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    host.volume_runtime.advance_one(worldline_id)
    frozen = host.volume_runtime.freeze_pending_moment(worldline_id)
    wake_id = frozen["pending_moment"]["wake_ids"][0]
    moment_id = frozen["pending_moment"]["id"]
    host.db.add_crisis_wake_operation(
        {
            "wake_id": wake_id,
            "tool_name": "logical_intent",
            "payload": {"moment_id": moment_id},
            "result": {"status": "rejected", "code": "missing_logical_intent"},
            "status": "REJECTED",
            "idempotency_key": f"{wake_id}:rejected",
        }
    )
    host.db.update_crisis_wake(
        wake_id,
        status="FAILED",
        error={"actor_id": "wu-sangui", "code": "missing_logical_intent"},
    )

    host.volume_runtime._validate_pending_reconcile(worldline_id)

    assert host.db.crisis_wake(wake_id)["status"] == "FAILED"


def test_failed_live_reconcile_blocks_reads_and_mutations(
    app_config, monkeypatch
):
    config = replace(app_config, dev=True)
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute(
            "UPDATE worldlines SET runtime_mode = 'live', runtime_phase = 'FAILED' WHERE id = ?",
            (worldline_id,),
        )

    def keep_failed(_runtime, _worldline_id):
        raise RuntimeError("reconcile remains unavailable")

    monkeypatch.setattr(
        "chronicle.volume_runtime.VolumeRuntime.reconcile_live_runtime",
        keep_failed,
    )

    with pytest.raises(VolumeRuntimeConflict, match="unavailable"):
        host.volume_runtime.worldline(worldline_id)
    with pytest.raises(VolumeRuntimeConflict, match="unavailable"):
        host.volume_runtime.seal(worldline_id)

    with TestClient(create_app(config)) as client:
        world = client.get(f"/api/worldlines/{worldline_id}/world")
        continued = client.post(f"/api/worldlines/{worldline_id}/continue")
        sealed = client.post(f"/api/worldlines/{worldline_id}/seal", json={})

    assert world.status_code == 503
    assert continued.status_code == 503
    assert sealed.status_code == 503


def test_failed_live_volume_can_be_resumed_by_create_request(app_config, monkeypatch):
    config = replace(app_config, dev=False)
    host = ChronicleHost(config)
    created = host.volume_runtime.create()
    worldline_id = created["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute(
            "UPDATE worldlines SET runtime_mode = 'live', runtime_phase = 'FAILED' WHERE id = ?",
            (worldline_id,),
        )
    resumed: list[str] = []

    def fake_ensure(runtime, target):
        resumed.append(target)
        return runtime.db.set_volume_runtime_state(target, "READY")

    monkeypatch.setattr("chronicle.volume_runtime.VolumeRuntime.ensure_live_runtime", fake_ensure)

    client = TestClient(create_app(config))
    response = client.post("/api/worldlines", json={"live": True})

    assert response.status_code == 200
    assert response.json()["worldline"]["id"] == worldline_id
    assert resumed == [worldline_id]


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
        host.db.create_subject_wake(
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


def test_live_driver_requeues_provider_timeout_for_safe_retry(
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

        def chat(self, _profile, _key, _messages, _session_id, _memory_key):
            raise RuntimeError("provider timed out")

    monkeypatch.setattr("chronicle.volume_live.HermesClient", FakeClient)
    monkeypatch.setattr("chronicle.volume_live.profile_api_key", lambda *_args: "profile-key")

    with pytest.raises(RetryableVolumeActorDriverError, match="Wake failed"):
        HermesVolumeActorDriver(config, host.db).run_wake(
            wake, wake["frozen_perspective"]
        )

    retriable = host.db.crisis_wake(wake["id"])
    assert retriable is not None
    assert retriable["status"] == "QUEUED"
    assert retriable["error"] == {
        "actor_id": seat,
        "code": "live_wake_failed",
        "retryable": True,
    }


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

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from chronicle.db import content_hash
from chronicle.host import ChronicleHost

BOUNDARY_EVALUATOR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "v6_controller_boundary_evaluator.py"
)
PUBLIC_TRACE_EXPORTER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "v6_export_public_trace.py"
)


def _blind_evaluate(trace: list[dict[str, object]]) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(
        [sys.executable, str(BOUNDARY_EVALUATOR), "-"],
        input=json.dumps({"trace": trace}, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_public_trace_exporter_only_emits_public_event_fields(tmp_path):
    database = tmp_path / "public-trace.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE worldline_events (
            sequence INTEGER PRIMARY KEY,
            id TEXT NOT NULL,
            worldline_id TEXT NOT NULL,
            tick INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        INSERT INTO worldline_events VALUES
        (1, 'public-1', 'volume-1', 2, 'MESSAGE_DELIVERED',
         '{"recipient":"shi-kefa","message_id":"message-1","content":"public"}'),
        (2, 'private-1', 'volume-1', 2, 'INTENT_COMMITTED',
         '{"seat":"shi-kefa","source":"human","intent":{"type":"wait"}}');
        """
    )
    connection.commit()
    connection.close()

    completed = subprocess.run(
        [sys.executable, str(PUBLIC_TRACE_EXPORTER), str(database), "volume-1"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert len(payload["trace"]) == 1
    assert payload["trace"][0]["action"] == "MESSAGE_DELIVERED"
    assert "content" not in payload["trace"][0]
    assert "human" not in completed.stdout.lower()


def _two_subject_pending_moment(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"{suffix}.db"),
        runtime_dir=app_config.runtime_dir / suffix,
        hermes_home=app_config.hermes_home / suffix,
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert dorgon is not None
    runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:wake:dorgon:adversarial",
            "worldline_id": worldline_id,
            "actor_id": dorgon["seat"],
            "wake_type": "OBSERVATION",
            "tick": 1,
            "status": "QUEUED",
            "source": "adversarial-harness",
            "trigger_event_id": f"{worldline_id}:trigger:dorgon",
        }
    )
    return runtime, worldline_id


def test_single_agent_impostor_baseline_converges_while_peer_contexts_diverge(app_config):
    runtime, worldline_id = _two_subject_pending_moment(app_config, "impostor-peer")
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert wu is not None and dorgon is not None
    wu_memory = "吴三桂私下判断：关口承诺必须等可见行动验证。"
    dorgon_memory = "多尔衮私下判断：西征路线不能被关内来信改写。"
    runtime.db.update_worldline_lifetime(
        worldline_id,
        wu["seat"],
        memory_text=wu_memory,
        memory_hash=content_hash(wu_memory),
    )
    runtime.db.update_worldline_lifetime(
        worldline_id,
        dorgon["seat"],
        memory_text=dorgon_memory,
        memory_hash=content_hash(dorgon_memory),
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    perspectives = {}
    for wake_id in frozen["pending_moment"]["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        actor_id = str(wake["actor_id"])
        seat = "wu-sangui" if actor_id in {wu["id"], wu["seat"]} else "dorgon"
        perspectives[seat] = wake["frozen_perspective"]

    def peer_policy(perspective):
        memory = perspective["context"]["subjective_memory"]["text"]
        if "吴三桂" in memory:
            return {"type": "message", "recipient": "dorgon", "content": "请以行动证明承诺。"}
        return {"type": "update_plan", "objective": "保留西征路线的自主判断"}

    peer_actions = {
        actor_id: peer_policy(perspective)
        for actor_id, perspective in perspectives.items()
    }
    central_context = "\n".join(
        perspective["context"]["subjective_memory"]["text"]
        for perspective in perspectives.values()
    )

    def central_persona_switch(_all_private_context):
        # Negative control: one central actor sees both private memories and emits one policy.
        assert wu_memory in _all_private_context and dorgon_memory in _all_private_context
        return {
            actor_id: {"type": "update_plan", "objective": "统一保留当前关口选择"}
            for actor_id in perspectives
        }

    central_actions = central_persona_switch(central_context)
    assert wu_memory in perspectives["wu-sangui"]["context"]["subjective_memory"]["text"]
    assert dorgon_memory not in perspectives["wu-sangui"]["context"]["subjective_memory"]["text"]
    assert dorgon_memory in perspectives["dorgon"]["context"]["subjective_memory"]["text"]
    assert wu_memory not in perspectives["dorgon"]["context"]["subjective_memory"]["text"]
    assert peer_actions["wu-sangui"] != peer_actions["dorgon"]
    assert central_actions["wu-sangui"] == central_actions["dorgon"]


def test_no_offscreen_cognition_changes_the_pending_user_boundary(app_config):
    deterministic, deterministic_id = _two_subject_pending_moment(app_config, "offscreen-none")
    cognitive, cognitive_id = _two_subject_pending_moment(app_config, "offscreen-resolved")

    for runtime, worldline_id in (
        (deterministic, deterministic_id),
        (cognitive, cognitive_id),
    ):
        runtime.reconcile_crisis_envelopes(worldline_id)
        runtime.settle_crisis(worldline_id, "before-shanhaiguan")
        runtime.settle_crisis(worldline_id, "nanjing-succession")
        runtime._suppress_dormant_crisis(
            worldline_id,
            "southern-consolidation",
            "南京政治中心未在当前测试分支形成可执行状态",
        )

    deterministic_boundary = deterministic.boundary(deterministic_id)["boundary"]
    assert deterministic_boundary["code"] == "due_wake_pending"
    assert not any(
        event["event_type"] == "INTENT_COMMITTED"
        for event in deterministic.db.worldline_events(deterministic_id)
    )

    frozen = cognitive.freeze_pending_moment(cognitive_id)
    for wake_id in frozen["pending_moment"]["wake_ids"]:
        wake = cognitive.db.crisis_wake(wake_id)
        assert wake is not None
        lifetime = cognitive.db.worldline_lifetime_by_id(
            cognitive_id, str(wake["actor_id"])
        ) or cognitive.db.worldline_lifetime(cognitive_id, str(wake["actor_id"]))
        assert lifetime is not None
        source = "human" if lifetime["controller"] == "HUMAN" else "agent"
        cognitive.stage_intent(
            cognitive_id,
            lifetime["id"],
            {"type": "wait"},
            source=source,
            wake_id=wake_id,
        )
    cognitive.commit_pending_moment(cognitive_id)
    resolved_boundary = cognitive.boundary(cognitive_id)["boundary"]

    assert resolved_boundary["code"] != "due_wake_pending"
    assert any(
        event["event_type"] == "MOMENT_COMMITTED"
        for event in cognitive.db.worldline_events(cognitive_id)
    )


def test_controller_boundary_uses_blind_external_evaluator(app_config):
    runtime, worldline_id = _two_subject_pending_moment(app_config, "blind-controller-boundary")
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert dorgon is not None
    wake = next(
        wake
        for wake in runtime.db.subject_wakes(worldline_id)
        if wake["actor_id"] in {dorgon["id"], dorgon["seat"]}
    )

    before = runtime.db.worldline_lifetime(worldline_id, dorgon["seat"])
    assert before is not None
    runtime.host.volume_runtime.inhabit(worldline_id, dorgon["id"])
    runtime.host.volume_runtime.leave(worldline_id)
    after = runtime.db.worldline_lifetime(worldline_id, dorgon["seat"])
    assert after is not None
    assert after["controller"] == before["controller"]
    assert runtime.db.worldline(worldline_id)["current_tick"] == 1
    persisted_wake = runtime.db.crisis_wake(wake["id"])
    assert persisted_wake is not None
    assert wake["trigger_event_id"] == persisted_wake["trigger_event_id"]

    # The subprocess receives only public behavior. Human/Hermes labels and
    # the lifecycle events are deliberately absent from its input.
    public_trace = [
        {
            "tick": 1,
            "subject": dorgon["seat"],
            "action": "wait",
            "public_state": "same_pending_trigger",
            "public_evidence": [
                {"id": "trigger-1", "kind": "public-trigger", "tick": 1}
            ],
        },
        {
            "tick": 1,
            "subject": dorgon["seat"],
            "action": "wait",
            "public_state": "same_pending_trigger",
            "public_evidence": [
                {"id": "trigger-1", "kind": "public-trigger", "tick": 1}
            ],
        },
    ]
    return_code, result = _blind_evaluate(public_trace)
    assert return_code == 0
    assert result["verdict"] == "PASS"
    assert result["unexplained_discontinuities"] == []

    bad_code, bad_result = _blind_evaluate(
        [
            {"tick": 1, "subject": "dorgon", "action": "wait"},
            {"tick": 1, "subject": "dorgon", "action": "message"},
        ]
    )
    assert bad_code == 1
    assert bad_result["verdict"] == "NEEDS_WORK"
    assert bad_result["reason"] if "reason" in bad_result else bad_result["unexplained_discontinuities"]

    malformed_code, malformed_result = _blind_evaluate(
        [
            {"tick": 1, "subject": "dorgon", "action": "wait"},
            {
                "tick": 1,
                "subject": "dorgon",
                "action": "message",
                "public_evidence": "unverified",
            },
        ]
    )
    assert malformed_code == 1
    assert malformed_result["verdict"] == "NEEDS_WORK"
    assert malformed_result["unexplained_discontinuities"]

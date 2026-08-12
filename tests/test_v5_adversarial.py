from __future__ import annotations

from dataclasses import replace

from chronicle.db import content_hash
from chronicle.host import ChronicleHost


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
        runtime.settle_crisis(worldline_id, "southern-consolidation")

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

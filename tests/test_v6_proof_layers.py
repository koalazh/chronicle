from __future__ import annotations

import copy
from dataclasses import replace

from chronicle.host import ChronicleHost


def _runtime(app_config, tmp_path):
    config = replace(
        app_config,
        database_path=tmp_path / "v6-proof-layers.db",
        runtime_dir=tmp_path / "runtime",
        hermes_home=tmp_path / "hermes",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return config, host, runtime, worldline_id, wu


def _establish(runtime, worldline_id, wu, *, depends_on_dorgon: bool = False):
    dependencies = (
        [{"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}]
        if depends_on_dorgon
        else []
    )
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "暂守关口",
            "steps": ["继续核验"],
            "open_dependencies": dependencies,
        },
        source="agent",
        idempotency_key="v6-proof-layers-course",
    )
    committed = runtime.commit_pending_moment(worldline_id)
    lifetime = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert lifetime is not None
    return committed, copy.deepcopy(lifetime["plan"][0])


def _custom_wake(runtime, worldline_id, wu, suffix: str):
    tick = int(runtime.db.worldline(worldline_id)["current_tick"])
    wake_id = f"{worldline_id}:v6-proof:{suffix}"
    runtime.db.create_subject_wake(
        {
            "id": wake_id,
            "worldline_id": worldline_id,
            "actor_id": wu["seat"],
            "wake_type": "OBSERVATION",
            "tick": tick,
            "status": "QUEUED",
            "source": "v6-proof-layer",
            "trigger_event_id": "",
        }
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    assert wake_id in frozen["pending_moment"]["wake_ids"]
    return wake_id


def test_p6_noise_is_known_but_does_not_reopen_the_course(app_config, tmp_path):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, tmp_path)
    _committed, before = _establish(runtime, worldline_id, wu)
    sent = runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="li-zicheng",
        recipient="wu-sangui",
        content="一封与当前守关判断无关的公开来信。",
        delivery_tick=2,
    )
    advanced = runtime.advance_one(worldline_id)
    after = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert after is not None
    attention = next(
        event
        for event in advanced["events"]
        if event["event_type"] == "ATTENTION_EVALUATED" and event["seat_id"] == "wu-sangui"
    )

    assert any(
        isinstance(item, dict) and item.get("message_id") == sent["message"]["id"]
        for item in after["knowledge"]
    )
    assert attention["payload"]["decision"] == "BACKGROUND"
    assert after["plan"][0]["version"] == before["version"]
    assert not [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=2)
        if wake["actor_id"] == "wu-sangui" and wake["source"] == "v6-attention"
    ]


def test_p6_confirming_reality_holds_the_same_course_and_advances_boundary(
    app_config, tmp_path
):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, tmp_path)
    _committed, before = _establish(runtime, worldline_id, wu)
    wake_id = _custom_wake(runtime, worldline_id, wu, "hold")

    runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        {"outcome": "HOLD", "world_actions": []},
        source="agent",
        idempotency_key="v6-proof-layers-hold",
        wake_id=wake_id,
    )
    committed = runtime.commit_pending_moment(worldline_id)
    after = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert after is not None

    assert any(event["event_type"] == "DECISION_HORIZON_HELD" for event in committed["events"])
    assert after["plan"][0]["version"] == before["version"]
    assert after["plan"][0]["last_deliberated_event_id"] != before["last_deliberated_event_id"]


def test_p6_disconfirming_reality_revises_with_actor_visible_evidence(app_config, tmp_path):
    _config, _host, runtime, worldline_id, wu = _runtime(app_config, tmp_path)
    _committed, before = _establish(runtime, worldline_id, wu, depends_on_dorgon=True)
    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="dorgon",
        recipient="wu-sangui",
        content="清方给出了新的可核验条件。",
        delivery_tick=2,
    )
    advanced = runtime.advance_one(worldline_id)
    delivered = next(
        event for event in advanced["events"] if event["event_type"] == "MESSAGE_DELIVERED"
    )
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake_id = frozen["pending_moment"]["wake_ids"][0]
    runtime.stage_deliberation(
        worldline_id,
        wu["id"],
        {
            "outcome": "REVISE",
            "course": {
                "summary": "先核验清方通行条件",
                "steps": ["核验边界"],
                "evidence_event_ids": [delivered["id"]],
            },
            "open_dependencies": [],
            "world_actions": [],
        },
        source="agent",
        idempotency_key="v6-proof-layers-revise",
        wake_id=wake_id,
    )
    committed = runtime.commit_pending_moment(worldline_id)
    after = runtime.db.worldline_lifetime(worldline_id, wu["seat"])
    assert after is not None

    revised = next(
        event for event in committed["events"] if event["event_type"] == "DECISION_HORIZON_REVISED"
    )
    assert after["plan"][0]["version"] != before["version"]
    assert after["plan"][0]["evidence_event_ids"] == [delivered["id"]]
    assert revised["causal_parent_ids"]


def test_p6_course_survives_restart_controller_switch_and_fresh_context(app_config, tmp_path):
    config, host, runtime, worldline_id, wu = _runtime(app_config, tmp_path)
    _committed, before = _establish(runtime, worldline_id, wu)
    host.worldline_runtime.inhabit(worldline_id, wu["id"])
    host.worldline_runtime.leave(worldline_id)

    restarted = ChronicleHost(config).volume_runtime
    after = restarted.db.worldline_lifetime(worldline_id, wu["seat"])
    assert after is not None
    assert after["plan"] == [before]
    wake_id = _custom_wake(restarted, worldline_id, after, "fresh-context")
    wake = restarted.db.crisis_wake(wake_id)
    assert wake is not None
    assert wake["frozen_perspective"]["context"]["current_course"] == before

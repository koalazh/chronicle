from __future__ import annotations

from dataclasses import replace

from chronicle.host import ChronicleHost


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-content-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-content-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-content-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    return runtime, worldline_id


def test_remote_offer_and_acceptance_follow_route_before_agreement_exists(app_config):
    runtime, worldline_id = _runtime(app_config, "remote-agreement")
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    dorgon = runtime.db.worldline_lifetime(worldline_id, "dorgon")
    assert wu is not None and dorgon is not None

    runtime.freeze_pending_moment(worldline_id)
    proposed = runtime.stage_actor_tool(
        worldline_id,
        wu["id"],
        "manage_offer",
        {
            "action": "PROPOSE",
            "recipient": "dorgon",
            "terms": [{"type": "passage", "subject": "shanhai-pass", "value": "permitted"}],
            "message": "若共同处置东部局势，可按约定条件通过山海关。",
            "expires_after_days": 6,
        },
        idempotency_key="v6-remote-offer",
    )
    runtime.commit_pending_moment(worldline_id)
    assert proposed["status"] == "accepted"
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["before-shanhaiguan"][
        "offers"
    ][0]["status"] == "PROPOSED"
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["before-shanhaiguan"][
        "agreements"
    ] == []

    delivered = runtime.advance_one(worldline_id)
    assert delivered["tick"] == 3
    assert any(event["event_type"] == "MESSAGE_DELIVERED" for event in delivered["events"])
    assert any(event["event_type"] == "OFFER_CHANGED" for event in delivered["events"])
    offer_wakes = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=3)
        if wake["actor_id"] == "dorgon"
        and "OFFER_CHANGED"
        in {
            event["event_type"]
            for event in runtime.db.worldline_events(worldline_id)
            if event["id"]
            in wake.get("result", {}).get("attention", {}).get("trigger_event_ids", [])
        }
    ]
    assert len(offer_wakes) == 1

    runtime.freeze_pending_moment(worldline_id)
    pending = runtime.worldline(worldline_id)["projection"]["pending_moment"]
    for wake_id in pending["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        if wake["id"] == offer_wakes[0]["id"]:
            runtime.stage_actor_tool(
                worldline_id,
                dorgon["id"],
                "manage_offer",
                {"action": "ACCEPT", "offer_id": proposed["offer_id"]},
                idempotency_key="v6-remote-accept",
                wake_id=wake_id,
            )
        else:
            lifetime = runtime.db.worldline_lifetime(worldline_id, wake["actor_id"])
            assert lifetime is not None
            runtime.stage_intent(
                worldline_id,
                lifetime["id"],
                {"type": "wait"},
                source="agent",
                idempotency_key=f"v6-remote-wait-{wake_id}",
                wake_id=wake_id,
            )
    committed = runtime.commit_pending_moment(worldline_id)
    assert "AGREEMENT_CREATED" not in {event["event_type"] for event in committed["events"]}
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["before-shanhaiguan"][
        "agreements"
    ] == []

    accepted = runtime.advance_one(worldline_id)
    assert accepted["tick"] == 5
    agreement_event = next(
        event for event in accepted["events"] if event["event_type"] == "AGREEMENT_CREATED"
    )
    agreement = runtime.worldline(worldline_id)["projection"]["crisis_instances"]["before-shanhaiguan"][
        "agreements"
    ][0]
    assert agreement["effective_tick"] == 5
    assert agreement_event["payload"]["agreement"]["effective_tick"] == 5
    assert agreement_event["causal_parent_ids"]
    assert any(event["event_type"] == "OFFER_CHANGED" for event in accepted["events"])


def test_fixed_pressure_remains_exogenous_and_source_bounded(host):
    pressure = host.volume_runtime.pack.pack("before-shanhaiguan").crisis.pressures[0]

    assert pressure.id == "eastern-transit-window-narrows"
    assert pressure.trigger_tick == 5
    assert pressure.kind.value == "EXOGENOUS"
    assert pressure.provenance.value == "scenario_assumption"
    assert pressure.assertion_ids == ["c015"]


def test_shanhai_preparation_is_the_source_defined_fixed_operation(host):
    operation = host.volume_runtime.pack.pack("before-shanhaiguan").operation_by_id[
        "prepare_force"
    ]

    assert operation.duration_kind.value == "FIXED"
    assert operation.duration_days == 2
    assert operation.actor_ids == ["li-zicheng", "wu-sangui", "dorgon"]
    assert operation.required_assets == ["force"]
    assert operation.completion_effects[0].state == "READY"

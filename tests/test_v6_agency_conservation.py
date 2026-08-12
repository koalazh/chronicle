from __future__ import annotations

from dataclasses import replace

from chronicle.host import ChronicleHost


def _nanjing_runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-agency-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-agency-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-agency-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.advance_one(worldline_id)
    return runtime, worldline_id


def test_nanjing_contract_keeps_subjects_institution_and_claimants_distinct(host):
    pack = host.volume_runtime.pack.pack("nanjing-succession")
    operations = {operation.id: operation for operation in pack.crisis.operations}

    assert operations["make_fu_backing_visible"].actor_ids == ["ma-shiying"]
    assert operations["arrange_fu_entry"].actor_ids == ["ma-shiying"]
    assert operations["arrange_lu_entry"].actor_ids == ["shi-kefa"]
    assert operations["formalize_fu_regency"].actor_ids == ["han-zanzhou"]
    assert operations["formalize_lu_regency"].actor_ids == ["han-zanzhou"]
    assert operations["issue_regency_proclamation"].actor_ids == ["han-zanzhou"]
    assert {"fu-prince", "lu-prince"}.isdisjoint(host.volume_runtime.pack.lifetimes)
    assert all(operation.actor_ids for operation in pack.crisis.operations)
    assert all(
        set(operation.actor_ids).issubset(requirement.party_ids)
        for operation in pack.crisis.operations
        for requirement in operation.agreement_requirements
    )


def test_subject_cannot_stage_another_subjects_institutional_result(app_config):
    runtime, worldline_id = _nanjing_runtime(app_config, "authority")
    tick = int(runtime.db.worldline(worldline_id)["current_tick"])
    ma_wake_id = f"{worldline_id}:agency:ma"
    runtime.db.create_subject_wake(
        {
            "id": ma_wake_id,
            "worldline_id": worldline_id,
            "actor_id": "ma-shiying",
            "wake_type": "OBSERVATION",
            "tick": tick,
            "status": "QUEUED",
            "source": "v6-agency-test",
            "trigger_event_id": "",
        }
    )
    runtime.freeze_pending_moment(worldline_id)
    before_state = runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "nanjing-succession"
    ]["entities"]["nanjing-recognition"]["state"]

    rejected = runtime.stage_actor_tool(
        worldline_id,
        "ma-shiying",
        "operate",
        {
            "operation_definition_id": "formalize_fu_regency",
            "targets": ["fu-prince", "nanjing-court", "nanjing-recognition"],
            "description": "越权尝试替南京中枢完成制度承认。",
        },
        idempotency_key="v6-agency-cross-subject",
        wake_id=ma_wake_id,
    )
    committed = runtime.commit_pending_moment(worldline_id)

    assert rejected["status"] == "rejected"
    assert rejected["code"] == "operation_authority_denied"
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "nanjing-succession"
    ]["entities"]["nanjing-recognition"]["state"] == before_state
    rejection = next(event for event in committed["events"] if event["event_type"] == "INTENT_REJECTED")
    assert rejection["payload"]["code"] == "operation_authority_denied"


def test_subject_owned_operation_effects_keep_actor_and_causal_parent(app_config):
    runtime, worldline_id = _nanjing_runtime(app_config, "causal")
    tick = int(runtime.db.worldline(worldline_id)["current_tick"])
    ma_wake_id = f"{worldline_id}:agency:ma-causal"
    runtime.db.create_subject_wake(
        {
            "id": ma_wake_id,
            "worldline_id": worldline_id,
            "actor_id": "ma-shiying",
            "wake_type": "OBSERVATION",
            "tick": tick,
            "status": "QUEUED",
            "source": "v6-agency-test",
            "trigger_event_id": "",
        }
    )
    runtime.freeze_pending_moment(worldline_id)
    runtime.stage_actor_tool(
        worldline_id,
        "ma-shiying",
        "operate",
        {
            "operation_definition_id": "make_fu_backing_visible",
            "targets": ["jiangbei-military-backing"],
            "description": "把可见的江北保护安排带入南京的共同事实。",
        },
        idempotency_key="v6-agency-owned-operation",
        wake_id=ma_wake_id,
    )
    runtime.commit_pending_moment(worldline_id)
    advanced = runtime.advance_one(worldline_id)

    started = next(
        event
        for event in runtime.db.worldline_events(worldline_id)
        if event["event_type"] == "OPERATION_STARTED"
        and event["payload"]["operation"]["definition_id"] == "make_fu_backing_visible"
    )
    completed = next(
        event
        for event in advanced["events"]
        if event["event_type"] == "OPERATION_COMPLETED"
        and event["payload"]["operation"]["definition_id"] == "make_fu_backing_visible"
    )
    effect = next(
        event
        for event in advanced["events"]
        if event["event_type"] == "ENTITY_STATE_CHANGED"
        and event["payload"]["operation_id"] == completed["payload"]["operation"]["id"]
    )

    assert started["seat_id"] == "ma-shiying"
    assert completed["seat_id"] == "ma-shiying"
    assert effect["seat_id"] == "ma-shiying"
    assert effect["causal_parent_ids"] == [completed["id"]]
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"][
        "nanjing-succession"
    ]["entities"]["jiangbei-military-backing"]["state"] == "FU_BACKED"

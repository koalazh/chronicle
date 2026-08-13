from __future__ import annotations

import json
from dataclasses import replace

import pytest

from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntimeError


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-ablation-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-ablation-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-ablation-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return runtime, worldline_id, wu


def test_one_action_ablation_keeps_host_boundary_without_prompt_help(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "one-action")
    pending = runtime.worldline(worldline_id)["projection"]["pending_moment"]
    wake_id = pending["wake_ids"][0]

    with pytest.raises(VolumeRuntimeError, match="at most one action"):
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            {
                "outcome": "HOLD",
                "world_actions": [
                    {
                        "tool": "schedule_revisit",
                        "arguments": {"after_days": 1, "reason": "甲"},
                    },
                    {
                        "tool": "schedule_revisit",
                        "arguments": {"after_days": 2, "reason": "乙"},
                    },
                ],
            },
            source="agent",
            idempotency_key="v6-ablation-two-actions",
            wake_id=wake_id,
        )

    operations = runtime.db.crisis_wake_operations(wake_id)
    assert len(operations) == 1
    assert operations[0]["result"]["status"] == "rejected"
    assert runtime.worldline(worldline_id)["worldline"]["current_tick"] == 1


def test_authored_prepare_maneuver_is_load_bearing_not_generic_balance(host):
    pack = host.volume_runtime.pack.pack("before-shanhaiguan")
    operations_without_prepare = [
        operation.model_copy(
            update={
                "conflicts": [
                    conflict
                    for conflict in operation.conflicts
                    if conflict != "prepare_force"
                ]
            }
        )
        for operation in pack.crisis.operations
        if operation.id != "prepare_force"
    ]
    reduced = replace(
        pack,
        crisis=pack.crisis.model_copy(update={"operations": operations_without_prepare}),
    )
    reduced.validate()

    enter = reduced.operation_by_id["enter-shanhai-pass"]
    assert any(
        precondition.subject == "force" and "READY" in precondition.states
        for precondition in enter.preconditions
    )
    assert "prepare_force" not in reduced.operation_by_id


def test_prompt_complexity_ablation_keeps_host_schema_boundary(app_config):
    proposals = (
        {"outcome": "HOLD", "world_actions": []},
        {
            "outcome": "HOLD",
            "course": {},
            "open_dependencies": [],
            "belief_updates": [],
            "world_actions": [],
        },
    )
    results = []
    for index, proposal in enumerate(proposals):
        runtime, worldline_id, wu = _runtime(app_config, f"prompt-{index}")
        runtime.db.update_worldline_lifetime(
            worldline_id,
            wu["seat"],
            plan_json=json.dumps(
                [
                    {
                        "course_schema_version": 1,
                        "course": "先守住关口，等待可见消息",
                        "objective": "先守住关口，等待可见消息",
                        "steps": ["守住关口"],
                        "status": "IN_FORCE",
                        "open_dependencies": [],
                        "last_deliberated_tick": 0,
                        "last_deliberated_event_id": "seed-course",
                    }
                ],
                ensure_ascii=False,
            ),
        )
        wake_id = runtime.worldline(worldline_id)["projection"]["pending_moment"]["wake_ids"][0]
        runtime.stage_deliberation(
            worldline_id,
            wu["id"],
            proposal,
            source="agent",
            idempotency_key=f"v6-ablation-prompt-{index}",
            wake_id=wake_id,
        )
        results.append(
            [event["event_type"] for event in runtime.commit_pending_moment(worldline_id)["events"]]
        )

    assert all("DELIBERATION_COMMITTED" in event_types for event_types in results)
    assert all("DECISION_HORIZON_HELD" in event_types for event_types in results)
    assert all("OPERATION_STARTED" not in event_types for event_types in results)


def test_fixed_pressure_ablation_keeps_source_pressure_load_bearing(app_config):
    outcomes = {}
    for suffix, include_pressure in (("with-pressure", True), ("without-pressure", False)):
        config = replace(
            app_config,
            database_path=app_config.database_path.with_name(f"chronicle-v6-ablation-{suffix}.db"),
            runtime_dir=app_config.runtime_dir / f"v6-ablation-{suffix}",
            hermes_home=app_config.hermes_home / f"v6-ablation-{suffix}",
        )
        host = ChronicleHost(config)
        runtime = host.volume_runtime
        if not include_pressure:
            packs = dict(runtime.pack.packs)
            shanhai = packs["before-shanhaiguan"]
            packs["before-shanhaiguan"] = replace(
                shanhai,
                crisis=shanhai.crisis.model_copy(update={"pressures": []}),
            )
            runtime.pack = replace(runtime.pack, packs=packs)
        worldline_id = runtime.create()["worldline"]["id"]
        runtime.activate_crisis(worldline_id, "before-shanhaiguan")
        events = []
        for _ in range(3):
            events.extend(runtime.advance_one(worldline_id)["events"])
        outcomes[suffix] = {
            "status": runtime.db.crisis_instance(
                f"{worldline_id}:crisis:before-shanhaiguan"
            )["status"],
            "pressure_events": [
                event
                for event in events
                if event["event_type"] == "CRISIS_PRESSURE_APPLIED"
                and event["payload"].get("crisis_id") == "before-shanhaiguan"
            ],
        }

    assert outcomes["with-pressure"]["status"] == "SETTLED"
    assert outcomes["with-pressure"]["pressure_events"]
    assert outcomes["without-pressure"]["status"] == "ACTIVE"
    assert outcomes["without-pressure"]["pressure_events"] == []

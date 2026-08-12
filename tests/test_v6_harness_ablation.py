from __future__ import annotations

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

    assert runtime.db.crisis_wake_operations(wake_id) == []
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

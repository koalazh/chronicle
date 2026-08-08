from __future__ import annotations

import pytest

from chronicle.host import BranchEngine
from chronicle.models import ActionType, BranchAction


def test_branch_enforces_authority_and_message_delay(host):
    host.set_tick(host.pack.event_by_id[host.pack.fork.event_id].tick)
    engine = BranchEngine(host)
    branch = engine.create()
    branch_id = branch["id"]

    rejected = engine.step(branch_id, "B", BranchAction(type=ActionType.MOVE_PRINCIPAL, target="capital"))
    assert rejected["result"]["status"] == "rejected"
    assert rejected["branch"]["tick"] == 44

    accepted = engine.step(
        branch_id,
        "A",
        BranchAction(type=ActionType.SEND_MESSAGE, recipient="C", payload="Confirm your position."),
    )
    assert accepted["result"]["status"] == "accepted"
    assert accepted["branch"]["tick"] == 45
    message = accepted["branch"]["state_json"]["messages"][0]
    assert message["status"] == "in_transit"
    assert message["delivery_tick"] == 50


def test_branch_stops_at_fourteen_simulated_days(host):
    host.set_tick(host.pack.event_by_id[host.pack.fork.event_id].tick)
    engine = BranchEngine(host)
    branch = engine.create()
    for _ in range(14):
        branch = engine.step(branch["id"], "A", BranchAction(type=ActionType.WAIT))["branch"]
    assert branch["status"] == "boundary"
    assert branch["state_json"]["day_offset"] == 14
    assert branch["boundary_reason"] == "14 simulated days reached"


def test_branch_creation_is_gated_by_canon_tick_and_unique_fork(host):
    engine = BranchEngine(host)

    with pytest.raises(ValueError, match="fork"):
        engine.create()

    host.set_tick(host.pack.event_by_id[host.pack.fork.event_id].tick)
    engine.create()

    with pytest.raises(ValueError, match="already exists"):
        engine.create()


def test_branch_rejects_unroutable_message_and_keeps_canon_future_out(host):
    host.set_tick(host.pack.event_by_id[host.pack.fork.event_id].tick)
    engine = BranchEngine(host)
    branch = engine.create()

    rejected = engine.step(
        branch["id"],
        "A",
        BranchAction(type=ActionType.SEND_MESSAGE, recipient="B", payload="No direct road."),
    )
    assert rejected["result"]["status"] == "rejected"
    assert rejected["branch"]["tick"] == 44

    branch = engine.step(branch["id"], "A", BranchAction(type=ActionType.WAIT))["branch"]
    branch = engine.step(branch["id"], "A", BranchAction(type=ActionType.WAIT))["branch"]
    assert branch["tick"] == 46
    assert branch["state_json"]["world"]["last_event_id"] == "e019"

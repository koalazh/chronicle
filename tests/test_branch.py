from __future__ import annotations

from chronicle.host import BranchEngine
from chronicle.models import ActionType, BranchAction


def test_branch_enforces_authority_and_message_delay(host):
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
    assert message["delivery_tick"] == 46


def test_branch_stops_at_fourteen_simulated_days(host):
    engine = BranchEngine(host)
    branch = engine.create()
    for _ in range(14):
        branch = engine.step(branch["id"], "A", BranchAction(type=ActionType.WAIT))["branch"]
    assert branch["status"] == "boundary"
    assert branch["state_json"]["day_offset"] == 14
    assert branch["boundary_reason"] == "14 simulated days reached"

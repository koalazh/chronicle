from __future__ import annotations

from pathlib import Path

from chronicle.crisis import CrisisPack, HistoricalPolicy, validate_crisis_pack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRISIS_ROOT = PROJECT_ROOT / "scenarios" / "jiashen" / "crises" / "before-shanhaiguan"


def test_before_shanhaiguan_crisis_pack_is_complete():
    pack = CrisisPack.load(CRISIS_ROOT)

    assert pack.crisis.id == "before-shanhaiguan"
    assert set(pack.actor_by_id) == {"li-zicheng", "wu-sangui", "dorgon"}
    assert pack.crisis.checkpoint.safety_horizon_days == 9
    assert pack.crisis.simulation_boundary.maximum_tick == 9
    assert [place.id for place in pack.crisis.corridor] == [
        "beijing",
        "yongping",
        "shanhaiguan",
        "liaoxi",
    ]
    assert {source.work for source in pack.sources}.issuperset(
        {"《清实录·世祖章皇帝实录》", "《明季北略》", "《清史稿》"}
    )
    assert validate_crisis_pack(CRISIS_ROOT)[0].startswith("Crisis Pack valid")
    visible_claims = "\n".join(assertion.claim for assertion in pack.assertions)
    assert not any(
        term in visible_claims
        for term in ("Runtime", "checkpoint", "Run ", " tick", "Crisis", "Battle Resolver")
    )
    assert "Battle Resolver" not in pack.crisis.simulation_boundary.reason


def test_checkpoint_preserves_private_perspectives_and_unresolved_choices():
    pack = CrisisPack.load(CRISIS_ROOT)
    li = pack.initial_perspective("li-zicheng")
    wu = pack.initial_perspective("wu-sangui")
    dorgon = pack.initial_perspective("dorgon")

    assert li["location"] == "beijing"
    assert wu["location"] == "shanhaiguan"
    assert dorgon["location"] == "liaoxi"
    assert li["knowledge"] != wu["knowledge"] != dorgon["knowledge"]
    assert all("已经决定" not in item for item in pack.crisis.checkpoint.unresolved)
    assert {message.recipient for message in pack.crisis.checkpoint.in_transit} == {
        "wu-sangui",
        "dorgon",
    }


def test_post_checkpoint_actor_history_is_reference_only():
    pack = CrisisPack.load(CRISIS_ROOT)

    actor_anchors = [anchor for anchor in pack.crisis.anchors if anchor.actor_ids]
    assert actor_anchors
    assert all(anchor.policy == HistoricalPolicy.REFERENCE_ONLY for anchor in actor_anchors)
    assert all(
        "x" not in type(place).model_fields and "y" not in type(place).model_fields
        for place in pack.crisis.corridor
    )

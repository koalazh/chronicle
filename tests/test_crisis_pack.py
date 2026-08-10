from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from chronicle.crisis import (
    CrisisPack,
    CrisisSurfaceKind,
    CrisisValidationError,
    HistoricalPolicy,
    VolumeRegistry,
    validate_crisis_pack,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRISIS_ROOT = PROJECT_ROOT / "scenarios" / "jiashen" / "crises" / "before-shanhaiguan"


def _write_generic_crisis(root: Path, actor_ids: list[str]) -> None:
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    template = crisis["actors"][0]
    crisis["actors"] = []
    for actor_id in actor_ids:
        actor = copy.deepcopy(template)
        actor["id"] = actor_id
        actor["display_name"] = actor_id
        crisis["actors"].append(actor)
    crisis["playable_actor_ids"] = [actor_ids[0]]
    crisis["checkpoint"]["in_transit"] = []
    crisis["anchors"] = []
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


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


def test_spatial_surface_projects_locations_and_only_visible_actors():
    pack = CrisisPack.load(CRISIS_ROOT)

    surface = pack.surface_projection(
        {
            "positions": {
                "li-zicheng": "beijing",
                "wu-sangui": "shanhaiguan",
                "dorgon": "liaoxi",
            },
            "messages": [{"id": "letter-1", "status": "in_transit"}],
            "movements": [{"actor_id": "dorgon", "status": "in_transit"}],
        },
        visible_actor_ids={"wu-sangui"},
    )

    assert pack.crisis.surface.kind == CrisisSurfaceKind.SPATIAL
    assert surface["kind"] == "SPATIAL"
    assert [location["id"] for location in surface["locations"]] == [
        "beijing",
        "yongping",
        "shanhaiguan",
        "liaoxi",
    ]
    assert surface["actors"] == [
        {
            "id": "wu-sangui",
            "display_name": "吴三桂",
            "location": "shanhaiguan",
            "in_transit": False,
        }
    ]
    assert surface["messages"] == []


def test_volume_registry_declares_the_current_crisis_without_a_global_actor_set():
    registry = VolumeRegistry.load(PROJECT_ROOT / "scenarios" / "jiashen")

    assert registry.volume.id == "jiashen"
    assert registry.default_pack.crisis.id == "before-shanhaiguan"
    assert registry.default_pack.crisis.playable_actor_ids == [
        "wu-sangui",
        "li-zicheng",
        "dorgon",
    ]
    assert registry.summary()["crises"][0]["id"] == "before-shanhaiguan"


@pytest.mark.parametrize("actor_count", [2, 3, 5])
def test_crisis_pack_supports_a_generic_two_to_five_actor_cast(tmp_path, actor_count):
    actor_ids = [f"actor-{index}" for index in range(actor_count)]
    root = tmp_path / f"crisis-{actor_count}"
    _write_generic_crisis(root, actor_ids)

    pack = CrisisPack.load(root)

    assert [actor.id for actor in pack.crisis.actors] == actor_ids
    assert pack.crisis.playable_actor_ids == [actor_ids[0]]


def test_crisis_pack_rejects_a_playable_actor_that_is_not_in_the_cast(tmp_path):
    root = tmp_path / "invalid-playable"
    _write_generic_crisis(root, ["actor-a", "actor-b"])
    crisis = yaml.safe_load((root / "crisis.yaml").read_text(encoding="utf-8"))
    crisis["playable_actor_ids"] = ["not-an-actor"]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(CrisisValidationError, match="playable_actor_ids: unknown actors"):
        CrisisPack.load(root)


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

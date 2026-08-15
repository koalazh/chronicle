from __future__ import annotations

from pathlib import Path

from chronicle.crisis import VolumePack

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOLUME_ROOT = PROJECT_ROOT / "scenarios" / "jiashen"


def test_volume_pack_owns_lifetimes_shared_world_and_crisis_participants():
    pack = VolumePack.load(VOLUME_ROOT)

    assert set(pack.lifetimes) == {
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    }
    assert len(pack.world.locations) == 12
    assert len(pack.world.routes) == 12
    assert pack.world.resolve_location("beijing") == "capital"

    assert pack.pack("before-shanhaiguan").participant_ids == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]
    before_participants = pack.participants("before-shanhaiguan")
    assert [participant.id for participant in before_participants] == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]
    assert before_participants[1].lifetime.display_name == "吴三桂"
    assert before_participants[1].overlay.initial_location == "shanhaiguan"


def test_active_world_catalog_combines_shared_world_and_existing_crisis_affordances():
    pack = VolumePack.load(VOLUME_ROOT)
    catalog = pack.active_catalog(["before-shanhaiguan"])

    assert catalog.world is pack.world
    assert catalog.crisis_ids == ("before-shanhaiguan",)
    affordances = catalog.affordance_catalog()
    assert affordances["crisis_ids"] == ["before-shanhaiguan"]
    assert "prepare_force" in affordances["operations"]["before-shanhaiguan"]
    assert affordances["investigations"]["before-shanhaiguan"]
    assert affordances["pressures"]["before-shanhaiguan"]

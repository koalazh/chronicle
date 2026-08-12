from __future__ import annotations

from pathlib import Path

from chronicle.crisis import VolumePack, VolumeRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOLUME_ROOT = PROJECT_ROOT / "scenarios" / "jiashen"


def test_volume_pack_owns_lifetimes_shared_world_and_crisis_participants():
    pack = VolumePack.load(VOLUME_ROOT)

    assert VolumeRegistry is VolumePack
    assert set(pack.lifetimes) == {
        "li-zicheng",
        "wu-sangui",
        "dorgon",
        "shi-kefa",
        "ma-shiying",
        "han-zanzhou",
    }
    assert len(pack.world.locations) == 15
    assert len(pack.world.routes) == 16
    assert pack.world.resolve_location("beijing") == "capital"

    assert pack.pack("before-shanhaiguan").participant_ids == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]
    assert pack.pack("nanjing-succession").participant_ids == [
        "shi-kefa",
        "ma-shiying",
        "han-zanzhou",
    ]
    assert pack.pack("southern-consolidation").participant_ids == [
        "shi-kefa",
        "ma-shiying",
        "han-zanzhou",
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
    catalog = pack.active_catalog(
        ["before-shanhaiguan", "nanjing-succession", "southern-consolidation"]
    )

    assert catalog.world is pack.world
    assert catalog.crisis_ids == (
        "before-shanhaiguan",
        "nanjing-succession",
        "southern-consolidation",
    )
    affordances = catalog.affordance_catalog()
    assert affordances["crisis_ids"] == [
        "before-shanhaiguan",
        "nanjing-succession",
        "southern-consolidation",
    ]
    assert "prepare_force" in affordances["operations"]["before-shanhaiguan"]
    assert "convene_recognition_assembly" in affordances["operations"]["nanjing-succession"]
    assert affordances["investigations"]["before-shanhaiguan"]
    assert affordances["offer_terms"]["nanjing-succession"]
    assert affordances["pressures"]["before-shanhaiguan"]
    assert "draft-jiangbei-mandate" in affordances["operations"]["southern-consolidation"]

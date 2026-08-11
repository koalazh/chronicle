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
        actor["asset_ids"] = []
        crisis["actors"].append(actor)
    crisis["playable_actor_ids"] = [actor_ids[0]]
    crisis["checkpoint"]["in_transit"] = []
    crisis["anchors"] = []
    crisis["entities"] = []
    crisis["operations"] = []
    crisis["investigations"] = []
    crisis["offer_terms"] = []
    crisis["pressures"] = []
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
    assert pack.crisis.checkpoint.safety_horizon_days == 30
    assert pack.crisis.simulation_boundary.maximum_tick == 30
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


def test_political_surface_projects_known_and_hidden_world_facts(tmp_path):
    root = tmp_path / "political-surface"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["surface"] = {
        "kind": "POLITICAL",
        "title": "未定的政治事实",
        "description": "主体、承认与支持仍须分别确认。",
        "subject_ids": ["shanhai-pass"],
        "context_entity_ids": ["wu-field-force"],
    }
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    pack = CrisisPack.load(root)
    world = pack.surface_projection(
        {
            "entities": {
                "shanhai-pass": {"state": "CONTESTED"},
                "wu-field-force": {"state": "READY"},
            }
        }
    )
    private = pack.surface_projection(
        {
            "entities": {
                "shanhai-pass": {"state": "CONTESTED"},
                "wu-field-force": {"state": "READY"},
            }
        },
        visible_entity_ids={"shanhai-pass"},
    )
    uncertain = pack.surface_projection(
        {
            "entities": {
                "shanhai-pass": {"state": "CONTESTED"},
                "wu-field-force": {"state": "READY"},
            }
        },
        visible_entity_ids=set(),
    )

    assert world == {
        "kind": "POLITICAL",
        "title": "未定的政治事实",
        "description": "主体、承认与支持仍须分别确认。",
        "subjects": [
            {
                "id": "shanhai-pass",
                "type": "ASSET",
                "display_name": "山海关通道",
                "knowledge": "KNOWN",
                "state": "CONTESTED",
            }
        ],
        "context": [
            {
                "id": "wu-field-force",
                "type": "FORCE",
                "display_name": "关宁所部",
                "knowledge": "KNOWN",
                "state": "READY",
            }
        ],
    }
    assert private["subjects"] == world["subjects"]
    assert private["context"] == [
        {
            "id": "wu-field-force",
            "type": "FORCE",
            "display_name": "关宁所部",
            "knowledge": "UNKNOWN",
        }
    ]
    assert uncertain["subjects"] == [
        {
            "id": "shanhai-pass",
            "type": "ASSET",
            "display_name": "山海关通道",
            "knowledge": "UNCONFIRMED",
        }
    ]


@pytest.mark.parametrize(
    ("surface", "message"),
    [
        (
            {
                "kind": "POLITICAL",
                "title": "未定的政治事实",
                "context_entity_ids": ["wu-field-force"],
            },
            "surface: POLITICAL requires subject_ids",
        ),
        (
            {
                "kind": "POLITICAL",
                "title": "未定的政治事实",
                "subject_ids": ["shanhai-pass"],
                "context_entity_ids": ["missing-entity"],
            },
            "surface: POLITICAL references unknown entities missing-entity",
        ),
    ],
)
def test_political_surface_requires_referenced_entities(tmp_path, surface, message):
    root = tmp_path / "invalid-political-surface"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["surface"] = surface
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(CrisisValidationError, match=message):
        CrisisPack.load(root)


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


def test_crisis_pack_requires_a_registered_resolution_contract(tmp_path):
    root = tmp_path / "invalid-resolution-contract"
    _write_generic_crisis(root, ["actor-a", "actor-b"])
    crisis = yaml.safe_load((root / "crisis.yaml").read_text(encoding="utf-8"))
    crisis["resolution_contract"] = {"id": "missing-contract", "version": 1}
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="resolution contract missing-contract/v1 is not registered",
    ):
        CrisisPack.load(root)


def test_crisis_pack_validates_explicit_historical_compatibility_references(tmp_path):
    root = tmp_path / "invalid-compatibility-reference"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["anchors"][0]["compatibility_preconditions"] = [
        {
            "id": "missing-entity",
            "kind": "ENTITY_STATE",
            "subject": "missing-entity",
            "satisfied_values": ["OPEN"],
            "description": "引用一个不存在的世界对象。",
        }
    ]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="compatibility precondition missing-entity references unknown entity missing-entity",
    ):
        CrisisPack.load(root)


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


def test_crisis_pack_rejects_an_operation_reference_to_a_missing_entity(tmp_path):
    root = tmp_path / "invalid-operation-reference"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["operations"][0]["preconditions"][0]["subject"] = "missing-force"
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="operation prepare_force: unknown precondition subject missing-force",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_an_investigation_reference_to_a_missing_entity(tmp_path):
    root = tmp_path / "invalid-investigation-reference"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["investigations"][0]["target_ids"] = ["missing-target"]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="investigation shanhai-pass-report: unknown targets missing-target",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_an_investigation_without_known_provenance(tmp_path):
    root = tmp_path / "invalid-investigation-provenance"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["investigations"][0]["observation"]["source_ids"] = ["missing-source"]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="investigation shanhai-pass-report: unknown observation sources missing-source",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_an_offer_term_with_an_unknown_subject(tmp_path):
    root = tmp_path / "invalid-offer-subject"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["offer_terms"][0]["subject"] = "missing-pass"
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(CrisisValidationError, match="offer term passage: unknown subject missing-pass"):
        CrisisPack.load(root)


def test_crisis_pack_rejects_an_operation_agreement_that_is_not_declared(tmp_path):
    root = tmp_path / "invalid-operation-agreement"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["operations"][1]["agreement_requirements"][0]["value"] = "denied"
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="operation enter-shanhai-pass: unknown agreement requirement passage/shanhai-pass",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_an_exogenous_pressure_with_actor_state_preconditions(tmp_path):
    root = tmp_path / "invalid-exogenous-pressure"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["pressures"][0]["preconditions"] = [
        {"subject": "wu-field-force", "states": ["READY"]}
    ]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="pressure eastern-transit-window-narrows: EXOGENOUS pressure cannot have preconditions",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_a_pressure_effect_for_a_missing_entity(tmp_path):
    root = tmp_path / "invalid-pressure-effect"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["pressures"][0]["effects"][0]["subject"] = "missing-window"
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="pressure eastern-transit-window-narrows: unknown effect subject missing-window",
    ):
        CrisisPack.load(root)


def test_crisis_pack_rejects_a_pressure_that_injects_decision_actor_history(tmp_path):
    root = tmp_path / "invalid-pressure-history"
    root.mkdir()
    crisis = yaml.safe_load((CRISIS_ROOT / "crisis.yaml").read_text(encoding="utf-8"))
    source = yaml.safe_load((CRISIS_ROOT / "sources.yaml").read_text(encoding="utf-8"))
    crisis["pressures"][0]["assertion_ids"] = ["c006"]
    (root / "crisis.yaml").write_text(
        yaml.safe_dump(crisis, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "sources.yaml").write_text(
        yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        CrisisValidationError,
        match="pressure eastern-transit-window-narrows: cannot inject Decision Actor historical anchors c006",
    ):
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

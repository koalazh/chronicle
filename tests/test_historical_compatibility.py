from __future__ import annotations

import copy
import json

from chronicle.compatibility import evaluate_historical_compatibility
from chronicle.crisis_runtime import CrisisRunEngine, RunMode


def _world(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    world = copy.deepcopy(engine.db.worldline_snapshot(run_id)["projection"])
    engine.seal(run_id, "compatibility-fixture")
    return engine.pack, world


def _by_anchor(pack, world):
    return {
        item["anchor_id"]: item
        for item in evaluate_historical_compatibility(pack, world)
    }


def test_historical_compatibility_is_explicit_and_deterministic(app_config):
    pack, world = _world(app_config)
    world["positions"]["dorgon"] = "shanhaiguan"
    world["entities"]["shanhai-pass"]["state"] = "OPEN"
    world["entities"]["shun-eastern-force"]["state"] = "COMMITTED"

    first = _by_anchor(pack, world)
    repeated = _by_anchor(pack, copy.deepcopy(world))

    assert first["historical-dorgon-reply"]["status"] == "UNKNOWN"
    assert first["historical-li-eastward-march"]["status"] == "COMPATIBLE"
    assert first["historical-shanhai-battle"]["status"] == "COMPATIBLE"
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        repeated, ensure_ascii=False, sort_keys=True
    )
    assert "必然发生" in first["historical-shanhai-battle"]["summary"]


def test_historical_compatibility_marks_unsettled_preconditions_as_contingent(app_config):
    pack, world = _world(app_config)
    world["positions"]["dorgon"] = "shanhaiguan"
    world["entities"]["shanhai-pass"]["state"] = "OPEN"
    world["entities"]["shun-eastern-force"]["state"] = "DISPERSED"

    result = _by_anchor(pack, world)["historical-shanhai-battle"]

    assert result["status"] == "CONTINGENT"
    assert {
        item["status"] for item in result["preconditions"]
    } == {"COMPATIBLE", "CONTINGENT"}


def test_historical_compatibility_invalidates_only_explicitly_lost_prerequisites(app_config):
    pack, world = _world(app_config)
    world["positions"]["dorgon"] = "shanhaiguan"
    world["entities"]["shanhai-pass"]["state"] = "CLOSED"
    world["entities"]["shun-eastern-force"]["state"] = "COMMITTED"

    result = _by_anchor(pack, world)["historical-shanhai-battle"]

    assert result["status"] == "INVALIDATED"
    access = next(
        item
        for item in result["preconditions"]
        if item["id"] == "qing-pass-access-remains-possible"
    )
    assert access["actual_value"] == "CLOSED"
    assert access["status"] == "INVALIDATED"

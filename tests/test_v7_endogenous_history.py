from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest

from chronicle.host import ChronicleHost
from chronicle.volume_boundary import VolumeBoundaryPolicy
from chronicle.volume_runtime import VOLUME_CONTENT_VERSION, VolumeRuntimeConflict

_ACTIVE_WAKE_STATUSES = {"QUEUED", "WAITING_HUMAN", "STAGED", "RUNNING"}


def _tick(runtime: Any, worldline_id: str) -> int:
    row = runtime.db.worldline(worldline_id)
    assert row is not None
    return int(row["current_tick"])


def _ensure_test_wake(runtime: Any, worldline_id: str, actor_id: str, tag: str) -> str:
    tick = _tick(runtime, worldline_id)
    existing = next(
        (
            wake
            for wake in runtime.db.subject_wakes(worldline_id, tick=tick)
            if wake["actor_id"] == actor_id and wake["status"] in _ACTIVE_WAKE_STATUSES
        ),
        None,
    )
    if existing is not None:
        return str(existing["id"])
    wake = runtime.db.create_subject_wake(
        {
            "id": f"{worldline_id}:v7:{tag}:{actor_id}:{tick}",
            "worldline_id": worldline_id,
            "actor_id": actor_id,
            "wake_type": "V7_TEST_ACTION",
            "tick": tick,
            "status": "QUEUED",
            "source": "v7-deterministic-test",
        }
    )
    return str(wake["id"])


def _run_moment(
    runtime: Any,
    worldline_id: str,
    actions: dict[str, tuple[str, dict[str, Any]]],
    tag: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    for actor_id in actions:
        _ensure_test_wake(runtime, worldline_id, actor_id, tag)
    frozen = runtime.freeze_pending_moment(worldline_id)
    staged: dict[str, dict[str, Any]] = {}
    used_actors: set[str] = set()
    for wake_id in frozen["pending_moment"]["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        actor_id = str(wake["actor_id"])
        lifetime = runtime.db.worldline_lifetime(worldline_id, actor_id)
        assert lifetime is not None
        action = actions.get(actor_id)
        if action is not None and actor_id not in used_actors:
            tool_name, arguments = action
            staged[actor_id] = runtime.stage_actor_tool(
                worldline_id,
                lifetime["id"],
                tool_name,
                arguments,
                source="agent",
                idempotency_key=f"{tag}:{actor_id}:{_tick(runtime, worldline_id)}",
                wake_id=wake_id,
            )
            used_actors.add(actor_id)
        else:
            runtime.stage_intent(
                worldline_id,
                lifetime["id"],
                {"type": "wait"},
                source="agent",
                idempotency_key=f"{tag}:wait:{wake_id}",
                wake_id=wake_id,
            )
    return staged, runtime.commit_pending_moment(worldline_id)


def _resolve_current_wakes(runtime: Any, worldline_id: str, tag: str) -> None:
    tick = _tick(runtime, worldline_id)
    if any(
        wake["status"] in _ACTIVE_WAKE_STATUSES
        for wake in runtime.db.subject_wakes(worldline_id, tick=tick)
    ):
        _run_moment(runtime, worldline_id, {}, f"{tag}-wait-{tick}")


def _advance_to(runtime: Any, worldline_id: str, target_tick: int, tag: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while _tick(runtime, worldline_id) < target_tick:
        _resolve_current_wakes(runtime, worldline_id, tag)
        next_tick = runtime.next_tick(worldline_id)
        assert next_tick is not None
        advanced = runtime.advance_one(worldline_id)
        events.extend(advanced["events"])
        assert _tick(runtime, worldline_id) <= target_tick
    return events


def _operate(
    runtime: Any,
    worldline_id: str,
    actor_id: str,
    definition_id: str,
    targets: list[str],
    tag: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            actor_id: (
                "operate",
                {
                    "operation_definition_id": definition_id,
                    "targets": targets,
                    "description": tag,
                },
            )
        },
        tag,
    )
    result = staged[actor_id]
    assert result["status"] == "accepted", result
    expected_tick = int(result["operation"]["result"]["expected_complete_tick"])
    events = _advance_to(runtime, worldline_id, expected_tick, tag)
    return result, events


def _north_runtime(host: Any) -> tuple[Any, str]:
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    return runtime, worldline_id


def _fresh_host(app_config: Any, tag: str) -> Any:
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v7-{tag}.db"),
        runtime_dir=app_config.runtime_dir / f"v7-{tag}",
        hermes_home=app_config.hermes_home / f"v7-{tag}",
    )
    return ChronicleHost(config)


def _north_li_actions(runtime: Any, worldline_id: str, tag: str = "li") -> None:
    _operate(runtime, worldline_id, "li-zicheng", "prepare_force", ["shun-eastern-force"], "li-prepare")
    _operate(
        runtime,
        worldline_id,
        "li-zicheng",
        "move_force",
        ["shun-eastern-force", "yongping"],
        f"{tag}-move-yongping",
    )
    _advance_to(runtime, worldline_id, 9, f"{tag}-field")


def _north_li_branch(host: Any) -> tuple[Any, str, list[dict[str, Any]]]:
    runtime, worldline_id = _north_runtime(host)
    _north_li_actions(runtime, worldline_id)
    return runtime, worldline_id, runtime.db.worldline_events(worldline_id)


def _north_dorgon_actions(runtime: Any, worldline_id: str, tag: str = "dorgon") -> None:
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            "wu-sangui": (
                "manage_offer",
                {
                    "action": "PROPOSE",
                    "recipient": "dorgon",
                    "terms": [{"type": "passage", "subject": "shanhai-pass", "value": "permitted"}],
                    "message": "按公开条件通行山海关。",
                    "expires_after_days": 6,
                },
            ),
            "dorgon": (
                "operate",
                {
                    "operation_definition_id": "prepare_force",
                    "targets": ["qing-expedition-force"],
                    "description": "整备清军主力",
                },
            ),
        },
        f"{tag}-prepare-offer",
    )
    offer_id = str(staged["wu-sangui"]["operation"]["result"]["offer_id"])
    _advance_to(runtime, worldline_id, 2, f"{tag}-offer")
    _run_moment(
        runtime,
        worldline_id,
        {"dorgon": ("manage_offer", {"action": "ACCEPT", "offer_id": offer_id})},
        f"{tag}-accept",
    )
    _advance_to(runtime, worldline_id, 4, f"{tag}-agreement")
    _operate(
        runtime,
        worldline_id,
        "dorgon",
        "enter-shanhai-pass",
        ["qing-expedition-force", "shanhaiguan"],
        f"{tag}-enter-shanhai",
    )
    _advance_to(runtime, worldline_id, 9, f"{tag}-field")


def _north_dorgon_branch(host: Any) -> tuple[Any, str, list[dict[str, Any]]]:
    runtime, worldline_id = _north_runtime(host)
    _north_dorgon_actions(runtime, worldline_id)
    return runtime, worldline_id, runtime.db.worldline_events(worldline_id)


def _field_message(runtime: Any) -> dict[str, Any]:
    return copy.deepcopy(runtime.pack.world.historical_field[0]["messages"][0])


def _nanjing_runtime(host: Any) -> tuple[Any, str]:
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    return runtime, worldline_id


def _nanjing_offer_setup(
    runtime: Any, worldline_id: str, supporter: str, subject: str, tag: str
) -> None:
    terms = [{"type": "endorsement", "subject": subject, "value": "public_support"}]
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            supporter: (
                "manage_offer",
                {
                    "action": "PROPOSE",
                    "recipient": "han-zanzhou",
                    "terms": terms,
                    "message": f"公开支持{subject}进入南京程序。",
                    "expires_after_days": 8,
                },
            ),
            "han-zanzhou": (
                "operate",
                {
                    "operation_definition_id": "convene_recognition_assembly",
                    "targets": ["nanjing-court"],
                    "description": "召集南京继统议程",
                },
            ),
        },
        f"{tag}-offer-convene",
    )
    offer_id = str(staged[supporter]["operation"]["result"]["offer_id"])
    current_tick = _tick(runtime, worldline_id)
    _advance_to(
        runtime,
        worldline_id,
        max(1, current_tick + 1 if current_tick >= 1 else 1),
        f"{tag}-convene",
    )
    _run_moment(
        runtime,
        worldline_id,
        {"han-zanzhou": ("manage_offer", {"action": "ACCEPT", "offer_id": offer_id})},
        f"{tag}-accept",
    )
    _advance_to(runtime, worldline_id, max(2, _tick(runtime, worldline_id)), f"{tag}-agreement")


def _nanjing_fu_actions(runtime: Any, worldline_id: str, tag: str = "fu") -> None:
    _nanjing_offer_setup(runtime, worldline_id, "ma-shiying", "fu-prince", tag)
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "make_fu_backing_visible",
        ["jiangbei-military-backing"],
        f"{tag}-backing",
    )
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "arrange_fu_entry",
        ["fu-prince"],
        f"{tag}-entry",
    )
    _operate(
        runtime,
        worldline_id,
        "han-zanzhou",
        "formalize_fu_regency",
        ["fu-prince", "nanjing-court", "nanjing-recognition"],
        f"{tag}-recognition",
    )


def _nanjing_fu_branch(host: Any) -> tuple[Any, str]:
    runtime, worldline_id = _nanjing_runtime(host)
    _nanjing_fu_actions(runtime, worldline_id)
    return runtime, worldline_id


def _nanjing_lu_actions(runtime: Any, worldline_id: str, tag: str = "lu") -> None:
    _nanjing_offer_setup(runtime, worldline_id, "shi-kefa", "lu-prince", tag)
    _operate(
        runtime,
        worldline_id,
        "shi-kefa",
        "arrange_lu_entry",
        ["lu-prince"],
        f"{tag}-entry",
    )
    _operate(
        runtime,
        worldline_id,
        "han-zanzhou",
        "formalize_lu_regency",
        ["lu-prince", "nanjing-court", "nanjing-recognition"],
        f"{tag}-recognition",
    )


def _nanjing_lu_branch(host: Any) -> tuple[Any, str]:
    runtime, worldline_id = _nanjing_runtime(host)
    _nanjing_lu_actions(runtime, worldline_id)
    return runtime, worldline_id


def _nanjing_contested_branch(host: Any) -> tuple[Any, str]:
    runtime, worldline_id = _nanjing_runtime(host)
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            "ma-shiying": (
                "manage_offer",
                {
                    "action": "PROPOSE",
                    "recipient": "han-zanzhou",
                    "terms": [{"type": "endorsement", "subject": "fu-prince", "value": "public_support"}],
                    "message": "公开支持福王。",
                    "expires_after_days": 10,
                },
            ),
            "shi-kefa": (
                "manage_offer",
                {
                    "action": "PROPOSE",
                    "recipient": "han-zanzhou",
                    "terms": [{"type": "endorsement", "subject": "lu-prince", "value": "public_support"}],
                    "message": "公开支持潞王。",
                    "expires_after_days": 10,
                },
            ),
            "han-zanzhou": (
                "operate",
                {
                    "operation_definition_id": "convene_recognition_assembly",
                    "targets": ["nanjing-court"],
                    "description": "召集南京继统议程",
                },
            ),
        },
        "contested-offers",
    )
    fu_offer = str(staged["ma-shiying"]["operation"]["result"]["offer_id"])
    lu_offer = str(staged["shi-kefa"]["operation"]["result"]["offer_id"])
    _advance_to(runtime, worldline_id, 1, "contested-convene")
    _run_moment(
        runtime,
        worldline_id,
        {"han-zanzhou": ("manage_offer", {"action": "ACCEPT", "offer_id": fu_offer})},
        "contested-accept-fu",
    )
    _advance_to(runtime, worldline_id, 2, "contested-agreement-fu")
    _run_moment(
        runtime,
        worldline_id,
        {"han-zanzhou": ("manage_offer", {"action": "ACCEPT", "offer_id": lu_offer})},
        "contested-accept-lu",
    )
    _advance_to(runtime, worldline_id, 3, "contested-agreement-lu")
    _run_moment(
        runtime,
        worldline_id,
        {
            "ma-shiying": (
                "operate",
                {
                    "operation_definition_id": "make_fu_backing_visible",
                    "targets": ["jiangbei-military-backing"],
                    "description": "使福王一侧支持可见",
                },
            ),
            "shi-kefa": (
                "operate",
                {
                    "operation_definition_id": "arrange_lu_entry",
                    "targets": ["lu-prince"],
                    "description": "安排潞王进入南京程序",
                },
            ),
        },
        "contested-entry-preparation",
    )
    _advance_to(runtime, worldline_id, 4, "contested-entry-prepared")
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "arrange_fu_entry",
        ["fu-prince"],
        "contested-fu-entry",
    )
    _advance_to(runtime, worldline_id, 6, "contested-resolution")
    return runtime, worldline_id


def _nanjing_fragmented_branch(host: Any) -> tuple[Any, str]:
    runtime, worldline_id = _nanjing_runtime(host)
    _operate(
        runtime,
        worldline_id,
        "han-zanzhou",
        "convene_recognition_assembly",
        ["nanjing-court"],
        "fragmented-convene",
    )
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "make_fu_backing_visible",
        ["jiangbei-military-backing"],
        "fragmented-backing",
    )
    _run_moment(
        runtime,
        worldline_id,
        {
            "ma-shiying": (
                "operate",
                {
                    "operation_definition_id": "arrange_fu_entry",
                    "targets": ["fu-prince"],
                    "description": "安排福王进入南京程序",
                },
            ),
            "shi-kefa": (
                "operate",
                {
                    "operation_definition_id": "arrange_lu_entry",
                    "targets": ["lu-prince"],
                    "description": "安排潞王进入南京程序",
                },
            ),
        },
        "fragmented-entry",
    )
    _advance_to(runtime, worldline_id, 4, "fragmented-resolution")
    return runtime, worldline_id


def _nanjing_deferred_branch(host: Any) -> tuple[Any, str]:
    runtime, worldline_id = _nanjing_runtime(host)
    _operate(
        runtime,
        worldline_id,
        "han-zanzhou",
        "convene_recognition_assembly",
        ["nanjing-court"],
        "deferred-convene",
    )
    _advance_to(runtime, worldline_id, 7, "deferred-pressure")
    _operate(
        runtime,
        worldline_id,
        "han-zanzhou",
        "defer_recognition_procedure",
        ["nanjing-court", "nanjing-recognition"],
        "deferred-recognition",
    )
    return runtime, worldline_id


def _southern_coordination_actions(runtime: Any, worldline_id: str, tag: str = "southern") -> None:
    _operate(
        runtime,
        worldline_id,
        "shi-kefa",
        "draft-jiangbei-mandate",
        ["jiangbei-mandate"],
        f"{tag}-draft",
    )
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "coordinate-jiangbei-command",
        ["jiangbei-command", "jiangbei-mandate"],
        f"{tag}-coordinate",
    )


def _terminalize_all(
    runtime: Any,
    worldline_id: str,
    reason: str = "v7-test-terminal",
    *,
    reconcile: bool = True,
) -> None:
    if reconcile:
        runtime.reconcile_crisis_envelopes(worldline_id)
    for crisis_id in sorted(runtime.pack.packs):
        instance = next(
            item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == crisis_id
        )
        if instance["status"] in {"ACTIVE", "RESOLUTION_PENDING", "AFTERMATH"}:
            runtime.settle_crisis(worldline_id, crisis_id, outcome={"summary": reason})
        elif instance["status"] == "DORMANT":
            runtime._suppress_dormant_crisis(worldline_id, crisis_id, reason)


def _drain_to_boundary(runtime: Any, worldline_id: str, tag: str) -> None:
    while True:
        _resolve_current_wakes(runtime, worldline_id, tag)
        if runtime.next_tick(worldline_id) is None:
            _resolve_current_wakes(runtime, worldline_id, f"{tag}-final")
            assert not [
                wake
                for wake in runtime.db.subject_wakes(worldline_id)
                if wake["status"] in _ACTIVE_WAKE_STATUSES
            ]
            return
        runtime.advance_one(worldline_id)


def test_v7_current_content_can_continue(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]

    current = runtime.worldline(worldline_id)

    assert current["worldline"]["volume_content_version"] == VOLUME_CONTENT_VERSION
    assert current["worldline"]["volume_content_hash"] == runtime._volume_content_hash()


def test_v7_content_hash_drift_fails_closed_without_rewriting_history(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]
    before_events = copy.deepcopy(runtime.db.worldline_events(worldline_id))
    before_snapshot = copy.deepcopy(
        runtime.db.worldline_snapshot(worldline_id, 0)["projection"]
    )
    runtime.pack = replace(
        runtime.pack,
        world=replace(
            runtime.pack.world,
            institutional_state={"content-drift": "OPEN"},
        ),
    )

    with pytest.raises(VolumeRuntimeConflict, match="different content semantics"):
        runtime.worldline(worldline_id)

    assert runtime.db.worldline_events(worldline_id) == before_events
    assert runtime.db.worldline_snapshot(worldline_id, 0)["projection"] == before_snapshot


def test_v7_content_version_drift_fails_closed(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    with host.db.transaction() as connection:
        connection.execute(
            "UPDATE worldlines SET volume_content_version = ? WHERE id = ?",
            (VOLUME_CONTENT_VERSION - 1, worldline_id),
        )

    with pytest.raises(VolumeRuntimeConflict, match="different content semantics"):
        runtime.next_tick(worldline_id)


def test_v7_live_reconcile_rejects_content_mismatch_before_profile_or_gateway_restore(
    app_config, monkeypatch
):
    calls: list[str] = []

    def fake_materialize(_config, worldline_id, lifetimes, **_kwargs):
        return {
            str(lifetime["id"]): {
                "profile": f"chronicle-{worldline_id}-{lifetime['id']}",
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{lifetime['id']}",
            }
            for lifetime in lifetimes
        }

    def unexpected_load(*_args, **_kwargs):
        calls.append("profile_load")
        raise AssertionError("profile restore must not run after content mismatch")

    def unexpected_gateway(*_args, **_kwargs):
        calls.append("gateway")
        raise AssertionError("gateway restore must not run after content mismatch")

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.hermes.load_lifetime_profile_records", unexpected_load)
    monkeypatch.setattr("chronicle.gateway.GatewayController.ensure", unexpected_gateway)

    runtime = ChronicleHost(app_config).volume_runtime
    created = runtime.create(runtime_mode="live")
    worldline_id = created["worldline"]["id"]
    runtime.pack = replace(
        runtime.pack,
        world=replace(
            runtime.pack.world,
            institutional_state={"content-drift": "OPEN"},
        ),
    )

    with pytest.raises(VolumeRuntimeConflict, match="different content semantics"):
        runtime.reconcile_live_runtime(worldline_id)

    assert calls == []


def test_v7_schema_remains_10(host):
    runtime = host.volume_runtime
    runtime.create()
    assert runtime.db.get_meta("schema_version") == "10"


def test_v7_position_report_is_a_narrow_exclusive_shape(pack):
    message = pack.world.historical_field[0]["messages"][0]
    assert "content" not in message
    assert set(message["position_report"]) == {"lifetime_ids"}
    assert len(message["position_report"]["lifetime_ids"]) == len(
        set(message["position_report"]["lifetime_ids"])
    )


def test_v7_07_real_li_move_yields_current_position_record(host):
    runtime, worldline_id, events = _north_li_branch(host)
    dispatches = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    ]
    assert dispatches
    assert "李自成现位于永平" in dispatches[0]["payload"]["content"]
    assert runtime.worldline(worldline_id)["projection"]["positions"]["li-zicheng"] == "yongping"


def test_v7_08_real_dorgon_move_yields_shanhai_position_record(host):
    runtime, worldline_id, events = _north_dorgon_branch(host)
    dispatches = [
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    ]
    assert dispatches
    assert "多尔衮现位于山海关" in dispatches[0]["payload"]["content"]
    assert runtime.worldline(worldline_id)["projection"]["positions"]["dorgon"] == "shanhaiguan"


def test_v7_09_real_branches_produce_different_records(app_config):
    _, _, li_events = _north_li_branch(_fresh_host(app_config, "branch-li"))
    _, _, dorgon_events = _north_dorgon_branch(_fresh_host(app_config, "branch-dorgon"))
    li_content = next(
        event["payload"]["content"]
        for event in li_events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    )
    dorgon_content = next(
        event["payload"]["content"]
        for event in dorgon_events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    )
    assert li_content != dorgon_content


def test_v7_10_unchanged_positions_apply_field_without_dispatch(host):
    runtime, worldline_id = _north_runtime(host)
    events = _advance_to(runtime, worldline_id, 9, "unchanged-field")
    assert any(event["event_type"] == "FIELD_EVENT_APPLIED" for event in events)
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
        for event in events
    )


def test_v7_11_return_to_genesis_does_not_resurrect_old_position(host):
    runtime, worldline_id, _ = _north_li_branch(host)
    projection = runtime.worldline(worldline_id)["projection"]
    projection = copy.deepcopy(projection)
    projection["positions"]["li-zicheng"] = "capital"
    message = _field_message(runtime)
    assert runtime._position_report_message(worldline_id, projection, message) is None


def test_v7_12_in_progress_movement_does_not_leak_destination(host):
    runtime, worldline_id = _north_runtime(host)
    _operate(runtime, worldline_id, "wu-sangui", "prepare_force", ["wu-field-force"], "moving-prepare")
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            "wu-sangui": (
                "operate",
                {
                    "operation_definition_id": "move_force",
                    "targets": ["wu-field-force", "yongping"],
                    "description": "沿线移动",
                },
            )
        },
        "moving-start",
    )
    assert staged["wu-sangui"]["status"] == "accepted"
    projection = runtime.worldline(worldline_id)["projection"]
    assert runtime._position_report_message(worldline_id, projection, _field_message(runtime)) is None


def test_v7_13_same_tick_field_observes_before_movement_completion(host):
    runtime = host.volume_runtime
    field = copy.deepcopy(runtime.pack.world.historical_field)
    field[0]["tick"] = 4
    runtime.pack = replace(
        runtime.pack,
        world=replace(runtime.pack.world, historical_field=tuple(field)),
    )
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    _operate(runtime, worldline_id, "wu-sangui", "prepare_force", ["wu-field-force"], "same-tick-prepare")
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            "wu-sangui": (
                "operate",
                {
                    "operation_definition_id": "move_force",
                    "targets": ["wu-field-force", "yongping"],
                    "description": "same-tick-move",
                },
            )
        },
        "same-tick-move",
    )
    assert staged["wu-sangui"]["status"] == "accepted"
    events = _advance_to(runtime, worldline_id, 4, "same-tick-field")
    field_index = next(i for i, event in enumerate(events) if event["event_type"] == "FIELD_EVENT_APPLIED")
    completion_index = next(i for i, event in enumerate(events) if event["event_type"] == "OPERATION_COMPLETED")
    assert field_index < completion_index
    assert not any(
        event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
        for event in events
    )


def test_v7_14_changed_position_without_committed_origin_fails_closed(host):
    runtime, worldline_id = _north_runtime(host)
    projection = runtime.worldline(worldline_id)["projection"]
    projection = copy.deepcopy(projection)
    projection["positions"]["wu-sangui"] = "yongping"
    assert runtime._position_report_message(worldline_id, projection, _field_message(runtime)) is None


def test_v7_15_dynamic_record_has_no_unconditional_canonical_north_claim(host):
    runtime, _, events = _north_li_branch(host)
    assert "content" not in runtime.pack.world.historical_field[0]["messages"][0]
    assert not any(entity.id == "north-affairs-recognition" for entity in runtime.pack.world.entities)
    assert all(
        "清军入关" not in str(event.get("payload", {}).get("content", ""))
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
    )


def test_v7_16_outcome_metadata_does_not_change_record(host):
    runtime, worldline_id, _ = _north_li_branch(host)
    projection = runtime.worldline(worldline_id)["projection"]
    message = _field_message(runtime)
    original = runtime._position_report_message(worldline_id, copy.deepcopy(projection), message)
    altered = copy.deepcopy(projection)
    altered["crisis_instances"]["before-shanhaiguan"]["outcome"] = {
        "variant": "CANONICAL_FUTURE",
        "summary": "清军入关",
    }
    altered["crisis_instances"]["before-shanhaiguan"]["resolution"] = {
        "result": {"variant": "CANONICAL_FUTURE"}
    }
    assert runtime._position_report_message(worldline_id, altered, message) == original


def test_v7_17_18_dynamic_record_provenance_and_causal_parents(host):
    _, _, events = _north_li_branch(host)
    applied = next(event for event in events if event["event_type"] == "FIELD_EVENT_APPLIED")
    dispatch = next(
        event
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    )
    assert dispatch["provenance"] == "volume_derived"
    assert applied["id"] in dispatch["causal_parent_ids"]
    assert any(
        event["event_type"] == "OPERATION_COMPLETED"
        and event["id"] in dispatch["causal_parent_ids"]
        and event["payload"]["operation"]["actor_id"] == "li-zicheng"
        for event in events
    )


def test_v7_19_delivery_enters_each_recipient_knowledge(host):
    runtime, worldline_id, _ = _north_li_branch(host)
    events = _advance_to(runtime, worldline_id, 10, "field-delivery")
    delivered = next(
        event
        for event in events
        if event["event_type"] == "MESSAGE_DELIVERED"
        and event["payload"].get("source") == "historical_field"
    )
    content = delivered["payload"]["content"]
    for actor_id in ("shi-kefa", "ma-shiying", "han-zanzhou"):
        lifetime = runtime.db.worldline_lifetime(worldline_id, actor_id)
        assert lifetime is not None
        assert any(
            isinstance(item, dict) and item.get("content") == content
            for item in lifetime["knowledge"]
        )


def test_v7_20_public_record_does_not_add_a_v7_forced_reopen(host):
    runtime, worldline_id, _ = _north_li_branch(host)
    _run_moment(
        runtime,
        worldline_id,
        {
            "ma-shiying": (
                "update_plan",
                {
                    "objective": "继续核验江北现实",
                    "steps": ["等待公开军情"],
                    "open_dependencies": [],
                },
            )
        },
        "field-course",
    )
    events = _advance_to(runtime, worldline_id, 10, "field-course-delivery")
    attention = [
        event
        for event in events
        if event["event_type"] == "ATTENTION_EVALUATED" and event["payload"].get("seat") == "ma-shiying"
    ]
    assert attention
    assert attention[-1]["payload"]["decision"] == "BACKGROUND"
    assert attention[-1]["payload"]["reason_code"] == "NO_REOPEN_CONDITION"


def test_v7_21_actual_fu_resolution_changes_shared_center_and_activates_southern(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "FU_RECOGNIZED"
    southern = next(
        item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == "southern-consolidation"
    )
    assert southern["status"] == "ACTIVE"


def test_v7_22_actual_lu_resolution_changes_shared_center(host):
    runtime, worldline_id = _nanjing_lu_branch(host)
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "LU_RECOGNIZED"


@pytest.mark.parametrize(
    ("branch", "expected_state"),
    [
        ("contested", "CONTESTED"),
        ("fragmented", "FRAGMENTED"),
        ("deferred", "DEFERRED"),
    ],
)
def test_v7_23_non_recognized_nanjing_results_change_shared_center(host, branch, expected_state):
    builders = {
        "contested": _nanjing_contested_branch,
        "fragmented": _nanjing_fragmented_branch,
        "deferred": _nanjing_deferred_branch,
    }
    runtime, worldline_id = builders[branch](host)
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == expected_state


def test_v7_24_shared_center_change_is_causally_parented_by_resolution(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    events = runtime.db.worldline_events(worldline_id)
    resolved = next(
        event
        for event in events
        if event["event_type"] == "CRISIS_RESOLVED"
        and event["payload"].get("crisis_id") == "nanjing-succession"
    )
    shared_change = next(
        event
        for event in events
        if event["event_type"] == "ENTITY_STATE_CHANGED"
        and event["payload"].get("entity_id") == "nanjing-political-center"
    )
    assert shared_change["causal_parent_ids"] == [resolved["id"]]


def test_v7_25_manual_settlement_never_promotes_shared_center_or_southern(host):
    runtime, worldline_id = _nanjing_runtime(host)
    runtime.settle_crisis(
        worldline_id,
        "nanjing-succession",
        outcome={"variant": "FU_RECOGNIZED", "summary": "手工写入的结果"},
    )
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "UNFORMED"
    southern = next(
        item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == "southern-consolidation"
    )
    assert southern["status"] == "DORMANT"
    with pytest.raises(VolumeRuntimeConflict, match="nanjing-political-center"):
        runtime.activate_crisis(worldline_id, "southern-consolidation")


def test_v7_26_active_nanjing_without_center_keeps_southern_dormant(host):
    runtime, worldline_id = _nanjing_runtime(host)
    projection = runtime.worldline(worldline_id)["projection"]
    southern = next(
        item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == "southern-consolidation"
    )
    assert southern["status"] == "DORMANT"
    assert projection["entities"]["nanjing-political-center"]["state"] == "UNFORMED"


def test_v7_27_fu_center_activates_southern(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    southern = next(
        item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == "southern-consolidation"
    )
    assert southern["status"] == "ACTIVE"


@pytest.mark.parametrize(
    ("branch", "expected_status"),
    [
        ("lu", "SUPPRESSED"),
        ("contested", "SUPPRESSED"),
        ("fragmented", "SUPPRESSED"),
        ("deferred", "SUPPRESSED"),
    ],
)
def test_v7_28_to_31_non_fu_centers_suppress_southern(host, branch, expected_status):
    builders = {
        "lu": _nanjing_lu_branch,
        "contested": _nanjing_contested_branch,
        "fragmented": _nanjing_fragmented_branch,
        "deferred": _nanjing_deferred_branch,
    }
    runtime, worldline_id = builders[branch](host)
    southern = next(
        item for item in runtime.db.crisis_instances(worldline_id) if item["crisis_id"] == "southern-consolidation"
    )
    assert southern["status"] == expected_status


def test_v7_32_suppressed_nanjing_suppresses_southern(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime._suppress_dormant_crisis(worldline_id, "nanjing-succession", "current branch removed Nanjing")
    runtime.reconcile_crisis_envelopes(worldline_id)
    statuses = {item["crisis_id"]: item["status"] for item in runtime.db.crisis_instances(worldline_id)}
    assert statuses["nanjing-succession"] == "SUPPRESSED"
    assert statuses["southern-consolidation"] == "SUPPRESSED"


def test_v7_33_outcome_variant_deletion_does_not_change_topology(host):
    runtime, worldline_id = _nanjing_lu_branch(host)
    current = runtime.worldline(worldline_id)["projection"]
    altered = copy.deepcopy(current)
    altered["crisis_instances"]["nanjing-succession"].pop("outcome", None)
    altered["crisis_instances"]["nanjing-succession"].pop("resolution", None)
    altered["crisis_instances"]["nanjing-succession"].pop("settlement", None)
    assert runtime._envelope_decision(worldline_id, "southern-consolidation", current) == runtime._envelope_decision(
        worldline_id, "southern-consolidation", altered
    )
    assert runtime._envelope_decision(worldline_id, "southern-consolidation", altered)["status"] == "SUPPRESSED"


def test_v7_34_to_39_southern_activation_has_no_canonical_reentry_state(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    southern_pack = runtime.pack.pack("southern-consolidation")
    southern = runtime.worldline(worldline_id)["projection"]["crisis_instances"]["southern-consolidation"]
    assert southern["entities"]["jiangbei-mandate"]["state"] == "NOT_ISSUED"
    assert southern["entities"]["jiangbei-command"]["state"] == "PENDING"
    assert "shi-kefa-leverage" not in southern["entities"]
    assert southern_pack.crisis.checkpoint.facts == ["s003"]
    assert all("s001" not in actor.initial_knowledge for actor in southern_pack.crisis.actors)
    assert all("请求督师" not in str(actor.model_dump(mode="json")) for actor in southern_pack.crisis.actors)
    assert "shi-kefa-leverage" not in {entity.id for entity in southern_pack.crisis.entities}


def test_v7_40_draft_requires_a_real_subject_action(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    southern = runtime.worldline(worldline_id)["projection"]["crisis_instances"]["southern-consolidation"]
    assert southern["entities"]["jiangbei-mandate"]["state"] == "NOT_ISSUED"
    _, events = _operate(
        runtime,
        worldline_id,
        "shi-kefa",
        "draft-jiangbei-mandate",
        ["jiangbei-mandate"],
        "southern-draft",
    )
    assert any(event["event_type"] == "OPERATION_COMPLETED" for event in events)
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["southern-consolidation"]["entities"]["jiangbei-mandate"]["state"] == "ISSUED"


def test_v7_41_coordination_requires_central_action_then_ma_response(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    _operate(
        runtime,
        worldline_id,
        "shi-kefa",
        "draft-jiangbei-mandate",
        ["jiangbei-mandate"],
        "coordination-draft",
    )
    _operate(
        runtime,
        worldline_id,
        "ma-shiying",
        "coordinate-jiangbei-command",
        ["jiangbei-command", "jiangbei-mandate"],
        "coordination-ma-response",
    )
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["southern-consolidation"]["entities"]["jiangbei-command"]["state"] == "COORDINATING"


@pytest.mark.parametrize("actor_id", ["shi-kefa", "han-zanzhou"])
def test_v7_42_non_ma_cannot_coordinate_jiangbei(actor_id, host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    _operate(
        runtime,
        worldline_id,
        "shi-kefa",
        "draft-jiangbei-mandate",
        ["jiangbei-mandate"],
        f"authority-draft-{actor_id}",
    )
    staged, _ = _run_moment(
        runtime,
        worldline_id,
        {
            actor_id: (
                "operate",
                {
                    "operation_definition_id": "coordinate-jiangbei-command",
                    "targets": ["jiangbei-command", "jiangbei-mandate"],
                    "description": "尝试单独协调",
                },
            )
        },
        f"authority-denied-{actor_id}",
    )
    assert staged[actor_id]["status"] == "rejected"
    assert staged[actor_id]["code"] == "operation_authority_denied"
    assert runtime.worldline(worldline_id)["projection"]["crisis_instances"]["southern-consolidation"]["entities"]["jiangbei-command"]["state"] == "PENDING"


def test_v7_43_silence_branch_with_terminal_knots_can_seal(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    _terminalize_all(runtime, worldline_id, "silence-terminal", reconcile=False)
    _drain_to_boundary(runtime, worldline_id, "silence-boundary")
    boundary = runtime.boundary(worldline_id)["boundary"]
    assert boundary["ready"] is True
    assert boundary["code"] == "structural_boundary"
    assert runtime.seal(worldline_id)["worldline"]["status"] == "SEALED"


def test_v7_44_non_fu_nanjing_with_suppressed_southern_can_seal(host):
    runtime, worldline_id = _nanjing_lu_branch(host)
    _terminalize_all(runtime, worldline_id, "non-fu-terminal")
    _drain_to_boundary(runtime, worldline_id, "non-fu-boundary")
    assert runtime.boundary(worldline_id)["boundary"]["ready"] is True
    assert runtime.seal(worldline_id)["worldline"]["status"] == "SEALED"


def test_v7_45_fu_and_settled_southern_can_seal(host):
    runtime, worldline_id = _nanjing_fu_branch(host)
    _terminalize_all(runtime, worldline_id, "fu-terminal")
    _drain_to_boundary(runtime, worldline_id, "fu-boundary")
    assert runtime.boundary(worldline_id)["boundary"]["ready"] is True
    assert runtime.seal(worldline_id)["worldline"]["status"] == "SEALED"


def test_v7_46_pending_field_blocks_seal_independently_of_knots(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    _terminalize_all(runtime, worldline_id, "pending-field", reconcile=False)
    boundary = runtime.boundary(worldline_id)["boundary"]
    assert boundary["ready"] is False
    assert boundary["code"] == "public_history_pending"


def test_v7_47_in_transit_dynamic_record_blocks_seal(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    runtime.settle_crisis(worldline_id, "nanjing-succession", outcome={"variant": "MANUAL"})
    runtime._suppress_dormant_crisis(worldline_id, "southern-consolidation", "center remains unformed")
    _operate(runtime, worldline_id, "wu-sangui", "prepare_force", ["wu-field-force"], "transit-prepare")
    _operate(
        runtime,
        worldline_id,
        "wu-sangui",
        "move_force",
        ["wu-field-force", "yongping"],
        "transit-move",
    )
    _advance_to(runtime, worldline_id, 9, "transit-field")
    boundary = runtime.boundary(worldline_id)["boundary"]
    assert boundary["ready"] is False
    assert boundary["code"] == "message_in_transit"


def test_v7_48_boundary_works_with_a_different_field_event_id(host):
    runtime = host.volume_runtime
    fields = copy.deepcopy(runtime.pack.world.historical_field)
    fields[0]["id"] = "neutral-public-window"
    runtime.pack = replace(
        runtime.pack,
        world=replace(runtime.pack.world, historical_field=tuple(fields)),
    )
    worldline_id = runtime.create()["worldline"]["id"]
    _terminalize_all(runtime, worldline_id, "neutral-field-id", reconcile=False)
    _drain_to_boundary(runtime, worldline_id, "neutral-field-boundary")
    boundary = runtime.boundary(worldline_id)["boundary"]
    assert boundary["ready"] is True
    assert "north-south-recognition-bridge" not in str(boundary)
    assert runtime.seal(worldline_id)["worldline"]["status"] == "SEALED"


def _archive_semantics(
    runtime: Any, worldline_id: str, projection: dict[str, Any] | None = None
) -> dict[str, Any]:
    events = runtime.db.worldline_events(worldline_id)
    north_records = [
        str(event["payload"].get("content"))
        for event in events
        if event["event_type"] == "MESSAGE_DISPATCHED"
        and event["payload"].get("source") == "historical_field"
    ]
    ledger = []
    for event in events:
        payload = event.get("payload", {})
        operation = payload.get("operation", {})
        ledger.append(
            (
                int(event["tick"]),
                str(event["event_type"]),
                str(event.get("seat_id") or ""),
                str(payload.get("crisis_id") or ""),
                str(payload.get("entity_id") or ""),
                str(payload.get("content") or ""),
                str(payload.get("variant") or ""),
                str(operation.get("definition_id") or "") if isinstance(operation, dict) else "",
            )
        )
    if projection is None:
        projection = runtime.worldline(worldline_id)["projection"]
    south_knowledge = {
        actor_id: tuple(sorted(str(item) for item in (runtime.db.worldline_lifetime(worldline_id, actor_id) or {}).get("knowledge", [])))
        for actor_id in ("shi-kefa", "ma-shiying", "han-zanzhou")
    }
    archive_event_types = {
        "CRISIS_RESOLVED",
        "CRISIS_SETTLED",
        "ENTITY_STATE_CHANGED",
        "MESSAGE_DELIVERED",
        "MESSAGE_DISPATCHED",
        "OPERATION_COMPLETED",
        "VOLUME_SEALED",
    }
    return {
        "ledger": tuple(ledger),
        "north_records": tuple(north_records),
        "south_knowledge": south_knowledge,
        "shared_center": projection["entities"]["nanjing-political-center"]["state"],
        "topology": {
            crisis_id: instance["status"]
            for crisis_id, instance in projection["crisis_instances"].items()
        },
        "southern_entities": {
            entity_id: entity["state"]
            for entity_id, entity in projection["crisis_instances"]["southern-consolidation"][
                "entities"
            ].items()
        },
        "archive": tuple(
            (
                int(event["tick"]),
                str(event["event_type"]),
                str(event.get("payload", {}).get("crisis_id") or ""),
                str(event.get("payload", {}).get("entity_id") or ""),
                str(event.get("payload", {}).get("content") or ""),
                str(event.get("payload", {}).get("variant") or ""),
            )
            for event in events
            if event["event_type"] in archive_event_types
        ),
    }


def _seal_actual_worldline(runtime: Any, worldline_id: str, tag: str) -> dict[str, Any]:
    _drain_to_boundary(runtime, worldline_id, f"{tag}-drain")
    boundary = runtime.boundary(worldline_id)["boundary"]
    assert boundary["ready"] is True
    projection = runtime.worldline(worldline_id)["projection"]
    sealed = runtime.seal(worldline_id)
    assert sealed["worldline"]["status"] == "SEALED"
    return _archive_semantics(runtime, worldline_id, projection)


def _worldline_a(host: Any) -> tuple[Any, str, dict[str, Any]]:
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    _north_li_actions(runtime, worldline_id, "worldline-a-li")
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    _nanjing_fu_actions(runtime, worldline_id, "worldline-a-fu")
    _southern_coordination_actions(runtime, worldline_id, "worldline-a-southern")
    result = _seal_actual_worldline(runtime, worldline_id, "worldline-a")
    return runtime, worldline_id, result


def _worldline_b(host: Any) -> tuple[Any, str, dict[str, Any]]:
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    _north_dorgon_actions(runtime, worldline_id, "worldline-b-dorgon")
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    _nanjing_lu_actions(runtime, worldline_id, "worldline-b-lu")
    result = _seal_actual_worldline(runtime, worldline_id, "worldline-b")
    return runtime, worldline_id, result


def test_v7_complete_deterministic_worldlines_a_and_b_diverge_and_seal(app_config):
    runtime_a, worldline_a, artifact_a = _worldline_a(_fresh_host(app_config, "worldline-a"))
    runtime_b, worldline_b, artifact_b = _worldline_b(_fresh_host(app_config, "worldline-b"))

    assert artifact_a["north_records"] and artifact_b["north_records"]
    assert artifact_a["north_records"] != artifact_b["north_records"]
    assert all(
        any(record in item for knowledge in artifact_a["south_knowledge"].values() for item in knowledge)
        for record in artifact_a["north_records"]
    )
    assert artifact_a["shared_center"] == "FU_RECOGNIZED"
    assert artifact_b["shared_center"] == "LU_RECOGNIZED"
    assert artifact_a["topology"]["southern-consolidation"] == "SETTLED"
    assert artifact_b["topology"]["southern-consolidation"] == "SUPPRESSED"
    assert artifact_a["southern_entities"] == {
        "jiangbei-command": "COORDINATING",
        "jiangbei-mandate": "ISSUED",
    }
    assert artifact_a["ledger"] != artifact_b["ledger"]
    assert artifact_a["south_knowledge"] != artifact_b["south_knowledge"]
    assert artifact_a["archive"] != artifact_b["archive"]
    assert any(
        event["event_type"] == "CRISIS_RESOLVED"
        and event["payload"].get("crisis_id") == "southern-consolidation"
        for event in runtime_a.db.worldline_events(worldline_a)
    )
    assert not any(
        event["event_type"] == "CRISIS_RESOLVED"
        and event["payload"].get("crisis_id") == "southern-consolidation"
        for event in runtime_b.db.worldline_events(worldline_b)
    )


def test_v7_outcome_deletion_proof_keeps_record_topology_and_boundary(app_config):
    north_runtime, north_worldline_id, _ = _north_li_branch(_fresh_host(app_config, "outcome-north"))
    north_projection = north_runtime.worldline(north_worldline_id)["projection"]
    north_message = _field_message(north_runtime)
    original_record = north_runtime._position_report_message(
        north_worldline_id, copy.deepcopy(north_projection), north_message
    )
    deleted_record_projection = copy.deepcopy(north_projection)
    deleted_record_projection["crisis_instances"]["before-shanhaiguan"].pop("outcome", None)
    deleted_record_projection["crisis_instances"]["before-shanhaiguan"].pop("resolution", None)
    assert north_runtime._position_report_message(
        north_worldline_id, deleted_record_projection, north_message
    ) == original_record

    runtime, worldline_id = _nanjing_lu_branch(_fresh_host(app_config, "outcome-nanjing"))
    projection = runtime.worldline(worldline_id)["projection"]
    altered_projection = copy.deepcopy(projection)
    altered_projection["crisis_instances"]["nanjing-succession"].pop("outcome", None)
    altered_projection["crisis_instances"]["nanjing-succession"].pop("resolution", None)
    assert altered_projection["entities"]["nanjing-political-center"]["state"] == "LU_RECOGNIZED"
    assert runtime._envelope_decision(worldline_id, "southern-consolidation", altered_projection)["status"] == "SUPPRESSED"
    _terminalize_all(runtime, worldline_id, "outcome-deletion-boundary")
    _drain_to_boundary(runtime, worldline_id, "outcome-deletion-drain")
    current_boundary = runtime.boundary(worldline_id)["boundary"]
    altered_boundary_projection = runtime.worldline(worldline_id)["projection"]
    altered_boundary_projection = copy.deepcopy(altered_boundary_projection)
    altered_boundary_projection["crisis_instances"]["nanjing-succession"].pop("outcome", None)
    altered_boundary_projection["crisis_instances"]["nanjing-succession"].pop("resolution", None)
    altered_boundary_projection["crisis_instances"]["nanjing-succession"].pop("settlement", None)
    altered_instances = copy.deepcopy(runtime.db.crisis_instances(worldline_id))
    for instance in altered_instances:
        instance.pop("outcome", None)
        instance.pop("outcome_json", None)
    altered_boundary = VolumeBoundaryPolicy().evaluate(
        current_tick=_tick(runtime, worldline_id),
        projection=altered_boundary_projection,
        events=runtime.db.worldline_events(worldline_id),
        instances=altered_instances,
        due_wakes=[],
        next_tick=None,
        safety_horizon_tick=None,
    ).as_dict()
    assert current_boundary["ready"] is True
    assert altered_boundary["ready"] is True
    assert altered_boundary["code"] == current_boundary["code"]


def test_v7_canon_deletion_proof_runs_without_reference_only_anchors(host):
    runtime = host.volume_runtime
    runtime.pack = replace(
        runtime.pack,
        packs={
            crisis_id: replace(pack, crisis=pack.crisis.model_copy(update={"anchors": []}))
            for crisis_id, pack in runtime.pack.packs.items()
        },
    )
    assert all(not pack.crisis.anchors for pack in runtime.pack.packs.values())
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    _nanjing_fu_actions(runtime, worldline_id, "canon-deletion-fu")
    _southern_coordination_actions(runtime, worldline_id, "canon-deletion-southern")
    projection = runtime.worldline(worldline_id)["projection"]
    assert projection["entities"]["nanjing-political-center"]["state"] == "FU_RECOGNIZED"
    assert projection["crisis_instances"]["southern-consolidation"]["status"] == "SETTLED"
    assert any(
        event["event_type"] == "CRISIS_RESOLVED"
        and event["payload"].get("crisis_id") == "nanjing-succession"
        for event in runtime.db.worldline_events(worldline_id)
    )
    assert any(
        event["event_type"] == "CRISIS_RESOLVED"
        and event["payload"].get("crisis_id") == "southern-consolidation"
        for event in runtime.db.worldline_events(worldline_id)
    )
    _drain_to_boundary(runtime, worldline_id, "canon-deletion-drain")
    assert runtime.boundary(worldline_id)["boundary"]["ready"] is True
    sealed = runtime.seal(worldline_id)
    assert sealed["worldline"]["status"] == "SEALED"
    assert any(
        event["event_type"] == "FIELD_EVENT_APPLIED"
        for event in runtime.db.worldline_events(worldline_id)
    )

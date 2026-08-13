from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.editorial import volume_attention
from chronicle.host import ChronicleHost
from chronicle.volume_runtime import VolumeRuntimeConflict


def _resolve_due_agent_wakes(runtime: Any, worldline_id: str) -> None:
    row = runtime.db.worldline(worldline_id)
    assert row is not None
    tick = int(row["current_tick"])
    due = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=tick)
        if wake["status"] in {"QUEUED", "WAITING_HUMAN"}
    ]
    if not due:
        return
    pending = runtime.freeze_pending_moment(worldline_id)
    for wake_id in pending["pending_moment"]["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        lifetime = runtime.db.worldline_lifetime_by_id(worldline_id, str(wake["actor_id"]))
        lifetime = lifetime or runtime.db.worldline_lifetime(
            worldline_id, str(wake["actor_id"])
        )
        assert lifetime is not None
        runtime.stage_intent(
            worldline_id,
            lifetime["id"],
            {"type": "wait"},
            source="agent",
        )
    runtime.commit_pending_moment(worldline_id)


def _drain_to_boundary(runtime: Any, worldline_id: str) -> None:
    while True:
        _resolve_due_agent_wakes(runtime, worldline_id)
        next_tick = runtime.next_tick(worldline_id)
        if next_tick is None:
            _resolve_due_agent_wakes(runtime, worldline_id)
            assert not [
                wake
                for wake in runtime.db.subject_wakes(worldline_id)
                if wake["status"] in {"QUEUED", "WAITING_HUMAN", "STAGED"}
            ]
            return
        runtime.advance_one(worldline_id)


def _settle_all(runtime: Any, worldline_id: str) -> None:
    for crisis_id in sorted(runtime.pack.packs):
        runtime.reconcile_crisis_envelopes(worldline_id)
        instance = runtime.db.crisis_instances(worldline_id)
        current = next(item for item in instance if item["crisis_id"] == crisis_id)
        if current["status"] in {"ACTIVE", "RESOLUTION_PENDING", "AFTERMATH"}:
            runtime.settle_crisis(
                worldline_id,
                crisis_id,
                outcome={"summary": f"{crisis_id} 已留下结果"},
            )
        elif current["status"] == "DORMANT" and crisis_id == "southern-consolidation":
            runtime._suppress_dormant_crisis(
                worldline_id,
                crisis_id,
                "南京政治中心未在当前测试分支形成可执行状态",
            )


def test_settlement_is_meaning_and_keeps_volume_active(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")

    settled = runtime.settle_crisis(
        worldline_id,
        "before-shanhaiguan",
        outcome={"summary": "山海关局势已经留下新的现实"},
    )

    assert settled["worldline"]["status"] == "ACTIVE"
    assert settled["instance"]["status"] == "SETTLED"
    assert volume_attention([settled["event"]]) == {
        "kind": "MEANING",
        "tick": 0,
        "event_id": settled["event"]["id"],
    }
    assert not any(
        event["event_type"] == "VOLUME_SEALED"
        for event in runtime.db.worldline_events(worldline_id)
    )


def test_volume_boundary_rejects_unsettled_worldline_and_seals_after_full_drain(host):
    runtime = host.volume_runtime
    created = runtime.create()
    worldline_id = created["worldline"]["id"]
    runtime.reconcile_crisis_envelopes(worldline_id)

    blocked = runtime.boundary(worldline_id)["boundary"]
    assert blocked["ready"] is False
    assert blocked["code"] == "crisis_unsettled"
    with pytest.raises(VolumeRuntimeConflict, match="局势没有成为"):
        runtime.seal(worldline_id)

    _settle_all(runtime, worldline_id)
    _drain_to_boundary(runtime, worldline_id)
    ready = runtime.boundary(worldline_id)["boundary"]
    assert ready["ready"] is True
    assert ready["code"] == "structural_boundary"
    assert ready["evidence_assertion_ids"] == ["n013", "n014"]

    sealed = runtime.seal(worldline_id, "test_boundary")
    assert sealed["worldline"]["status"] == "SEALED"
    assert sealed["event"]["event_type"] == "VOLUME_SEALED"
    assert all(
        binding["status"] == "REVOKED"
        for binding in runtime.db.agent_bindings(worldline_id)
    )
    assert all(
        lifetime["status"] == "SEALED"
        for lifetime in runtime.db.worldline_lifetimes(worldline_id)
    )
    assert runtime.seal(worldline_id)["idempotent"] is True


def test_live_volume_profiles_are_cleaned_only_after_volume_seal(app_config, monkeypatch):
    config = replace(app_config, dev=True, hermes_base_url="http://127.0.0.1:0")
    runtime = ChronicleHost(config).volume_runtime
    materialized: dict[str, Any] = {}
    cleaned: dict[str, Any] = {}

    def fake_materialize(config, worldline_id, lifetimes, **kwargs):
        materialized["worldline_id"] = worldline_id
        return {
            item["id"]: {
                "profile": f"chronicle-{worldline_id}-{item['id']}",
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{item['id']}",
            }
            for item in lifetimes
        }

    def fake_cleanup(config, worldline_id, profiles, **kwargs):
        row = runtime.db.worldline(worldline_id)
        cleaned["status"] = row["status"] if row else None
        cleaned["profiles"] = profiles

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.hermes.cleanup_volume_runtime", fake_cleanup)
    created = runtime.create(runtime_mode="live")
    worldline_id = created["worldline"]["id"]
    assert cleaned == {}
    runtime.reconcile_crisis_envelopes(worldline_id)
    _settle_all(runtime, worldline_id)
    _drain_to_boundary(runtime, worldline_id)

    runtime.seal(worldline_id)

    assert materialized["worldline_id"] == worldline_id
    assert cleaned["status"] == "SEALED"
    assert len(cleaned["profiles"]) == 6


def test_sealed_volume_archive_has_public_and_lifetime_replay(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))
    created = client.post("/api/worldlines", json={"live": False})
    assert created.status_code == 200
    worldline_id = created.json()["worldline"]["id"]
    assert client.get(f"/api/worldlines/{worldline_id}/archive").status_code == 409
    runtime = ChronicleHost(config).volume_runtime
    _settle_all(runtime, worldline_id)
    _drain_to_boundary(runtime, worldline_id)
    runtime.seal(worldline_id)

    listed = client.get("/api/worldlines")
    assert listed.status_code == 200
    assert any(
        item["id"] == worldline_id and item["kind"] == "VOLUME"
        for item in listed.json()["worldlines"]
    )

    archive = client.get(
        f"/api/worldlines/{worldline_id}/archive",
        params={"lifetime_id": "shi-kefa"},
    )

    assert archive.status_code == 200
    payload = archive.json()
    assert payload["available"] is True
    assert payload["ending"]["code"] == "structural_boundary"
    assert payload["history"]
    assert payload["lives"]
    assert "events" not in payload
    assert "replay" not in payload
    assert "boundary" not in payload
    assert not _keys(payload) & {
        "controller",
        "wake",
        "field_events",
        "pending_moment",
        "moment",
        "moments",
    }
    assert isinstance(payload["final_reality"], list)
    shi = payload["selected_life"]
    assert isinstance(shi["later_known"], list)
    assert all(item["happened_tick"] < item["known_tick"] for item in shi["later_known"])
    assert not {"knowledge", "beliefs", "plan", "controller", "profile_name"} & _keys(payload)
    visible_replay_text = " ".join(
        beat["text"] for chapter in payload["history"] for beat in chapter["beats"]
    )
    for internal_id in (
        "before-shanhaiguan",
        "nanjing-succession",
        "southern-consolidation",
    ):
        assert internal_id not in visible_replay_text


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()

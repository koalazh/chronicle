from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


def _settle_all(runtime: Any, worldline_id: str) -> None:
    for crisis_id in sorted(runtime.pack.packs):
        runtime.reconcile_crisis_envelopes(worldline_id)
        instance = next(
            item
            for item in runtime.db.crisis_instances(worldline_id)
            if item["crisis_id"] == crisis_id
        )
        if instance["status"] in {"ACTIVE", "RESOLUTION_PENDING", "AFTERMATH"}:
            runtime.settle_crisis(
                worldline_id,
                crisis_id,
                outcome={"summary": f"{crisis_id} 已留下结果"},
            )
        elif instance["status"] == "DORMANT" and crisis_id == "southern-consolidation":
            runtime._suppress_dormant_crisis(
                worldline_id,
                crisis_id,
                "南京政治中心未在当前测试分支形成可执行状态",
            )


def _drain_to_boundary(runtime: Any, worldline_id: str) -> None:
    while True:
        row = runtime.db.worldline(worldline_id)
        assert row is not None
        due = [
            wake
            for wake in runtime.db.subject_wakes(worldline_id, tick=int(row["current_tick"]))
            if wake["status"] in {"QUEUED", "WAITING_HUMAN"}
        ]
        if due:
            pending = runtime.freeze_pending_moment(worldline_id)
            for wake_id in pending["pending_moment"]["wake_ids"]:
                wake = runtime.db.crisis_wake(wake_id)
                assert wake is not None
                lifetime = runtime.db.worldline_lifetime_by_id(
                    worldline_id, str(wake["actor_id"])
                )
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
            continue
        next_tick = runtime.next_tick(worldline_id)
        if next_tick is None:
            assert not [
                wake
                for wake in runtime.db.subject_wakes(worldline_id)
                if wake["status"] in {"QUEUED", "WAITING_HUMAN", "STAGED"}
            ]
            return
        runtime.advance_one(worldline_id)


def test_product_continue_auto_seals_at_structural_boundary(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        created = client.post("/api/worldlines", json={"live": False})
        worldline_id = created.json()["worldline"]["id"]
        runtime = ChronicleHost(config).volume_runtime
        _settle_all(runtime, worldline_id)
        _drain_to_boundary(runtime, worldline_id)

        continued = client.post(f"/api/worldlines/{worldline_id}/continue")

        assert continued.status_code == 200
        assert continued.json()["continue_status"] == "volume_sealed"
        assert continued.json()["worldline"]["status"] == "SEALED"
        assert client.get("/api/worldlines/active").json()["active"] is None
        assert client.get(f"/api/worldlines/{worldline_id}/archive").status_code == 200


def test_active_life_requires_handoff_before_realtime_world_read(app_config):
    config = replace(app_config, dev=True)
    with TestClient(create_app(config)) as client:
        worldline_id = client.post("/api/worldlines", json={"live": False}).json()[
            "worldline"
        ]["id"]
        inhabited = client.post(
            f"/api/worldlines/{worldline_id}/inhabit",
            json={"lifetime_id": "wu-sangui"},
        )
        assert inhabited.status_code == 200

        blocked = client.get(f"/api/worldlines/{worldline_id}/world")
        active = client.get("/api/worldlines/active")

        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "请先交还这一生，再回到世界。"
        assert active.status_code == 200
        assert active.json()["world"] is None
        assert active.json()["world_access"] == "HANDOFF_REQUIRED"

        left = client.post(f"/api/worldlines/{worldline_id}/leave")
        assert left.status_code == 200
        assert client.get(f"/api/worldlines/{worldline_id}/world").status_code == 200


def test_sealed_history_survives_live_cleanup_failure_and_reconcile(app_config, monkeypatch):
    config = replace(app_config, dev=True, hermes_base_url="http://127.0.0.1:0")

    def fake_materialize(config, worldline_id, lifetimes, **kwargs):
        return {
            item["id"]: {
                "profile": f"chronicle-{worldline_id}-{item['id']}",
                "world_server_name": f"chronicle-volume-world-{worldline_id}-{item['id']}",
            }
            for item in lifetimes
        }

    def failed_cleanup(*_args, **_kwargs):
        raise RuntimeError("cleanup unavailable")

    monkeypatch.setattr("chronicle.hermes.materialize_lifetime_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.hermes.cleanup_volume_runtime", failed_cleanup)
    runtime = ChronicleHost(config).volume_runtime
    with TestClient(create_app(config)) as client:
        created = runtime.create(runtime_mode="live")
        worldline_id = created["worldline"]["id"]
        runtime.reconcile_crisis_envelopes(worldline_id)
        _settle_all(runtime, worldline_id)
        _drain_to_boundary(runtime, worldline_id)

        sealed = runtime.seal(worldline_id)

        assert sealed["worldline"]["status"] == "SEALED"
        assert sealed["cleanup_pending"] is True
        assert runtime.db.worldline(worldline_id)["runtime_phase"] == "CLEANUP_PENDING"
        assert client.get(f"/api/worldlines/{worldline_id}/archive").status_code == 200

    monkeypatch.setattr("chronicle.hermes.cleanup_volume_runtime", lambda *_args, **_kwargs: None)
    reconciled = runtime.reconcile_live_runtime(worldline_id)
    assert reconciled["status"] == "SEALED"
    assert reconciled["runtime_phase"] == "READY"

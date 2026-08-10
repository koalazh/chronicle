from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.crisis_runtime import CrisisRunEngine, RunMode


def test_watch_product_api_create_switch_continue_seal_replay_and_archive(app_config):
    client = TestClient(create_app(replace(app_config, dev=True)))

    crisis = client.get("/api/crisis")
    created = client.post("/api/runs", json={"mode": "WATCH", "live": False})

    assert crisis.status_code == 200
    assert crisis.json()["title"] == "山海关之前"
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]
    assert created.json()["started"] is True
    assert created.json()["run"]["current_tick"] == 0
    assert created.json()["run"]["human_decision"]["state"] == "NONE"
    assert client.get("/api/runs/active").json()["run"]["id"] == run_id
    assert client.get(f"/api/runs/{run_id}/world").status_code == 200
    for actor_id in ("li-zicheng", "wu-sangui", "dorgon"):
        perspective = client.get(f"/api/runs/{run_id}/perspective/{actor_id}")
        assert perspective.status_code == 200
        assert perspective.json()["actor"]["id"] == actor_id

    assert client.post(f"/api/runs/{run_id}/continue").json()["advanced"] is True
    sealed = client.post(f"/api/runs/{run_id}/seal", json={"reason": "test_complete"})
    replay = client.get(f"/api/runs/{run_id}/replay")
    archive = client.get("/api/archive")

    assert sealed.json()["run"]["status"] == "SEALED"
    assert replay.status_code == 200
    assert replay.json()["items"]
    assert any(item["id"] == run_id for item in archive.json()["runs"])


def test_takeover_api_enforces_perspective_lock_and_single_decision_slot(
    app_config, tmp_path
):
    config = replace(app_config, database_path=tmp_path / "takeover-api.db", dev=True)
    client = TestClient(create_app(config))
    created = client.post("/api/runs", json={"mode": "TAKEOVER", "live": False})
    run_id = created.json()["run"]["id"]

    assert client.get(f"/api/runs/{run_id}/perspective/wu-sangui").status_code == 200
    assert client.get(f"/api/runs/{run_id}/perspective/dorgon").status_code == 403
    assert client.get(f"/api/runs/{run_id}/world").status_code == 403

    decision = client.post(
        f"/api/runs/{run_id}/decision",
        json={"text": "向关外说明条件，并在两日后重新比较。"},
    )
    duplicate = client.post(
        f"/api/runs/{run_id}/decision",
        json={"text": "同一模拟日再次提交。"},
    )
    silence = client.post(f"/api/runs/{run_id}/decision", json={"text": ""})

    assert decision.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "decision_already_exists",
        "message": "当前模拟日已经提交过决定，请先继续推进。",
        "state": "COMMITTED",
        "tick": 0,
    }
    assert len(decision.json()["operations"]) == 3
    assert silence.status_code == 409
    assert silence.json()["detail"]["code"] == "decision_already_exists"
    assert client.post(f"/api/runs/{run_id}/seal", json={}).status_code == 200
    assert client.get(f"/api/runs/{run_id}/world").status_code == 200
    assert client.get(f"/api/runs/{run_id}/replay").status_code == 200


def test_historical_api_keeps_actor_future_anchors_reference_only(app_config):
    client = TestClient(create_app(app_config))
    history = client.get("/api/history")

    assert history.status_code == 200
    assert history.json()["sources"]
    assert all(
        anchor["policy"] == "REFERENCE_ONLY"
        for anchor in history.json()["anchors"]
        if anchor["actor_ids"]
    )


def test_live_run_stages_orient_until_gateway_has_reloaded_profiles(
    app_config, monkeypatch
):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    def fake_materialize(_config, run_id, actors, **_identity):
        return {
            actor["id"]: {
                "profile": f"chronicle-{run_id[-8:]}-{actor['id']}",
                "profile_key": f"key-{actor['id']}",
                "world_token": f"token-{actor['id']}",
                "ownership_marker": f"marker-{actor['id']}",
                "world_server_name": f"world-{actor['id']}",
            }
            for actor in actors
        }

    monkeypatch.setattr("chronicle.hermes.materialize_crisis_profiles", fake_materialize)
    client = TestClient(create_app(configured))

    created = client.post("/api/runs", json={"mode": "WATCH", "live": True})
    run_id = created.json()["run"]["id"]
    engine = CrisisRunEngine(configured)

    assert created.status_code == 200
    assert created.json()["started"] is False
    assert "重新启动" in created.json()["start_error"]
    assert "Profile" not in created.json()["start_error"]
    assert "Gateway" not in created.json()["start_error"]
    assert len(engine.db.crisis_wakes(run_id, status="QUEUED", tick=0)) == 3
    assert not engine.db.crisis_wakes(run_id, status="COMPLETED")
    not_ready = client.post(f"/api/runs/{run_id}/continue")
    assert not_ready.status_code == 409
    assert "设置页" in not_ready.json()["detail"]["message"]
    assert not engine.db.crisis_wakes(run_id, status="COMPLETED")


def test_product_run_fails_closed_without_setup_or_explicit_live(app_config):
    client = TestClient(create_app(app_config))

    missing_setup = client.post("/api/runs", json={"mode": "WATCH", "live": True})
    fixture_attempt = client.post("/api/runs", json={"mode": "WATCH", "live": False})

    assert missing_setup.status_code == 409
    assert fixture_attempt.status_code == 409
    assert CrisisRunEngine(app_config).db.active_run() is None


def test_live_run_creation_failure_uses_product_language(app_config, monkeypatch):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )

    def fail_materialize(*_args, **_kwargs):
        raise FileNotFoundError("hermes executable missing")

    monkeypatch.setattr("chronicle.hermes.materialize_crisis_profiles", fail_materialize)
    response = TestClient(create_app(configured)).post(
        "/api/runs", json={"mode": "WATCH", "live": True}
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == "这一局未能建立，请确认设置页中的模型连接和本地主体服务后重试。"
    assert all(term not in detail for term in ("Hermes", "Profile", "Wake", "Session"))
    assert CrisisRunEngine(configured).db.active_run() is None


def test_dev_api_is_disabled_normally_and_redacts_active_takeover(app_config):
    regular = TestClient(create_app(app_config))
    run_id = CrisisRunEngine(app_config).create(RunMode.TAKEOVER)["run"]["id"]
    assert regular.get(f"/api/dev/runs/{run_id}").status_code == 404

    dev_config = replace(app_config, dev=True)
    dev = TestClient(create_app(dev_config))
    payload = dev.get(f"/api/dev/runs/{run_id}").json()

    assert {item["seat"] for item in payload["lifetimes"]} == {"wu-sangui"}
    assert all(item["actor_id"] == "wu-sangui" for item in payload["wakes"])
    assert "dorgon" not in str(payload["lifetimes"])

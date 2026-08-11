from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.crisis_runtime import CrisisRunEngine, FixtureActorDriver, RunMode
from chronicle.live_runtime import LiveRuntimeManager


def test_watch_product_api_create_switch_continue_seal_replay_and_archive(app_config):
    client = TestClient(create_app(replace(app_config, dev=True)))

    crisis = client.get("/api/crisis")
    volume = client.get("/api/volume")
    crises = client.get("/api/crises")
    crisis_detail = client.get("/api/crises/before-shanhaiguan")
    created = client.post("/api/runs", json={"mode": "WATCH", "live": False})

    assert crisis.status_code == 200
    assert crisis.json()["title"] == "山海关之前"
    assert crisis.json()["surface"] == {
        "kind": "SPATIAL",
        "title": "山海关一线",
        "description": "北京、山海关与辽西之间，消息和兵力都必须经过现实的距离。",
        "locations": crisis.json()["corridor"],
        "actors": [],
        "messages": [],
    }
    assert volume.json()["id"] == "jiashen"
    assert crises.json()["crises"][0]["id"] == "before-shanhaiguan"
    assert crisis_detail.json()["actors"][0]["playable"] is True
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]
    assert created.json()["started"] is True
    assert created.json()["run"]["current_tick"] == 0
    assert created.json()["run"]["human_decision"]["state"] == "NONE"
    assert client.get("/api/runs/active").json()["run"]["id"] == run_id
    world = client.get(f"/api/runs/{run_id}/world")
    assert world.status_code == 200
    assert world.json()["surface"]["kind"] == "SPATIAL"
    assert {actor["id"] for actor in world.json()["surface"]["actors"]} == {
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    }
    assert world.json()["surface"]["messages"] == world.json()["messages"]
    for actor_id in ("li-zicheng", "wu-sangui", "dorgon"):
        perspective = client.get(f"/api/runs/{run_id}/perspective/{actor_id}")
        assert perspective.status_code == 200
        assert perspective.json()["actor"]["id"] == actor_id
        assert perspective.json()["surface"]["kind"] == "SPATIAL"
        assert perspective.json()["surface"]["messages"] == []
        assert [actor["id"] for actor in perspective.json()["surface"]["actors"]] == [
            actor_id
        ]

    continued = client.post(f"/api/runs/{run_id}/continue").json()
    assert continued["advanced"] is True
    assert continued["attention"]["mode"] == "WATCH"
    assert continued["moments"] > 1
    outcome_pending = client.get(f"/api/runs/{run_id}/outcome")
    sealed = client.post(f"/api/runs/{run_id}/seal", json={"reason": "test_complete"})
    outcome = client.get(f"/api/runs/{run_id}/outcome")
    replay = client.get(f"/api/runs/{run_id}/replay")
    archive = client.get("/api/archive")

    assert sealed.json()["run"]["status"] == "SEALED"
    assert outcome_pending.status_code == 409
    assert outcome_pending.json()["detail"]["code"] == "outcome_not_ready"
    assert outcome.status_code == 200
    assert outcome.json()["run"]["id"] == run_id
    assert outcome.json()["outcome"] == {}
    assert replay.status_code == 200
    assert replay.json()["items"]
    layers = replay.json()["layers"]
    assert layers["outcome"] == {}
    assert layers["causal_attribution"] == {
        "mode": "WATCH",
        "title": "几条 Life 如何互相改变",
        "chains": [],
    }
    assert layers["perspective_reveal"]["title"] == "在你看不见的地方"
    assert layers["historical_compatibility"] == []
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


@pytest.mark.parametrize("human_actor_id", ["li-zicheng", "wu-sangui", "dorgon"])
def test_takeover_api_accepts_each_playable_actor(
    app_config, tmp_path, human_actor_id
):
    config = replace(
        app_config,
        database_path=tmp_path / f"{human_actor_id}-takeover-api.db",
        dev=True,
    )
    client = TestClient(create_app(config))
    created = client.post(
        "/api/runs",
        json={
            "crisis_id": "before-shanhaiguan",
            "mode": "TAKEOVER",
            "human_actor_id": human_actor_id,
            "live": False,
        },
    )
    run_id = created.json()["run"]["id"]

    assert created.status_code == 200
    assert created.json()["run"]["human_actor"] == human_actor_id
    assert client.get(f"/api/runs/{run_id}/perspective/{human_actor_id}").status_code == 200
    for other_actor_id in {"li-zicheng", "wu-sangui", "dorgon"} - {human_actor_id}:
        assert client.get(
            f"/api/runs/{run_id}/perspective/{other_actor_id}"
        ).status_code == 403
    assert client.post(f"/api/runs/{run_id}/decision", json={"text": ""}).status_code == 200


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
    battle = next(
        anchor
        for anchor in history.json()["anchors"]
        if anchor["id"] == "historical-shanhai-battle"
    )
    assert battle["compatibility_preconditions"][0]["id"] == (
        "qing-pass-access-remains-possible"
    )


def test_live_run_bootstraps_without_a_manual_gateway_restart(
    app_config, monkeypatch
):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )
    class Gateway:
        def ensure(self, _run_id, _epoch):
            return {}

        def stop(self, _run_id, _epoch):
            return None

    records: dict[str, dict[str, dict[str, str]]] = {}

    def fake_materialize(_config, run_id, actors, **_identity):
        return records.setdefault(
            run_id,
            {
                actor["id"]: {
                    "profile": actor["profile"],
                    "profile_key": f"key-{actor['id']}",
                    "world_token": f"token-{actor['id']}",
                    "ownership_marker": actor["ownership_marker"],
                    "world_server_name": actor["world_server_name"],
                }
                for actor in actors
            },
        )

    monkeypatch.setattr("chronicle.live_runtime.materialize_crisis_profiles", fake_materialize)
    runtime = LiveRuntimeManager(
        configured,
        controller=Gateway(),
        engine_factory=lambda active: CrisisRunEngine(active, actor_driver=FixtureActorDriver()),
    )
    client = TestClient(create_app(configured, live_runtime=runtime))

    created = client.post("/api/runs", json={"mode": "WATCH", "live": True})
    run_id = created.json()["run"]["id"]
    engine = CrisisRunEngine(configured)

    assert created.status_code == 200
    assert created.json()["started"] is True
    assert created.json()["start_error"] == ""
    assert created.json()["run"]["runtime_phase"] == "READY"
    orient = [wake for wake in engine.db.crisis_wakes(run_id) if wake["wake_type"] == "ORIENT"]
    assert len(orient) == 3
    assert {wake["status"] for wake in orient} == {"COMPLETED"}
    continued = client.post(f"/api/runs/{run_id}/continue")
    assert continued.status_code == 200
    assert continued.json()["attention"]["mode"] == "WATCH"


def test_product_startup_reconciles_the_active_live_run(app_config, monkeypatch):
    configured = replace(
        app_config,
        llm_base_url="https://provider.example/v1",
        llm_api_key="provider-key",
        llm_model="demo-model",
    )

    class Gateway:
        def __init__(self):
            self.ensured: list[tuple[str, str]] = []

        def ensure(self, run_id, epoch):
            self.ensured.append((run_id, epoch))
            return {}

        def stop(self, _run_id, _epoch):
            return None

    records: dict[str, dict[str, dict[str, str]]] = {}

    def fake_materialize(_config, run_id, actors, **_identity):
        return records.setdefault(
            run_id,
            {
                actor["id"]: {
                    "profile": actor["profile"],
                    "profile_key": f"key-{actor['id']}",
                    "world_token": f"token-{actor['id']}",
                    "ownership_marker": actor["ownership_marker"],
                    "world_server_name": actor["world_server_name"],
                }
                for actor in actors
            },
        )

    def fake_load(_config, run_id, _actors, **_identity):
        return records[run_id]

    monkeypatch.setattr("chronicle.live_runtime.materialize_crisis_profiles", fake_materialize)
    monkeypatch.setattr("chronicle.live_runtime.load_crisis_profile_records", fake_load)
    gateway = Gateway()
    runtime = LiveRuntimeManager(
        configured,
        controller=gateway,
        engine_factory=lambda active: CrisisRunEngine(active, actor_driver=FixtureActorDriver()),
    )
    created = runtime.create(RunMode.WATCH)

    with TestClient(
        create_app(
            configured,
            live_runtime=runtime,
            manage_live_runtime_on_startup=True,
        )
    ) as client:
        active = client.get("/api/runs/active").json()["run"]

    assert active["id"] == created["id"]
    assert active["runtime_phase"] == "READY"
    assert len(gateway.ensured) == 2
    assert len(CrisisRunEngine(configured).db.crisis_wakes(created["id"], tick=0)) == 3


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

    monkeypatch.setattr("chronicle.live_runtime.materialize_crisis_profiles", fail_materialize)
    response = TestClient(create_app(configured)).post(
        "/api/runs", json={"mode": "WATCH", "live": True}
    )

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["runtime_phase"] == "FAILED"
    assert response.json()["start_error"] == "这一局尚未准备好；请在页面中重新准备。"
    assert all(term not in response.json()["start_error"] for term in ("Hermes", "Profile", "Wake", "Session"))
    assert CrisisRunEngine(configured).db.active_run()["id"] == run["id"]


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

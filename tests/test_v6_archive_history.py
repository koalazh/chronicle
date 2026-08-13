from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.host import ChronicleHost


def _resolve_due_agent_wakes(runtime: Any, worldline_id: str) -> None:
    row = runtime.db.worldline(worldline_id)
    assert row is not None
    due = [
        wake
        for wake in runtime.db.subject_wakes(worldline_id, tick=int(row["current_tick"]))
        if wake["status"] in {"QUEUED", "WAITING_HUMAN"}
    ]
    if not due:
        return
    pending = runtime.freeze_pending_moment(worldline_id)
    for wake_id in pending["pending_moment"]["wake_ids"]:
        wake = runtime.db.crisis_wake(wake_id)
        assert wake is not None
        lifetime = runtime.db.worldline_lifetime_by_id(worldline_id, str(wake["actor_id"]))
        lifetime = lifetime or runtime.db.worldline_lifetime(worldline_id, str(wake["actor_id"]))
        assert lifetime is not None
        runtime.stage_intent(
            worldline_id,
            lifetime["id"],
            {"type": "wait"},
            source="agent",
            wake_id=wake_id,
        )
    runtime.commit_pending_moment(worldline_id)


def _drain_to_boundary(runtime: Any, worldline_id: str) -> None:
    while True:
        _resolve_due_agent_wakes(runtime, worldline_id)
        if runtime.next_tick(worldline_id) is None:
            _resolve_due_agent_wakes(runtime, worldline_id)
            return
        runtime.advance_one(worldline_id)


def _settle_all(runtime: Any, worldline_id: str) -> None:
    for crisis_id in sorted(runtime.pack.packs):
        runtime.reconcile_crisis_envelopes(worldline_id)
        current = next(
            item
            for item in runtime.db.crisis_instances(worldline_id)
            if item["crisis_id"] == crisis_id
        )
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


def test_archive_projects_append_only_judgment_history(app_config):
    config = replace(app_config, dev=True)
    client = TestClient(create_app(config))
    created = client.post("/api/worldlines", json={"live": False})
    assert created.status_code == 200
    worldline_id = created.json()["worldline"]["id"]

    runtime = ChronicleHost(config).volume_runtime
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "先守住关口，再核验来信",
            "steps": ["守住关口", "核验来信"],
            "open_dependencies": [],
        },
        source="agent",
        wake_id=next(
            wake["id"]
            for wake in runtime.db.subject_wakes(worldline_id, tick=1)
            if wake["actor_id"] == "wu-sangui"
        ),
    )
    runtime.commit_pending_moment(worldline_id)
    _settle_all(runtime, worldline_id)
    _drain_to_boundary(runtime, worldline_id)
    runtime.seal(worldline_id)

    archive = client.get(
        f"/api/worldlines/{worldline_id}/archive",
        params={"lifetime_id": "wu-sangui"},
    )
    assert archive.status_code == 200
    history = archive.json()["replay"]["lifetime"]["judgment_history"]
    assert history
    first = history[0]
    assert first["label"] == "第一次判断"
    assert first["course"] == "先守住关口，再核验来信"
    assert first["before"] == "此前还没有明确打算。"
    assert "DECISION_HORIZON" not in str(history)
    assert "wake_id" not in str(history)

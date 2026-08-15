from __future__ import annotations

from dataclasses import replace

import pytest

from chronicle.host import ChronicleHost


def _runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(f"chronicle-v6-context-{suffix}.db"),
        runtime_dir=app_config.runtime_dir / f"v6-context-{suffix}",
        hermes_home=app_config.hermes_home / f"v6-context-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "before-shanhaiguan")
    runtime.advance_one(worldline_id)
    runtime.freeze_pending_moment(worldline_id)
    wu = runtime.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert wu is not None
    return runtime, worldline_id, wu


def _establish_course(runtime, worldline_id, wu):
    runtime.stage_intent(
        worldline_id,
        wu["id"],
        {
            "type": "update_plan",
            "objective": "等待多尔衮答复，同时防备李军继续东进",
            "steps": ["保留关口选择", "核验来信"],
            "rationale": "尚无足够事实作出最终承诺",
            "open_dependencies": [
                {
                    "id": "await-dorgon",
                    "type": "MESSAGE_FROM",
                    "actor_id": "dorgon",
                }
            ],
        },
        source="agent",
        idempotency_key="v6-context-course",
    )
    runtime.commit_pending_moment(worldline_id)


def _wu_attention_wake(runtime, worldline_id):
    current_tick = int(runtime.db.worldline(worldline_id)["current_tick"])
    return next(
        wake
        for wake in reversed(runtime.db.subject_wakes(worldline_id))
        if wake["actor_id"] == "wu-sangui"
        and wake["source"] == "v6-attention"
        and int(wake["tick"]) == current_tick
    )


def test_reality_first_context_keeps_background_contrary_fact(app_config):
    runtime, worldline_id, wu = _runtime(app_config, "background-reality")
    _establish_course(runtime, worldline_id, wu)
    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="li-zicheng",
        recipient="wu-sangui",
        content="李军已经公开东向推进。",
        delivery_tick=2,
    )
    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="dorgon",
        recipient="wu-sangui",
        content="多尔衮明确回复：须先见到关口处置。",
        delivery_tick=3,
    )

    runtime.advance_one(worldline_id)
    runtime.advance_one(worldline_id)
    frozen = runtime.freeze_pending_moment(worldline_id)
    wake = _wu_attention_wake(runtime, worldline_id)
    context = wake["frozen_perspective"]["context"]

    assert frozen["pending_moment"]["tick"] == 3
    assert context["why_now"]["decision"] == "REOPEN"
    assert context["why_now"]["reason_code"] == "OPEN_DEPENDENCY_MATCH"
    assert context["why_now"]["matched_dependency_ids"] == ["await-dorgon"]
    assert [fact["payload"]["content"] for fact in context["why_now"]["facts"]] == [
        "多尔衮明确回复：须先见到关口处置。"
    ]
    assert [fact["content"] for fact in context["since_last_deliberation"]["facts"]] == [
        "李军已经公开东向推进。",
        "多尔衮明确回复：须先见到关口处置。",
    ]
    assert context["previous_course"]["course"] == "等待多尔衮答复，同时防备李军继续东进"
    assert context["binding_reality"]["position"]["id"] == "shanhaiguan"
    assert context["binding_reality"]["resources"]["pass_control"] == "contested-but-held"
    assert context["affordances"]["operations"]
    assert set(context["relevant_experience"]) == {"beliefs", "evidence", "memory"}


@pytest.mark.skip(reason="历史南京主体 affordance 样例；当前山海关版本由 phase8 测试覆盖")
def test_reality_first_context_keeps_subject_affordances_private(app_config):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name("chronicle-v6-context-private.db"),
        runtime_dir=app_config.runtime_dir / "v6-context-private",
        hermes_home=app_config.hermes_home / "v6-context-private",
    )
    runtime = ChronicleHost(config).volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.activate_crisis(worldline_id, "nanjing-succession")
    context = runtime.lifetime_context(worldline_id, "ma-shiying")

    operation_ids = {
        item["item"]["id"] for item in context["affordances"]["operations"]
    }
    investigation_ids = {
        item["item"]["id"] for item in context["affordances"]["investigations"]
    }

    assert "make_fu_backing_visible" in operation_ids
    assert "claimant-position-report" in investigation_ids
    assert "military-backing-report" not in investigation_ids
    assert context["binding_reality"]["active_operations"] == []

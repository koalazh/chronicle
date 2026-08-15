from __future__ import annotations

from dataclasses import replace

from chronicle.db import content_hash
from chronicle.hermes import append_profile_memory, read_profile_memory
from chronicle.host import ChronicleHost
from chronicle.product_projection import ProductProjection


def _build_runtime(app_config, suffix: str):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name(
            f"chronicle-killer-demo-{suffix}.db"
        ),
        runtime_dir=app_config.runtime_dir / f"killer-demo-{suffix}",
        hermes_home=app_config.hermes_home / f"killer-demo-{suffix}",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.reconcile_crisis_envelopes(worldline_id)
    return host, runtime, worldline_id


def test_killer_demo_is_one_world_with_three_independent_subjects(pack):
    assert list(pack.packs) == ["before-shanhaiguan"]
    assert set(pack.lifetimes) == {"li-zicheng", "wu-sangui", "dorgon"}
    assert {location.id for location in pack.world.locations}.isdisjoint(
        {"nanjing", "fengyang", "yangzhou"}
    )
    assert [item["id"] for item in pack.summary()["crises"]] == ["before-shanhaiguan"]
    assert pack.summary()["crises"][0]["participants"] == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]


def test_live_world_projection_exposes_only_the_three_person_corridor(app_config):
    host, _runtime, worldline_id = _build_runtime(app_config, "projection")
    view = ProductProjection(host, lambda active, identifier: active.db.worldline(identifier) or {})

    world = view.public_world(worldline_id)
    corridor = world["corridor"]

    assert [item["display_name"] for item in corridor["locations"]] == [
        "北京",
        "山海关",
        "辽西行军路",
    ]
    assert [item["id"] for item in corridor["people"]] == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]
    assert corridor["transit"][0]["from"]["display_name"] == "北京"
    assert corridor["transit"][0]["to"]["display_name"] == "山海关"
    assert "content" not in str(corridor["transit"])


def test_replay_uses_readable_sources_without_null_actor_or_redundant_investigation(
    app_config,
):
    host, _runtime, worldline_id = _build_runtime(app_config, "replay-copy")
    projection = ProductProjection(
        host, lambda active, identifier: active.db.worldline(identifier) or {}
    )
    observation = {
        "id": "investigation-1:observation",
        "content": "山海关仍由吴三桂一方守持。",
    }
    events = [
        {
            "id": "horizon",
            "tick": 0,
            "event_type": "DECISION_HORIZON_ESTABLISHED",
            "seat_id": "li-zicheng",
            "payload": {
                "seat": "li-zicheng",
                "course": {"course": "先核验关口态势"},
            },
        },
        {
            "id": "investigation",
            "tick": 2,
            "event_type": "INVESTIGATION_COMPLETED",
            "seat_id": "li-zicheng",
            "payload": {
                "investigation": {
                    "id": "investigation-1",
                    "actor_id": "li-zicheng",
                    "observation": observation,
                },
                "visibility": ["li-zicheng"],
            },
        },
        {
            "id": "observation",
            "tick": 2,
            "event_type": "OBSERVATION_OBTAINED",
            "seat_id": "li-zicheng",
            "payload": {"observation": observation, "visibility": ["li-zicheng"]},
        },
    ]

    history = projection.judgment_history({"seat": "li-zicheng"}, events)
    assert [item["kind"] for item in history[0]["consequences"]] == ["观察"]

    reality = projection.history_beats(
        [
            {
                "id": "reality",
                "tick": 5,
                "event_type": "ENTITY_STATE_CHANGED",
                "seat_id": None,
                "payload": {
                    "crisis_id": "before-shanhaiguan",
                    "entity_id": "eastern-transit-window",
                    "description": "这一轮通行窗口已经结束。",
                    "visibility": "PUBLIC",
                },
            }
        ]
    )
    assert reality[0]["actor"] == {
        "id": "external-reality",
        "display_name": "外部现实",
    }
    assert "None" not in str(reality)

    why_now = projection.desk_why_now(
        {
            "why_now": {
                "decision": "REOPEN",
                "facts": [
                    {
                        "event_type": "ENTITY_STATE_CHANGED",
                        "payload": {"description": "京东通行窗口已经收紧。"},
                    }
                ],
            }
        }
    )
    assert why_now["facts"] == [{"text": "京东通行窗口已经收紧。"}]


def test_product_item_text_reads_nested_payload_without_user_hostile_placeholder(app_config):
    host, _runtime, _worldline_id = _build_runtime(app_config, "nested-fact-copy")
    projection = ProductProjection(
        host, lambda active, identifier: active.db.worldline(identifier) or {}
    )

    assert projection.product_item_text(
        {"payload": {"content": "关口仍由吴三桂一方守持。"}}
    ) == "关口仍由吴三桂一方守持。"
    assert projection.product_item_text({"payload": {"content": "INTERNAL_FACT_1"}}) == (
        "一项已知事实。"
    )


def test_consequential_experience_survives_restart_and_is_causally_referenced(app_config):
    host, runtime, worldline_id = _build_runtime(app_config, "experience")
    runtime.inhabit(worldline_id, "wu-sangui")
    runtime.advance_one(worldline_id)
    pending = runtime.freeze_pending_moment(worldline_id)["pending_moment"]
    wu_wake_id = pending["wake_ids"][0]

    runtime.stage_intent(
        worldline_id,
        "wu-sangui",
        {
            "type": "update_plan",
            "objective": "守住关口，等待关外回复",
            "steps": ["核验来信"],
            "rationale": "先等待可核验消息",
            "rationale_source": "explicit",
            "open_dependencies": [
                {"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}
            ],
        },
        source="human",
        wake_id=wu_wake_id,
    )
    runtime.commit_pending_moment(worldline_id)

    reconsideration = runtime.open_voluntary_reconsideration(worldline_id, "wu-sangui")
    runtime.stage_intent(
        worldline_id,
        "wu-sangui",
        {
            "type": "update_plan",
            "objective": "不再无限等待，先核验关口",
            "steps": ["核验来信", "保留关口选择"],
            "rationale": "现实要求给等待设限",
            "rationale_source": "explicit",
            "open_dependencies": [
                {"id": "await-dorgon", "type": "MESSAGE_FROM", "actor_id": "dorgon"}
            ],
        },
        source="human",
        wake_id=reconsideration["pending_moment"]["wake_ids"][0],
    )
    runtime.commit_pending_moment(worldline_id)

    experience = host.db.worldline_lifetime(worldline_id, "wu-sangui")["experiences"][0]
    assert experience["kind"] == "COMMITMENT_REVISED"
    assert experience["basis_event_ids"]
    lifetime = host.db.worldline_lifetime(worldline_id, "wu-sangui")
    assert lifetime is not None
    assert "Experience:" in lifetime["memory_text"]
    desk = ProductProjection(
        host, lambda active, identifier: active.db.worldline(identifier) or {}
    ).public_desk(worldline_id, None)
    assert desk["desk"]["experiences"]
    assert experience["id"] not in str(desk["desk"]["experiences"])

    runtime.leave(worldline_id)
    runtime.dispatch_message(
        worldline_id,
        crisis_id="before-shanhaiguan",
        sender="dorgon",
        recipient="wu-sangui",
        content="关外回复已到，请明确关口条件。",
        delivery_tick=3,
    )
    runtime.advance_one(worldline_id)
    runtime.inhabit(worldline_id, "wu-sangui")
    pending = runtime.freeze_pending_moment(worldline_id)["pending_moment"]
    wu_wake = next(
        wake
        for wake_id in pending["wake_ids"]
        if (wake := host.db.crisis_wake(wake_id)) is not None
        and wake["actor_id"] == "wu-sangui"
    )
    dorgon_wake = next(
        wake
        for wake_id in pending["wake_ids"]
        if (wake := host.db.crisis_wake(wake_id)) is not None
        and wake["actor_id"] == "dorgon"
    )

    runtime.stage_deliberation(
        worldline_id,
        "wu-sangui",
        {
            "outcome": "REVISE",
            "course": {
                "summary": "带着过去的教训先核验",
                "steps": ["核验来信"],
            },
            "open_dependencies": [],
            "belief_updates": [],
            "world_actions": [],
            "experience_refs": [experience["id"]],
        },
        source="human",
        wake_id=wu_wake["id"],
    )
    runtime.stage_intent(
        worldline_id,
        "dorgon",
        {"type": "wait"},
        source="agent",
        wake_id=dorgon_wake["id"],
    )
    committed = runtime.commit_pending_moment(worldline_id)
    deliberation = next(
        event for event in committed["events"] if event["event_type"] == "DELIBERATION_COMMITTED"
    )
    experience_event_id = next(
        event["id"]
        for event in host.db.worldline_events(worldline_id)
        if event["event_type"] == "EXPERIENCE_RECORDED"
        and event["payload"]["experience"]["id"] == experience["id"]
    )
    assert deliberation["payload"]["experience_refs"] == [experience["id"]]
    assert deliberation["payload"]["experience_event_ids"] == [experience_event_id]
    assert experience_event_id in deliberation["causal_parent_ids"]

    restarted = ChronicleHost(host.config)
    context = restarted.volume_runtime.lifetime_context(worldline_id, "wu-sangui")
    assert context["experiences"]
    assert context["current_course"]["course"] == "带着过去的教训先核验"


def test_subject_profiles_are_distinct_and_experience_is_private(app_config):
    host, runtime, worldline_id = _build_runtime(app_config, "ownership")
    lifetimes = host.db.worldline_lifetimes(worldline_id)
    assert len(lifetimes) == 3
    assert {item["profile_name"] for item in lifetimes} == {
        "wu-sangui",
        "li-zicheng",
        "dorgon",
    }
    assert len({item["profile_name"] for item in lifetimes}) == 3

    projection = ProductProjection(
        host, lambda active, identifier: active.db.worldline(identifier) or {}
    )
    world = projection.public_world(worldline_id)
    assert "EXPERIENCE_RECORDED" not in str(world)
    assert runtime.pack.pack("before-shanhaiguan").participant_ids == [
        "li-zicheng",
        "wu-sangui",
        "dorgon",
    ]


def test_profile_memory_append_is_private_and_idempotent(app_config):
    block = "Experience: 过去的判断曾经被现实改写。"

    append_profile_memory(app_config, "wu-sangui", block)
    append_profile_memory(app_config, "wu-sangui", block)

    memory, digest = read_profile_memory(app_config, "wu-sangui")
    assert memory.count(block) == 1
    assert memory == block
    assert digest == content_hash(block)
    assert not (app_config.hermes_home / "profiles" / "dorgon" / "memories" / "MEMORY.md").exists()

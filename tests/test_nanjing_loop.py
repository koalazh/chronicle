from __future__ import annotations

import pytest

from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode


def _endorsement_terms(perspective: dict, claimant_id: str) -> list[dict[str, str]]:
    term = next(
        item
        for item in perspective["available_offer_terms"]
        if item["type"] == "endorsement" and item["subject"]["id"] == claimant_id
    )
    return [
        {
            "type": term["type"],
            "subject": term["subject"]["id"],
            "value": term["value"],
            "description": term["description"],
        }
    ]


class _FuRecognitionDriver:
    source = "fixture"

    def __init__(self):
        self.proposed_endorsement = False
        self.arranged_entry = False
        self.formalized = False
        self.proclaimed = False

    def run_wake(self, actor_id, wake, perspective, world):
        available_operations = {
            item["id"] for item in perspective.get("available_operations", [])
        }
        if actor_id == "han-zanzhou" and wake["wake_type"] == "ORIENT":
            world.operate(
                "convene_recognition_assembly",
                ["nanjing-court"],
                "先把继统问题放入能够实际处理的南京议程。",
                idempotency_key="convene-assembly",
            )
        elif actor_id == "ma-shiying" and wake["wake_type"] == "ORIENT":
            world.operate(
                "make_fu_backing_visible",
                ["jiangbei-military-backing"],
                "先让可见的江北保护安排进入南京的共同事实。",
                idempotency_key="make-backing-visible",
            )
        elif actor_id == "han-zanzhou" and wake["wake_type"] == "OPERATION_RESULT":
            if not self.proposed_endorsement:
                world.manage_offer(
                    "PROPOSE",
                    recipient="ma-shiying",
                    terms=_endorsement_terms(perspective, "fu-prince"),
                    message="若福王进入南京程序，请共同把公开支持约定为可被彼此依赖的条件。",
                    idempotency_key="propose-fu-endorsement",
                )
                self.proposed_endorsement = True
            elif "formalize_fu_regency" in available_operations and not self.formalized:
                world.operate(
                    "formalize_fu_regency",
                    ["fu-prince", "nanjing-court", "nanjing-recognition"],
                    "在候选、支持与中枢程序已经汇合后完成制度承认。",
                    idempotency_key="formalize-fu",
                )
                self.formalized = True
        elif actor_id == "ma-shiying" and wake["wake_type"] == "OPERATION_RESULT":
            if "arrange_fu_entry" in available_operations and not self.arranged_entry:
                world.operate(
                    "arrange_fu_entry",
                    ["fu-prince"],
                    "在议程和可见支持已经具备后，安排福王进入南京程序。",
                    idempotency_key="arrange-fu-entry",
                )
                self.arranged_entry = True
        elif actor_id == "ma-shiying" and wake["wake_type"] == "OFFER_CHANGE":
            incoming = next(
                (
                    offer
                    for offer in perspective["active_offers"]
                    if offer["recipient"] == "ma-shiying"
                    and offer["terms"][0]["subject"] == "fu-prince"
                ),
                None,
            )
            if incoming is not None:
                world.manage_offer(
                    "ACCEPT",
                    offer_id=incoming["id"],
                    idempotency_key="accept-fu-endorsement",
                )
        elif actor_id == "han-zanzhou" and wake["wake_type"] == "RESOLUTION_RESULT":
            if "issue_regency_proclamation" in available_operations and not self.proclaimed:
                world.operate(
                    "issue_regency_proclamation",
                    ["regency-proclamation"],
                    "让已经形成的制度承认进入公开文书。",
                    idempotency_key="issue-proclamation",
                )
                self.proclaimed = True
        return ActorTurnResult("保持有限且可追溯的南京处置。")


class _LateLuEntryDriver(_FuRecognitionDriver):
    """Keep a competing claimant's already-started entry visible after recognition."""

    def __init__(self):
        super().__init__()
        self.lu_revisit_scheduled = False
        self.lu_entry_arranged = False

    def run_wake(self, actor_id, wake, perspective, world):
        available_operations = {
            item["id"] for item in perspective.get("available_operations", [])
        }
        if actor_id == "shi-kefa" and wake["wake_type"] == "ORIENT":
            if not self.lu_revisit_scheduled:
                world.schedule_revisit(
                    3,
                    "待程序已实际开始后，再判断是否安排潞王进入南京。",
                    idempotency_key="revisit-lu-entry",
                )
                self.lu_revisit_scheduled = True
        elif (
            actor_id == "shi-kefa"
            and wake["wake_type"] == "REVISIT_DUE"
            and "arrange_lu_entry" in available_operations
            and not self.lu_entry_arranged
        ):
            world.operate(
                "arrange_lu_entry",
                ["lu-prince"],
                "程序已经开启，安排潞王进入南京以保留可见的候选事实。",
                idempotency_key="arrange-lu-entry-late",
            )
            self.lu_entry_arranged = True
        return super().run_wake(actor_id, wake, perspective, world)


class _DeferredProcedureDriver:
    source = "fixture"

    def __init__(self):
        self.deferred = False

    def run_wake(self, actor_id, wake, perspective, world):
        available_operations = {
            item["id"] for item in perspective.get("available_operations", [])
        }
        if actor_id == "han-zanzhou" and wake["wake_type"] == "ORIENT":
            world.operate(
                "convene_recognition_assembly",
                ["nanjing-court"],
                "先使南京程序能够处理继统问题。",
                idempotency_key="convene-assembly",
            )
        elif (
            actor_id == "han-zanzhou"
            and wake["wake_type"] == "PRESSURE"
            and "defer_recognition_procedure" in available_operations
            and not self.deferred
        ):
            world.operate(
                "defer_recognition_procedure",
                ["nanjing-court", "nanjing-recognition"],
                "当前没有可执行的单一承认，先将程序明确记录为延期。",
                idempotency_key="defer-procedure",
            )
            self.deferred = True
        return ActorTurnResult("保持有限且可追溯的南京处置。")


def test_nanjing_endorsement_agreement_unlocks_the_formalization_affordance(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    projection["entities"]["nanjing-court"]["state"] = "DELIBERATING"
    projection["entities"]["nanjing-recognition"]["state"] = "DELIBERATING"
    projection["entities"]["fu-prince"]["state"] = "IN_NANJING"
    projection["entities"]["jiangbei-military-backing"]["state"] = "FU_BACKED"

    without_agreement = {
        item["id"]
        for item in engine.pack.operation_affordances("han-zanzhou", projection, tick=2)
    }
    projection["agreements"].append(
        {
            "id": "agreement-fu-endorsement",
            "parties": ["ma-shiying", "han-zanzhou"],
            "terms": _endorsement_terms(
                engine.actor_perspective(run_id, "han-zanzhou"), "fu-prince"
            ),
            "status": "ACTIVE",
        }
    )
    with_agreement = {
        item["id"]
        for item in engine.pack.operation_affordances("han-zanzhou", projection, tick=2)
    }

    assert "formalize_fu_regency" not in without_agreement
    assert "formalize_fu_regency" in with_agreement


@pytest.mark.parametrize("human_actor_id", ["shi-kefa", "ma-shiying", "han-zanzhou"])
def test_nanjing_every_decision_actor_can_be_taken_over(app_config, human_actor_id):
    engine = CrisisRunEngine(app_config)
    created = engine.create(
        RunMode.TAKEOVER,
        human_actor_id=human_actor_id,
        crisis_id="nanjing-succession",
    )
    run_id = created["run"]["id"]
    controllers = created["run"]["controller_map"]

    assert controllers[human_actor_id] == "HUMAN"
    assert {
        actor_id for actor_id, controller in controllers.items() if controller == "AGENT"
    } == {"shi-kefa", "ma-shiying", "han-zanzhou"} - {human_actor_id}
    assert engine.db.worldline_lifetime(run_id, human_actor_id)["profile_name"] == ""
    assert engine.product_perspective(run_id, human_actor_id)["actor"]["id"] == human_actor_id


def test_nanjing_fixture_loop_reaches_recognition_aftermath_and_settlement(app_config):
    engine = CrisisRunEngine(app_config, actor_driver=_FuRecognitionDriver())
    run_id = engine.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]
    initial_surface = engine.product_perspective(run_id, "han-zanzhou")["surface"]

    result = engine.run_until_idle(run_id)
    run = engine.run_summary(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    outcome = run["outcome_json"]

    assert initial_surface["kind"] == "POLITICAL"
    assert {subject["knowledge"] for subject in initial_surface["subjects"]} == {
        "UNCONFIRMED"
    }
    context = {item["id"]: item for item in initial_surface["context"]}
    assert context["nanjing-court"]["knowledge"] == "KNOWN"
    assert context["nanjing-court"]["state_label"] == "可召集"
    assert context["nanjing-recognition"]["knowledge"] == "UNKNOWN"
    assert "state" not in context["nanjing-recognition"]

    assert run["status"] == "SEALED"
    assert run["crisis_phase"] == "SETTLED"
    assert run["settlement_reason"] == "resolution_stabilized"
    assert outcome["settlement_type"] == "RESOLVED"
    assert outcome["resolution_kind"] == "RECOGNIZED_SETTLEMENT"
    assert outcome["resolution_variant"] == "FU_RECOGNIZED"
    assert outcome["summary"] == next(
        event["payload"]["result"]["summary"]
        for event in result["events"]
        if event["event_type"] == "RESOLUTION_APPLIED"
    )
    assert projection["resolution"]["status"] == "APPLIED"
    assert projection["settlement"]["status"] == "SETTLED"
    assert projection["entities"]["fu-prince"]["state"] == "IN_NANJING"
    assert projection["entities"]["lu-prince"]["state"] == "NOT_SELECTED"
    assert projection["entities"]["nanjing-recognition"]["state"] == "FU_RECOGNIZED"
    assert projection["entities"]["nanjing-court"]["state"] == "RECOGNIZED"
    assert projection["entities"]["regency-proclamation"]["state"] == "ISSUED"
    assert projection["agreements"][0]["status"] == "FULFILLED"
    assert {
        operation["definition_id"]
        for operation in projection["operations"]
        if operation["status"] == "COMPLETED"
    } >= {
        "convene_recognition_assembly",
        "make_fu_backing_visible",
        "arrange_fu_entry",
        "formalize_fu_regency",
        "issue_regency_proclamation",
    }
    assert any(event["event_type"] == "AGREEMENT_CREATED" for event in result["events"])
    assert any(event["event_type"] == "RESOLUTION_APPLIED" for event in result["events"])
    assert any(
        event["event_type"] == "OPERATION_COMPLETED"
        and event["payload"]["operation"]["definition_id"] == "issue_regency_proclamation"
        for event in result["events"]
    )
    compatibility = {item["anchor_id"]: item["status"] for item in outcome["historical_compatibility"]}
    assert compatibility["historical-fu-regency"] == "COMPATIBLE"
    assert compatibility["historical-fu-enthronement"] == "UNKNOWN"


def test_nanjing_recognition_remains_distinct_from_a_late_competing_claimant_entry(
    app_config,
):
    engine = CrisisRunEngine(app_config, actor_driver=_LateLuEntryDriver())
    run_id = engine.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]

    engine.run_until_idle(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    events = engine.db.worldline_events(run_id)

    assert projection["entities"]["nanjing-recognition"]["state"] == "FU_RECOGNIZED"
    assert projection["entities"]["nanjing-court"]["state"] == "RECOGNIZED"
    assert projection["entities"]["lu-prince"]["state"] == "IN_NANJING"
    resolution_tick = next(
        int(event["tick"])
        for event in events
        if event["event_type"] == "RESOLUTION_APPLIED"
    )
    late_entry_tick = next(
        int(event["tick"])
        for event in events
        if event["event_type"] == "OPERATION_COMPLETED"
        and event["payload"]["operation"]["definition_id"] == "arrange_lu_entry"
    )
    assert late_entry_tick > resolution_tick


def test_replay_offer_detail_does_not_duplicate_canonical_term_punctuation(app_config):
    engine = CrisisRunEngine(app_config)
    engine.select_crisis("nanjing-succession")
    detail = engine._replay_detail(
        {
            "event_type": "OFFER_PROPOSED",
            "payload": {
                "offer": {
                    "issuer": "han-zanzhou",
                    "recipient": "ma-shiying",
                    "terms": [
                        {
                            "type": "endorsement",
                            "subject": "fu-prince",
                            "value": "public_support",
                            "description": "对福王进入南京程序作出可被对方依赖的公开支持安排。",
                        }
                    ],
                    "message": "请明确回应这一公开支持条件。",
                }
            },
        }
    )

    assert "安排。。" not in detail
    assert detail.endswith("安排。请明确回应这一公开支持条件。")


def test_nanjing_pressure_can_lead_to_a_deferred_world_resolution_before_safety_horizon(
    app_config,
):
    engine = CrisisRunEngine(app_config, actor_driver=_DeferredProcedureDriver())
    run_id = engine.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]

    engine.run_until_idle(run_id)
    run = engine.run_summary(run_id)
    projection = engine.db.worldline_snapshot(run_id)["projection"]

    assert run["status"] == "SEALED"
    assert run["settlement_reason"] == "deferred_resolution"
    assert run["outcome_json"]["settlement_type"] == "DEFERRED"
    assert run["outcome_json"]["resolution_variant"] == "PROCEDURE_DEFERRED"
    assert int(run["current_tick"]) < int(run["maximum_tick"])
    assert projection["entities"]["nanjing-recognition"]["state"] == "DEFERRED"
    assert any(
        operation["definition_id"] == "defer_recognition_procedure"
        and operation["status"] == "COMPLETED"
        for operation in projection["operations"]
    )

from __future__ import annotations

from dataclasses import replace

from chronicle.crisis import AgreementTerm
from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode


def _passage_terms(perspective: dict) -> list[dict[str, str]]:
    term = next(
        item
        for item in perspective["available_offer_terms"]
        if item["type"] == "passage" and item["subject"]["id"] == "shanhai-pass"
    )
    return [
        {
            "type": term["type"],
            "subject": term["subject"]["id"],
            "value": term["value"],
            "description": term["description"],
        }
    ]


def _terms_with_value(perspective: dict, value: str) -> list[dict[str, str]]:
    term = next(
        item
        for item in perspective["available_offer_terms"]
        if item["type"] == "passage"
        and item["subject"]["id"] == "shanhai-pass"
        and item["value"] == value
    )
    return [
        {
            "type": term["type"],
            "subject": term["subject"]["id"],
            "value": term["value"],
            "description": term["description"],
        }
    ]


def test_manage_offer_requires_a_declared_term_and_stages_the_request(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    wake = next(
        item
        for item in engine.db.crisis_wakes(run_id, status="QUEUED")
        if item["actor_id"] == "wu-sangui"
    )
    engine.db.update_crisis_wake(wake["id"], status="RUNNING")
    world = engine.world.fixture_session(wake["id"], "wu-sangui")
    terms = _passage_terms(engine.actor_perspective(run_id, "wu-sangui"))

    assert engine.actor_perspective(run_id, "li-zicheng")["available_offer_terms"] == []

    rejected = world.manage_offer(
        "PROPOSE",
        recipient="dorgon",
        terms=[{**terms[0], "value": "denied"}],
        message="提出一个并不存在的条件。",
        idempotency_key="invalid-passage",
    )
    accepted = world.manage_offer(
        "PROPOSE",
        recipient="dorgon",
        terms=terms,
        message="允许清军按约定条件通过山海关。",
        expires_after_days=1,
        idempotency_key="passage-offer",
    )

    assert rejected == {"status": "rejected", "code": "offer_term_unavailable"}
    assert accepted["status"] == "accepted"
    assert accepted["expires_tick"] == 1
    assert engine.db.worldline_snapshot(run_id)["projection"]["offers"] == []


def test_offer_terms_take_their_display_description_from_the_crisis_pack(app_config):
    engine = CrisisRunEngine(app_config)
    perspective = engine.actor_perspective(
        engine.create(RunMode.WATCH)["run"]["id"], "wu-sangui"
    )
    term = _passage_terms(perspective)[0]

    canonical, code = engine.pack.offer_terms_request(
        "wu-sangui",
        "dorgon",
        [
            AgreementTerm.model_validate(
                {
                    "type": term["type"],
                    "subject": term["subject"],
                    "value": term["value"],
                }
            )
        ],
    )

    assert code == ""
    assert canonical is not None
    assert canonical[0].description == term["description"]


def test_accepted_agreement_unlocks_another_actor_operation_and_survives_restart(app_config):
    observed: dict[str, object] = {}

    class AgreementDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.operate(
                    "prepare_force",
                    ["qing-expedition-force"],
                    "先整备西征主力。",
                    idempotency_key="prepare-qing",
                )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.schedule_revisit(
                    after_days=2,
                    reason="待关外军力完成整备后重看通行条件。",
                    idempotency_key="offer-after-preparation",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OPERATION_RESULT":
                observed["before"] = {
                    item["id"] for item in perspective["available_operations"]
                }
            elif actor_id == "wu-sangui" and wake["wake_type"] == "REVISIT_DUE":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="若共同处置东部局势，可按约定条件通过山海关。",
                    idempotency_key="propose-passage",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
                world.manage_offer(
                    "ACCEPT",
                    offer_id=perspective["trigger"]["offer_id"],
                    idempotency_key="accept-passage",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "AGREEMENT_CHANGE":
                available = {item["id"] for item in perspective["available_operations"]}
                if "enter-shanhai-pass" in available:
                    observed["after"] = available
                    observed["restart"] = CrisisRunEngine(app_config).actor_perspective(
                        run_id, "dorgon"
                    )
                    world.operate(
                        "enter-shanhai-pass",
                        ["qing-expedition-force", "shanhaiguan"],
                        "依照已生效的通行约定进入山海关。",
                        idempotency_key="enter-with-passage",
                    )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=AgreementDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    assert "enter-shanhai-pass" not in observed["before"]
    assert "enter-shanhai-pass" in observed["after"]
    restarted_view = observed["restart"]
    assert restarted_view["active_agreements"][0]["status"] == "ACTIVE"
    assert "enter-shanhai-pass" in {
        item["id"] for item in restarted_view["available_operations"]
    }
    agreement = snapshot["agreements"][0]
    assert agreement["status"] == "FULFILLED"
    assert snapshot["positions"]["dorgon"] == "shanhaiguan"

    created = next(event for event in result["events"] if event["event_type"] == "AGREEMENT_CREATED")
    enter_started = next(
        event
        for event in result["events"]
        if event["event_type"] == "OPERATION_STARTED"
        and event["payload"]["operation"]["definition_id"] == "enter-shanhai-pass"
    )
    assert enter_started["causal_parent_ids"] == [created["id"]]
    agreement_wake = next(
        wake
        for wake in result["wakes"]
        if wake["actor_id"] == "dorgon"
        and wake["wake_type"] == "AGREEMENT_CHANGE"
        and wake["trigger_event_id"] == created["id"]
    )
    assert agreement_wake["status"] == "COMPLETED"


def test_counter_with_changed_terms_can_be_accepted_with_a_complete_source_lineage(app_config):
    class CounterDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="先提出通行条件。",
                    idempotency_key="initial-offer",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
                world.manage_offer(
                    "COUNTER",
                    offer_id=perspective["trigger"]["offer_id"],
                    terms=_terms_with_value(perspective, "limited"),
                    message="接受通行原则，但以共同处置为条件。",
                    idempotency_key="counter-offer",
                )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "OFFER_CHANGE":
                incoming = next(
                    offer
                    for offer in perspective["active_offers"]
                    if offer["recipient"] == "wu-sangui"
                )
                world.manage_offer(
                    "ACCEPT",
                    offer_id=incoming["id"],
                    idempotency_key="accept-counter",
                )
            return ActorTurnResult("保持有限行动。")

    base_pack = CrisisRunEngine(app_config).pack
    passage = next(
        term
        for term in base_pack.crisis.offer_terms
        if term.type.value == "passage" and term.subject == "shanhai-pass"
    )
    pack = replace(
        base_pack,
        crisis=base_pack.crisis.model_copy(
            update={
                "offer_terms": [
                    *base_pack.crisis.offer_terms,
                    passage.model_copy(
                        update={
                            "value": "limited",
                            "description": "允许清军在限定条件下通过山海关通道。",
                        }
                    ),
                ]
            }
        ),
    )
    pack.validate()
    engine = CrisisRunEngine(app_config, pack=pack, actor_driver=CounterDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    parent, counter = snapshot["offers"]
    agreement = snapshot["agreements"][0]
    assert parent["status"] == "COUNTERED"
    assert counter["status"] == "ACCEPTED"
    assert counter["parent_offer_id"] == parent["id"]
    assert agreement["status"] == "ACTIVE"
    assert agreement["source_offer_ids"] == [parent["id"], counter["id"]]


def test_counter_without_a_material_term_change_accepts_the_original_offer(app_config):
    class ReaffirmingDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="先提出通行条件。",
                    idempotency_key="initial-offer",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
                world.manage_offer(
                    "COUNTER",
                    offer_id=perspective["trigger"]["offer_id"],
                    terms=_passage_terms(perspective),
                    message="条款不变，但希望重申共同处置的来意。",
                    idempotency_key="reaffirm-offer",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=ReaffirmingDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]
    events = engine.db.worldline_events(run_id)

    assert len(snapshot["offers"]) == 1
    assert snapshot["offers"][0]["status"] == "ACCEPTED"
    assert snapshot["agreements"][0]["source_offer_ids"] == [snapshot["offers"][0]["id"]]
    accepted = next(event for event in events if event["event_type"] == "OFFER_ACCEPTED")
    assert accepted["payload"]["normalized_from"] == "COUNTER"


def test_offer_can_be_rejected_then_a_later_offer_withdrawn(app_config):
    class RejectionDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="first",
                    idempotency_key="first-offer",
                )
                world.schedule_revisit(
                    after_days=1,
                    reason="重看第一项条件的回应。",
                    idempotency_key="first-revisit",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
                if perspective["trigger"]["message"] == "first":
                    world.manage_offer(
                        "REJECT",
                        offer_id=perspective["trigger"]["offer_id"],
                        idempotency_key="reject-first",
                    )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "REVISIT_DUE":
                outgoing = next(
                    (
                        offer
                        for offer in perspective["active_offers"]
                        if offer["issuer"] == "wu-sangui"
                    ),
                    None,
                )
                if outgoing is None:
                    world.manage_offer(
                        "PROPOSE",
                        recipient="dorgon",
                        terms=_passage_terms(perspective),
                        message="second",
                        idempotency_key="second-offer",
                    )
                    world.schedule_revisit(
                        after_days=1,
                        reason="重看第二项条件是否仍需保留。",
                        idempotency_key="second-revisit",
                    )
                else:
                    world.manage_offer(
                        "WITHDRAW",
                        offer_id=outgoing["id"],
                        idempotency_key="withdraw-second",
                    )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=RejectionDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    first, second = snapshot["offers"]
    assert [first["status"], second["status"]] == ["REJECTED", "WITHDRAWN"]
    rejected = next(event for event in result["events"] if event["event_type"] == "OFFER_REJECTED")
    withdrawn = next(event for event in result["events"] if event["event_type"] == "OFFER_WITHDRAWN")
    assert {wake["actor_id"] for wake in result["wakes"] if wake["trigger_event_id"] == rejected["id"]} == {
        "wu-sangui"
    }
    assert {wake["actor_id"] for wake in result["wakes"] if wake["trigger_event_id"] == withdrawn["id"]} == {
        "dorgon"
    }


def test_unanswered_offer_expires_and_only_wakes_its_parties(app_config):
    class ExpiryDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="一日内请明确回应。",
                    expires_after_days=1,
                    idempotency_key="expiring-offer",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=ExpiryDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    assert snapshot["offers"][0]["status"] == "EXPIRED"
    expired = next(event for event in result["events"] if event["event_type"] == "OFFER_EXPIRED")
    expiry_wakes = [
        wake for wake in result["wakes"] if wake["trigger_event_id"] == expired["id"]
    ]
    assert {wake["actor_id"] for wake in expiry_wakes} == {"wu-sangui", "dorgon"}
    assert {wake["wake_type"] for wake in expiry_wakes} == {"OFFER_CHANGE"}


def test_real_operation_can_breach_an_active_agreement_only_for_its_parties(app_config):
    dorgon_agreement_statuses: list[str] = []

    class BreachDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.operate(
                    "prepare_force",
                    ["wu-field-force"],
                    "先整备关宁所部。",
                    idempotency_key="prepare-wu",
                )
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="同意按条件通行。",
                    idempotency_key="offer-passage",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "OFFER_CHANGE":
                world.manage_offer(
                    "ACCEPT",
                    offer_id=perspective["trigger"]["offer_id"],
                    idempotency_key="accept-passage",
                )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "OPERATION_RESULT":
                if any(
                    item["id"] == "secure-shanhai-pass"
                    for item in perspective["available_operations"]
                ):
                    world.operate(
                        "secure-shanhai-pass",
                        ["wu-field-force", "shanhai-pass"],
                        "封闭山海关通道。",
                        idempotency_key="close-pass",
                    )
            elif actor_id == "dorgon" and wake["wake_type"] == "AGREEMENT_CHANGE":
                dorgon_agreement_statuses.append(str(perspective["trigger"]["status"]))
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=BreachDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    agreement = snapshot["agreements"][0]
    assert agreement["status"] == "BREACHED"
    assert snapshot["entities"]["shanhai-pass"]["state"] == "CLOSED"
    assert dorgon_agreement_statuses == ["ACTIVE", "BREACHED"]
    breached = next(event for event in result["events"] if event["event_type"] == "AGREEMENT_BREACHED")
    breach_wakes = [
        wake for wake in result["wakes"] if wake["trigger_event_id"] == breached["id"]
    ]
    assert breached["payload"]["visibility"] == ["dorgon", "wu-sangui"]
    assert {wake["actor_id"] for wake in breach_wakes} == {"dorgon", "wu-sangui"}
    assert {wake["wake_type"] for wake in breach_wakes} == {"AGREEMENT_CHANGE"}
    assert engine.actor_perspective(run_id, "li-zicheng")["active_agreements"] == []


def test_private_operation_does_not_reveal_an_agreement_breach_to_an_unaware_party(app_config):
    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    projection = engine.db.worldline_snapshot(run_id)["projection"]
    agreement = {
        "id": "agreement-private-breach",
        "parties": ["wu-sangui", "dorgon"],
        "terms": [
            {
                "type": "passage",
                "subject": "shanhai-pass",
                "value": "permitted",
                "description": "允许清军按约定条件通过山海关通道。",
            }
        ],
        "effective_tick": 0,
        "status": "ACTIVE",
    }
    projection["agreements"] = [agreement]

    events, queued = engine._operation_agreement_outcomes(
        run_id,
        1,
        projection,
        {"id": "operation-private-close", "actor_id": "wu-sangui"},
        engine.pack.operation_by_id["secure-shanhai-pass"],
        visible_actor_ids=["wu-sangui"],
        causal_parent_id="event-private-close",
    )

    assert agreement["status"] == "BREACHED"
    assert events[0]["payload"]["visibility"] == ["wu-sangui"]
    assert queued == {("wu-sangui", events[0]["id"])}


def test_same_moment_offer_conflict_becomes_a_world_refusal_not_a_run_failure(app_config):
    class CompetingOfferDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.schedule_revisit(
                    after_days=1,
                    reason="明日再决定是否接受通行条件。",
                    idempotency_key="dorgon-revisit",
                )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="dorgon",
                    terms=_passage_terms(perspective),
                    message="请接受通行条件。",
                    idempotency_key="offer-for-race",
                )
                world.schedule_revisit(
                    after_days=1,
                    reason="明日若无定论便撤回条件。",
                    idempotency_key="wu-revisit",
                )
            elif actor_id == "dorgon" and wake["wake_type"] == "REVISIT_DUE":
                incoming = next(
                    offer
                    for offer in perspective["active_offers"]
                    if offer["recipient"] == "dorgon"
                )
                world.manage_offer(
                    "ACCEPT",
                    offer_id=incoming["id"],
                    idempotency_key="accept-at-revisit",
                )
            elif actor_id == "wu-sangui" and wake["wake_type"] == "REVISIT_DUE":
                outgoing = next(
                    offer
                    for offer in perspective["active_offers"]
                    if offer["issuer"] == "wu-sangui"
                )
                world.manage_offer(
                    "WITHDRAW",
                    offer_id=outgoing["id"],
                    idempotency_key="withdraw-at-revisit",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=CompetingOfferDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    result = engine.run_until_idle(run_id)
    snapshot = engine.db.worldline_snapshot(run_id)["projection"]

    assert snapshot["offers"][0]["status"] == "ACCEPTED"
    assert snapshot["agreements"][0]["status"] == "ACTIVE"
    dorgon_wake = next(
        wake
        for wake in result["wakes"]
        if wake["actor_id"] == "dorgon" and wake["wake_type"] == "REVISIT_DUE"
    )
    wu_wake = next(
        wake
        for wake in result["wakes"]
        if wake["actor_id"] == "wu-sangui" and wake["wake_type"] == "REVISIT_DUE"
    )
    withdraw = next(
        operation
        for operation in engine.db.crisis_wake_operations(wu_wake["id"])
        if operation["tool_name"] == "manage_offer"
    )
    assert dorgon_wake["tick"] == wu_wake["tick"] == 1
    assert withdraw["status"] == "REJECTED"
    assert withdraw["result"] == {"status": "rejected", "code": "offer_not_open"}
    assert any(
        event["event_type"] == "ACTOR_TOOL_REJECTED"
        and event["seat_id"] == "wu-sangui"
        and event["payload"]["code"] == "offer_not_open"
        for event in result["events"]
    )

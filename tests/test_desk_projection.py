from __future__ import annotations

from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
from chronicle.decision import DecisionOperation, InterpretedDecision


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


def test_desk_projects_ongoing_investigation_then_its_private_observation(app_config):
    class InvestigationInterpreter:
        source = "fixture"

        def interpret(self, text, perspective):
            return InterpretedDecision(
                summary="先核实山海关近况。",
                operations=[
                    DecisionOperation(
                        tool="investigate",
                        arguments={
                            "question": "山海关是否已有可核验的公开通行安排？",
                            "target": "shanhai-pass",
                            "method": "courier_report",
                        },
                    )
                ],
            )

    engine = CrisisRunEngine(app_config)
    run_id = engine.create(RunMode.TAKEOVER)["run"]["id"]

    initial = engine.product_perspective(run_id, "wu-sangui")["desk"]
    assert set(initial) == {"arrivals", "unresolved", "ongoing", "agreements"}
    assert any(item["kind"] == "MESSAGE" for item in initial["ongoing"])

    engine.submit_human_decision(
        run_id,
        "先查问山海关近况。",
        interpreter=InvestigationInterpreter(),
    )
    in_progress = engine.product_perspective(run_id, "wu-sangui")["desk"]
    investigation = next(item for item in in_progress["ongoing"] if item["kind"] == "INVESTIGATION")
    assert investigation["title"] == "查问山海关近况正在进行"
    assert investigation["expected_tick"] == 2

    engine.run_until_idle(run_id)
    recovered = CrisisRunEngine(app_config).product_perspective(run_id, "wu-sangui")["desk"]
    arrival = next(item for item in recovered["arrivals"] if item["kind"] == "INVESTIGATION")
    assert arrival["title"] == "调查回报"
    assert arrival["source"] == "沿线来人与关口往来文书的交叉转述"
    assert arrival["reliability"] == "MEDIUM"
    assert not any(item["kind"] == "INVESTIGATION" for item in recovered["ongoing"])
    li_desk = CrisisRunEngine(app_config).product_perspective(run_id, "li-zicheng")["desk"]
    assert not any(item["kind"] == "INVESTIGATION" for item in li_desk["arrivals"])
    assert not any(item["kind"] == "INVESTIGATION" for item in li_desk["ongoing"])


def test_desk_turns_an_incoming_offer_into_a_real_unresolved_matter(app_config):
    class IncomingOfferDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "dorgon" and wake["wake_type"] == "ORIENT":
                world.manage_offer(
                    "PROPOSE",
                    recipient="wu-sangui",
                    terms=_passage_terms(perspective),
                    message="若通行可以明确，愿共同处置东部局势。",
                    idempotency_key="propose-passage",
                )
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=IncomingOfferDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)

    wu_desk = engine.product_perspective(run_id, "wu-sangui")["desk"]
    dorgon_desk = engine.product_perspective(run_id, "dorgon")["desk"]
    li_desk = engine.product_perspective(run_id, "li-zicheng")["desk"]

    offer = next(item for item in wu_desk["unresolved"] if item["kind"] == "OFFER")
    arrival = next(item for item in wu_desk["arrivals"] if item["kind"] == "OFFER")
    assert offer["title"] == "多尔衮等待你的答复"
    assert offer["terms"] == ["允许清军在约定条件下通过山海关通道。"]
    assert arrival["title"] == "多尔衮提出条件"
    assert any(item["kind"] == "OFFER" for item in dorgon_desk["ongoing"])
    assert not any(item["kind"] == "OFFER" for item in li_desk["unresolved"])


def test_desk_shows_active_agreements_only_to_their_parties(app_config):
    class AgreementDriver:
        source = "fixture"

        def run_wake(self, actor_id, wake, perspective, world):
            if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
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
            return ActorTurnResult("保持有限行动。")

    engine = CrisisRunEngine(app_config, actor_driver=AgreementDriver())
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)

    wu_agreement = engine.product_perspective(run_id, "wu-sangui")["desk"]["agreements"]
    dorgon_agreement = engine.product_perspective(run_id, "dorgon")["desk"]["agreements"]
    li_agreement = engine.product_perspective(run_id, "li-zicheng")["desk"]["agreements"]

    assert wu_agreement[0]["title"] == "与多尔衮的约定"
    assert dorgon_agreement[0]["title"] == "与吴三桂的约定"
    assert wu_agreement[0]["terms"] == ["允许清军在约定条件下通过山海关通道。"]
    assert li_agreement == []

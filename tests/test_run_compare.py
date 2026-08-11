from __future__ import annotations

import json

from fastapi.testclient import TestClient

from chronicle.app import create_app
from chronicle.crisis_runtime import ActorTurnResult, CrisisRunEngine, RunMode
from chronicle.replay_projection import compare_material_runs


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


class _PassageDriver:
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
                reason="待关外军力完成整备后重新判断通行条件。",
                idempotency_key="offer-after-preparation",
            )
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
            if "enter-shanhai-pass" in {
                item["id"] for item in perspective["available_operations"]
            }:
                world.operate(
                    "enter-shanhai-pass",
                    ["qing-expedition-force", "shanhaiguan"],
                    "依照已生效的通行约定进入山海关。",
                    idempotency_key="enter-with-passage",
                )
        return ActorTurnResult("保持有限行动。")


class _ClosureDriver:
    source = "fixture"

    def __init__(self):
        self.closed = False

    def run_wake(self, actor_id, wake, perspective, world):
        available = {item["id"] for item in perspective.get("available_operations", [])}
        if actor_id == "wu-sangui" and wake["wake_type"] == "ORIENT":
            world.operate(
                "prepare_force",
                ["wu-field-force"],
                "先整备关宁所部。",
                idempotency_key="prepare-wu",
            )
        elif (
            actor_id == "wu-sangui"
            and wake["wake_type"] == "OPERATION_RESULT"
            and "secure-shanhai-pass" in available
            and not self.closed
        ):
            world.operate(
                "secure-shanhai-pass",
                ["wu-field-force", "shanhai-pass"],
                "封闭山海关通道。",
                idempotency_key="close-pass",
            )
            self.closed = True
        return ActorTurnResult("保持有限行动。")


def _settled_run(app_config, driver) -> str:
    engine = CrisisRunEngine(app_config, actor_driver=driver)
    run_id = engine.create(RunMode.WATCH)["run"]["id"]
    engine.run_until_idle(run_id)
    assert engine.run_summary(run_id)["crisis_phase"] == "SETTLED"
    return run_id


def test_compare_ignores_message_wording_when_information_state_is_unchanged():
    left = [
        {
            "id": "event-left",
            "tick": 2,
            "event_type": "MESSAGE_DELIVERED",
            "payload": {
                "sender": "actor-a",
                "recipient": "actor-b",
                "arrival_tick": 2,
                "content": "以甲种措辞重申同一封信。",
            },
            "causal_parent_ids": [],
        }
    ]
    right = [
        {
            "id": "event-right",
            "tick": 2,
            "event_type": "MESSAGE_DELIVERED",
            "payload": {
                "sender": "actor-a",
                "recipient": "actor-b",
                "arrival_tick": 2,
                "content": "以乙种措辞重申同一封信。",
            },
            "causal_parent_ids": [],
        }
    ]

    comparison = compare_material_runs(
        left,
        right,
        project_event=lambda event: {"text": event["event_type"]},
    )

    assert comparison["first_material_divergence"] is None


def test_same_crisis_compare_projects_a_world_fork_and_outcome_difference(app_config):
    passage_run = _settled_run(app_config, _PassageDriver())
    closure_run = _settled_run(app_config, _ClosureDriver())

    comparison = CrisisRunEngine(app_config).compare(passage_run, closure_run)

    fork = comparison["first_material_divergence"]
    assert comparison["crisis"] == {
        "id": "before-shanhaiguan",
        "title": "山海关之前",
        "subtitle": "三封未决的信，四处仍在移动的人",
    }
    assert comparison["runs"]["left"]["id"] == passage_run
    assert comparison["runs"]["right"]["id"] == closure_run
    assert fork is not None
    assert fork["tick"] == 0
    assert fork["left"][0]["category"] == "行动"
    assert fork["right"][0]["category"] == "行动"
    assert comparison["outcome_difference"]["same"] is False
    assert comparison["outcome_difference"]["left"]["summary"]
    assert comparison["outcome_difference"]["right"]["critical_realities"]
    assert any(
        path["entered_outcome"]
        for path in comparison["consequence_paths"].values()
        if isinstance(path, dict) and "entered_outcome" in path
    )
    assert "event-" not in json.dumps(comparison, ensure_ascii=False)
    assert "resolution_variant" not in comparison
    assert comparison == CrisisRunEngine(app_config).compare(passage_run, closure_run)


def test_compare_api_requires_two_settled_runs_from_the_same_crisis(app_config):
    passage_run = _settled_run(app_config, _PassageDriver())
    closure_run = _settled_run(app_config, _ClosureDriver())
    client = TestClient(create_app(app_config))

    response = client.get("/api/compare", params={"left": passage_run, "right": closure_run})

    assert response.status_code == 200
    assert response.json()["first_material_divergence"]["tick"] == 0

    nanjing = CrisisRunEngine(app_config)
    nanjing_run = nanjing.create(RunMode.WATCH, crisis_id="nanjing-succession")["run"]["id"]
    nanjing.seal(nanjing_run, "test_complete")
    mismatch = client.get("/api/compare", params={"left": passage_run, "right": nanjing_run})
    duplicate = client.get("/api/compare", params={"left": passage_run, "right": passage_run})

    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "compare_crisis_mismatch"
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "compare_runs_must_differ"

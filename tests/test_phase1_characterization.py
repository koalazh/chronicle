from chronicle.crisis_lifecycle import next_simulation_tick
from chronicle.crisis_projection import build_actor_perspective, same_material_plan
from chronicle.crisis_wakes import wake_batches
from chronicle.editorial import watch_attention


def test_phase1_editorial_attention_ignores_checkpoint_messages():
    assert watch_attention(
        [
            {
                "id": "checkpoint-message",
                "tick": 0,
                "event_type": "MESSAGE_DISPATCHED",
                "payload": {"source": "checkpoint"},
            },
            {
                "id": "public-pressure",
                "tick": 2,
                "event_type": "PRESSURE_APPLIED",
                "payload": {},
            },
        ]
    ) == {
        "mode": "WATCH",
        "tick": 2,
        "event_id": "public-pressure",
        "event_type": "PRESSURE_APPLIED",
    }


def test_phase1_wake_batches_preserve_priority_and_coalesce_inputs():
    wakes = [
        {"id": "message", "wake_type": "MESSAGE", "trigger_event_id": "m"},
        {"id": "operation", "wake_type": "OPERATION_RESULT", "trigger_event_id": "o"},
        {"id": "orient", "wake_type": "ORIENT", "trigger_event_id": ""},
    ]

    assert [[wake["id"] for wake in batch] for batch in wake_batches(wakes)] == [
        ["operation", "message"],
        ["orient"],
    ]


def test_phase1_next_tick_combines_world_and_wake_due_effects():
    projection = {
        "messages": [{"arrival_tick": 4, "status": "in_transit"}],
        "operations": [{"expected_complete_tick": 6, "status": "IN_PROGRESS"}],
        "investigations": [],
        "offers": [{"expires_tick": 3, "status": "PROPOSED"}],
        "pressures": [{"trigger_tick": 5, "status": "PENDING"}],
        "movements": [],
        "resolution_reports": [],
    }

    assert next_simulation_tick(
        projection,
        [{"tick": 2}],
    ) == 2
    assert next_simulation_tick(projection, []) == 3


def test_phase1_plan_characterization_ignores_punctuation_and_whitespace():
    assert same_material_plan(
        {"objective": "守住东部。", "steps": ["等待 回音"], "reconsider_when": ["来信"]},
        {"objective": " 守住东部 ", "steps": ["等待回音"], "reconsider_when": ["来信"]},
    )


def test_phase1_perspective_assembly_keeps_private_fields_separate():
    perspective = build_actor_perspective(
        run_id="run-1",
        actor_id="wu-sangui",
        projection={"tick": 3, "positions": {"wu-sangui": "shanhai-pass"}},
        knowledge=["known-event"],
        beliefs={"dorgon": {"assessment": "uncertain"}},
        plan=[{"objective": "hold"}],
        revisits=[],
        resources={"force": 1},
        authority=["military"],
        affordances={"available_operations": []},
    )

    assert perspective == {
        "run_id": "run-1",
        "actor_id": "wu-sangui",
        "tick": 3,
        "location": "shanhai-pass",
        "knowledge": ["known-event"],
        "beliefs": {"dorgon": {"assessment": "uncertain"}},
        "plan": [{"objective": "hold"}],
        "revisits": [],
        "resources": {"force": 1},
        "authority": ["military"],
        "available_operations": [],
    }

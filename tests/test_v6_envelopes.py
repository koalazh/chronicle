from __future__ import annotations

from dataclasses import replace

import pytest

from chronicle.crisis import CrisisActivationPrecondition, CrisisActivationPreconditionKind
from chronicle.models import CrisisInstanceStatus
from chronicle.volume_runtime import VolumeRuntimeConflict


def test_volume_registers_envelopes_and_activates_only_eligible_crises(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]

    assert {
        item["status"] for item in runtime.db.crisis_instances(worldline_id)
    } == {CrisisInstanceStatus.DORMANT.value}

    runtime.reconcile_crisis_envelopes(worldline_id)
    instances = {
        item["crisis_id"]: item for item in runtime.db.crisis_instances(worldline_id)
    }
    projection = runtime.worldline(worldline_id)["projection"]

    assert instances["before-shanhaiguan"]["status"] == CrisisInstanceStatus.ACTIVE.value
    assert instances["nanjing-succession"]["status"] == CrisisInstanceStatus.ACTIVE.value
    assert instances["southern-consolidation"]["status"] == CrisisInstanceStatus.DORMANT.value
    assert projection["active_crisis_ids"] == [
        "before-shanhaiguan",
        "nanjing-succession",
    ]
    assert projection["crisis_instances"]["southern-consolidation"]["envelope"][
        "activation_preconditions"
    ][0]["crisis_id"] == "nanjing-succession"
    assert [
        event["event_type"] for event in runtime.db.worldline_events(worldline_id)
    ].count("CRISIS_ENVELOPE_REGISTERED") == 3


def test_southern_envelope_requires_nanjing_settlement_and_shared_center(host):
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
    runtime.reconcile_crisis_envelopes(worldline_id)

    with pytest.raises(VolumeRuntimeConflict, match="precondition nanjing-settlement"):
        runtime.activate_crisis(worldline_id, "southern-consolidation")

    settled = runtime.settle_crisis(
        worldline_id,
        "nanjing-succession",
        outcome={"summary": "南都定策留下可执行的江北问题"},
    )
    instances = {
        item["crisis_id"]: item for item in runtime.db.crisis_instances(worldline_id)
    }
    assert instances["southern-consolidation"]["status"] == CrisisInstanceStatus.DORMANT.value
    assert not any(
        event["event_type"] == "CRISIS_ACTIVATED"
        and event["payload"]["crisis_id"] == "southern-consolidation"
        for event in settled["events"]
    )
    assert runtime.worldline(worldline_id)["projection"]["entities"][
        "nanjing-political-center"
    ]["state"] == "UNFORMED"

    repeated = runtime.reconcile_crisis_envelopes(worldline_id)
    assert repeated["events"] == []
    with pytest.raises(VolumeRuntimeConflict, match="nanjing-political-center"):
        runtime.activate_crisis(worldline_id, "southern-consolidation")


def test_suppressed_precondition_is_persisted_without_activation(host):
    runtime = host.volume_runtime
    references = []
    for reference in runtime.pack.volume.crises:
        if reference.id == "before-shanhaiguan":
            references.append(reference.model_copy(update={"earliest_activation_tick": 99}))
        elif reference.id == "southern-consolidation":
            references.append(
                reference.model_copy(
                    update={
                        "activation_preconditions": [
                            CrisisActivationPrecondition(
                                id="before-suppression",
                                kind=CrisisActivationPreconditionKind.CRISIS_STATUS,
                                description="结构性消失后不再激活下游局势。",
                                crisis_id="before-shanhaiguan",
                                required_statuses=[CrisisInstanceStatus.ACTIVE.value],
                                suppressed_statuses=[CrisisInstanceStatus.SUPPRESSED.value],
                            )
                        ]
                    }
                )
            )
        else:
            references.append(reference)
    runtime.pack = replace(
        runtime.pack,
        volume=runtime.pack.volume.model_copy(update={"crises": references}),
    )
    worldline_id = runtime.create()["worldline"]["id"]
    runtime._suppress_dormant_crisis(
        worldline_id, "before-shanhaiguan", "required institution no longer exists"
    )

    runtime.reconcile_crisis_envelopes(worldline_id)
    instances = {
        item["crisis_id"]: item for item in runtime.db.crisis_instances(worldline_id)
    }
    assert instances["before-shanhaiguan"]["status"] == CrisisInstanceStatus.SUPPRESSED.value
    assert instances["southern-consolidation"]["status"] == CrisisInstanceStatus.SUPPRESSED.value
    assert instances["nanjing-succession"]["status"] == CrisisInstanceStatus.ACTIVE.value
    assert [
        event["event_type"] for event in runtime.db.worldline_events(worldline_id)
    ].count("CRISIS_SUPPRESSED") == 2

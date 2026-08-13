from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace

from chronicle.host import ChronicleHost


def test_v6_proof_receipt_is_machine_readable_and_secret_free(app_config):
    config = replace(
        app_config,
        database_path=app_config.database_path.with_name("chronicle-v6-proof-receipt.db"),
        runtime_dir=app_config.runtime_dir / "v6-proof-receipt",
        hermes_home=app_config.hermes_home / "v6-proof-receipt",
    )
    host = ChronicleHost(config)
    runtime = host.volume_runtime
    worldline_id = runtime.create()["worldline"]["id"]
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
            "objective": "暂守关口",
            "steps": ["继续核验"],
            "open_dependencies": [],
        },
        source="agent",
        idempotency_key="v6-proof-receipt-course",
    )
    runtime.commit_pending_moment(worldline_id)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/v6_proof_receipt.py",
            str(config.database_path),
            worldline_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout)

    assert receipt["worldline_hash"]
    assert receipt["event_counts"]["DECISION_HORIZON_ESTABLISHED"] == 1
    assert receipt["deliberations"]["count"] == 0
    assert receipt["causal_links"]
    assert "暂守关口" not in completed.stdout
    assert "proposal" not in completed.stdout

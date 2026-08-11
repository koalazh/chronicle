from __future__ import annotations

from chronicle.db import ChronicleDB
from chronicle.models import Controller, CrisisInstanceStatus, WorldlineKind, WorldlineStatus


def test_v10_schema_exposes_volume_instance_lifetime_and_binding_fields(tmp_path):
    db = ChronicleDB(tmp_path / "chronicle.db")

    with db.transaction() as connection:
        worldline_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(worldlines)")
        }
        lifetime_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(worldline_lifetimes)")
        }
        binding_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worldline_agent_bindings)")
        }
        instance_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(worldline_crisis_instances)")
        }

    assert db.get_meta("schema_version") == "10"
    assert {
        "worldline_phase",
        "volume_content_version",
        "volume_content_hash",
        "boundary_policy_id",
        "safety_horizon_tick",
        "human_lifetime_id",
    }.issubset(worldline_columns)
    assert {"lifetime_kind", "genesis_context_json", "profile_state"}.issubset(lifetime_columns)
    assert {
        "lifetime_id",
        "binding_scope",
        "volume_id",
        "content_version",
        "content_hash",
        "genesis_hash",
        "runtime_epoch",
    }.issubset(binding_columns)
    assert {
        "worldline_id",
        "crisis_id",
        "content_version",
        "content_hash",
        "status",
        "phase",
        "activation_tick",
        "local_origin_tick",
        "settled_tick",
        "outcome_json",
        "suppression_reason",
    }.issubset(instance_columns)


def test_v10_migration_is_additive_and_repeat_open_is_idempotent(tmp_path):
    path = tmp_path / "chronicle.db"
    db = ChronicleDB(path)
    db.create_worldline(
        {
            "id": "legacy-v4-run",
            "kind": "CRISIS",
            "status": WorldlineStatus.ACTIVE.value,
            "current_tick": 12,
            "runtime_mode": "fixture",
        }
    )
    with db.transaction() as connection:
        connection.execute("UPDATE app_meta SET value = '9' WHERE key = 'schema_version'")

    migrated = ChronicleDB(path)
    assert migrated.get_meta("schema_version") == "10"
    assert migrated.migration_backup_path is not None
    assert ".pre-v10." in migrated.migration_backup_path.name
    assert migrated.worldline("legacy-v4-run")["status"] == WorldlineStatus.ACTIVE.value

    reopened = ChronicleDB(path)
    assert reopened.get_meta("schema_version") == "10"
    assert reopened.migration_backup_path is None
    assert reopened.worldline("legacy-v4-run")["status"] == WorldlineStatus.ACTIVE.value


def test_volume_crisis_instance_and_lifetime_profile_binding_are_persistent(tmp_path):
    db = ChronicleDB(tmp_path / "chronicle.db")
    volume = db.create_worldline(
        {
            "id": "volume-jiashen",
            "scenario_id": "jiashen",
            "kind": WorldlineKind.VOLUME.value,
            "status": WorldlineStatus.ACTIVE.value,
            "current_tick": 100,
            "runtime_epoch": "epoch-v5",
            "volume_id": "jiashen",
            "volume_content_version": 1,
            "volume_content_hash": "volume-hash",
            "worldline_phase": "READY",
            "boundary_policy_id": "jiashen-v5",
            "safety_horizon_tick": 160,
            "human_lifetime_id": "lifetime-wu",
        }
    )
    assert volume["kind"] == WorldlineKind.VOLUME.value
    assert db.active_volume_worldline()["id"] == "volume-jiashen"

    lifetime = db.create_worldline_lifetime(
        {
            "id": "lifetime-wu",
            "worldline_id": "volume-jiashen",
            "seat": "wu-sangui",
            "controller": Controller.HUMAN.value,
            "lifetime_kind": "ACTOR",
            "profile_name": "chronicle-volume-jiashen-lifetime-wu",
            "profile_state": "DORMANT",
            "genesis_hash": "genesis-wu",
            "genesis_context": {
                "display_name": "Wu Sangui",
                "starting_location": "shanhaiguan",
            },
        }
    )
    assert lifetime["controller"] == Controller.HUMAN.value
    assert lifetime["genesis_context"] == {
        "display_name": "Wu Sangui",
        "starting_location": "shanhaiguan",
    }
    assert lifetime["profile_state"] == "DORMANT"

    binding = db.create_agent_binding(
        {
            "id": "binding-wu",
            "worldline_id": "volume-jiashen",
            "actor_id": "wu-sangui",
            "lifetime_id": "lifetime-wu",
            "binding_scope": "LIFETIME",
            "profile_name": lifetime["profile_name"],
            "ownership_marker": "marker-wu",
            "token_hash": "token-wu",
            "volume_id": "jiashen",
            "content_version": 1,
            "content_hash": "volume-hash",
            "genesis_hash": "genesis-wu",
            "runtime_epoch": "epoch-v5",
        }
    )
    assert binding["lifetime_id"] == "lifetime-wu"
    assert binding["binding_scope"] == "LIFETIME"
    assert binding["profile_identity"] == lifetime["profile_name"]

    instance = db.create_crisis_instance(
        {
            "id": "instance-shanhaiguan",
            "worldline_id": "volume-jiashen",
            "crisis_id": "before-shanhaiguan",
            "content_version": 1,
            "content_hash": "crisis-hash",
            "status": CrisisInstanceStatus.ACTIVE.value,
            "phase": "OPEN",
            "activation_tick": 100,
            "local_origin_tick": 0,
            "resolution_contract_id": "shanhaiguan-v1",
            "resolution_contract_version": 1,
            "resolution_seed": "seed-1",
        }
    )
    assert instance["status"] == CrisisInstanceStatus.ACTIVE.value
    assert instance["outcome"] == {}
    assert db.crisis_instances("volume-jiashen", status=CrisisInstanceStatus.ACTIVE.value) == [instance]

    db.update_worldline_lifetime(
        "volume-jiashen",
        "wu-sangui",
        controller=Controller.AGENT.value,
    )
    settled = db.update_crisis_instance(
        "instance-shanhaiguan",
        status=CrisisInstanceStatus.SETTLED.value,
        phase="AFTERMATH",
        settled_tick=118,
        outcome={"kind": "historical_settlement"},
    )

    assert db.worldline_lifetime("volume-jiashen", "wu-sangui")["controller"] == Controller.AGENT.value
    assert settled["status"] == CrisisInstanceStatus.SETTLED.value
    assert settled["outcome"] == {"kind": "historical_settlement"}
    assert db.worldline("volume-jiashen")["status"] == WorldlineStatus.ACTIVE.value
    assert db.worldline("volume-jiashen")["current_tick"] == 100
    assert db.worldline_events("volume-jiashen") == []

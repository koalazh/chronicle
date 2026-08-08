from __future__ import annotations

import json
import sqlite3

import pytest

from chronicle.config import write_runtime_env
from chronicle.models import WakeType


def test_host_has_one_way_canon_clock(host):
    assert host.current_tick == 0
    assert host.set_tick(4) == 4
    with pytest.raises(ValueError, match="cannot move backwards"):
        host.set_tick(3)


def test_runtime_input_is_opaque_and_seat_scoped(host):
    runtime_input = host._runtime_input("A", 44, WakeType.OBSERVATION)
    encoded = json.dumps(runtime_input, ensure_ascii=False)
    assert runtime_input["seat"] == "Seat A"
    assert runtime_input["observations"]
    assert "崇祯" not in encoded
    assert "李自成" not in encoded
    assert "吴三桂" not in encoded
    assert "北京" not in encoded
    assert "太原" not in encoded
    assert host.pack.who_knows("a019", 44) == {"A": True, "B": False, "C": False}


def test_observation_wake_cannot_mutate_memory(host):
    before_text, before_hash = host.db.current_memory("A")
    result = host.wake("A", tick=4, wake_type=WakeType.OBSERVATION)
    after_text, after_hash = host.db.current_memory("A")
    assert result["source"] == "fixture"
    assert result["memory"]["changed"] is False
    assert (after_text, after_hash) == (before_text, before_hash)
    assert host.db.memory_versions("A") == []
    assert len(host.db.life_records("A")) == 1


def test_reflection_creates_a_memory_version(host):
    observation = host.wake("A", tick=4, wake_type=WakeType.OBSERVATION)
    result = host.wake(
        "A",
        tick=8,
        wake_type=WakeType.REFLECTION,
        outcome="The later report arrived after the decision.",
    )
    versions = host.db.memory_versions("A")
    assert observation["memory"]["changed"] is False
    assert result["memory"]["changed"] is True
    assert len(versions) == 1
    assert versions[0]["mutation_kind"] == "reflection"
    assert versions[0]["previous_hash"] == observation["memory"]["after_hash"]
    assert json.loads(versions[0]["source_record_ids"]) == [result["life_record_id"]]


def test_life_records_are_append_only(host):
    host.wake("A", tick=4)
    record_id = host.db.life_records("A")[0]["id"]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with host.db.transaction() as connection:
            connection.execute("UPDATE life_records SET tick = 9 WHERE id = ?", (record_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with host.db.transaction() as connection:
            connection.execute("DELETE FROM life_records WHERE id = ?", (record_id,))


def test_live_input_and_lifetime_read_native_hermes_memory(host, app_config):
    memory_path = host._native_memory_path("A")
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("A compact lesson carried by Hermes.", encoding="utf-8")
    write_runtime_env(
        app_config,
        {"CHRONICLE_CHRONICLE_SEAT_A_API_SERVER_KEY": "test-profile-key-123456"},
    )

    runtime_input = host._runtime_input("A", 4, WakeType.OBSERVATION, live=True)
    lifetime = host.lifetime("A")
    assert runtime_input["subjective_memory"] == "A compact lesson carried by Hermes."
    assert lifetime["memory"]["text"] == "A compact lesson carried by Hermes."
    assert lifetime["memory"]["hash"] == host._native_memory("A")[1]

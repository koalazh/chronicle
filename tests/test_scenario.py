from __future__ import annotations


def test_source_pack_is_complete(pack):
    assert len(pack.sources) == 4
    assert len(pack.assertions) == 36
    assert len(pack.events) == 36
    assert {actor.seat for actor in pack.actors} == {"A", "B", "C"}
    assert pack.fork.event_id == "e019"
    assert pack.fork.max_days == 14


def test_observations_are_delivered_by_tick(pack):
    assert pack.who_knows("a019", 44) == {"A": True, "B": False, "C": False}
    assert pack.who_knows("a019", 57) == {"A": True, "B": False, "C": True}
    assert pack.who_knows("a018", 57) == {"A": False, "B": True, "C": False}
    delivered = pack.observations_for("B", 44)
    assert delivered
    assert all(ob.delivery_tick <= 44 for _, ob in delivered)
    assert [ob.delivery_tick for _, ob in delivered] == sorted(ob.delivery_tick for _, ob in delivered)


def test_runtime_payloads_do_not_include_display_terms(pack):
    forbidden = pack.forbidden_runtime_terms()
    payloads = [ob.runtime_payload for event in pack.events for observations in event.observations.values() for ob in observations]
    assert all(not any(term.casefold() in payload.casefold() for term in forbidden) for payload in payloads)

from __future__ import annotations

from typing import Any, Iterable


def next_simulation_tick(
    projection: dict[str, Any], queued_wakes: Iterable[dict[str, Any]]
) -> int | None:
    """Return the next deterministic or cognitive due tick for one Crisis Run."""

    candidates = [int(wake["tick"]) for wake in queued_wakes]
    candidates.extend(
        int(message["arrival_tick"])
        for message in projection.get("messages", [])
        if message["status"] == "in_transit"
    )
    candidates.extend(
        int(operation["expected_complete_tick"])
        for operation in projection.get("operations", [])
        if operation["status"] == "IN_PROGRESS"
    )
    candidates.extend(
        int(investigation["expected_result_tick"])
        for investigation in projection.get("investigations", [])
        if investigation["status"] == "IN_PROGRESS"
    )
    candidates.extend(
        int(offer["expires_tick"])
        for offer in projection.get("offers", [])
        if offer.get("status") == "PROPOSED" and offer.get("expires_tick") is not None
    )
    candidates.extend(
        int(pressure["trigger_tick"])
        for pressure in projection.get("pressures", [])
        if pressure.get("status") == "PENDING"
    )
    candidates.extend(
        int(movement["arrival_tick"])
        for movement in projection.get("movements", [])
        if movement["status"] == "in_transit"
    )
    candidates.extend(
        int(report["expected_tick"])
        for report in projection.get("resolution_reports", [])
        if report.get("status") == "IN_TRANSIT"
    )
    return min(candidates) if candidates else None

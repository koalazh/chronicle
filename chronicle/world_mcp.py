from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .crisis import VolumeRegistry
from .db import ChronicleDB
from .world import WorldAccessError, WorldService, token_hash

mcp = FastMCP("chronicle-world")


def _world():
    token = os.environ.get("CHRONICLE_WORLD_TOKEN", "")
    if not token:
        raise WorldAccessError("Chronicle world binding is missing")
    config = load_config(environ=os.environ)
    db = ChronicleDB(config.database_path)
    binding = db.agent_binding_for_token_hash(token_hash(token))
    if binding is None:
        raise WorldAccessError("invalid Chronicle world binding")
    run = db.worldline(str(binding["worldline_id"]))
    if run is None or run["kind"] != "CRISIS":
        raise WorldAccessError("Chronicle Run is unavailable")
    pack = VolumeRegistry.load(config.volume_path).pack(str(run["crisis_id"]))
    service = WorldService(db, pack)
    return service.session_for_current_token(token)


@mcp.tool()
def communicate(
    recipient: str | dict[str, Any],
    content: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Send an in-world courier message; delivery follows simulated corridor time."""

    return _world().communicate(recipient, content, idempotency_key=idempotency_key)


@mcp.tool()
def investigate(
    question: str,
    target: str | dict[str, Any],
    idempotency_key: str,
    method: str = "",
) -> dict[str, Any]:
    """Start a delayed, source-bounded investigation of one available target."""

    return _world().investigate(
        question,
        target,
        method=method,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def manage_offer(
    action: str,
    idempotency_key: str,
    offer_id: str | dict[str, Any] = "",
    recipient: str | dict[str, Any] = "",
    terms: list[dict[str, Any]] | None = None,
    message: str = "",
    expires_after_days: int = 0,
) -> dict[str, Any]:
    """Propose, counter, accept, reject, or withdraw one structured in-world offer."""

    return _world().manage_offer(
        action,
        offer_id=offer_id,
        recipient=recipient,
        terms=terms,
        message=message,
        expires_after_days=expires_after_days,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def operate(
    operation_definition_id: str | dict[str, Any],
    targets: list[str | dict[str, Any]],
    description: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Start one currently available Crisis-defined Operation."""

    return _world().operate(
        operation_definition_id,
        targets,
        description,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def update_plan(
    objective: str,
    steps: list[str],
    idempotency_key: str,
    rationale: str = "",
    belief_updates: list[dict[str, str] | str] | None = None,
    rationale_source: str = "",
    belief_source: str = "",
    reconsider_when: list[str] | None = None,
) -> dict[str, Any]:
    """Replace the private current plan and optionally revise a few private beliefs."""

    return _world().update_plan(
        objective,
        steps,
        rationale=rationale,
        rationale_source=rationale_source,
        belief_updates=belief_updates,
        belief_source=belief_source,
        reconsider_when=reconsider_when,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def schedule_revisit(
    after_days: int,
    reason: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create a private simulated-time Revisit that will cause a future Wake."""

    return _world().schedule_revisit(
        after_days,
        reason,
        idempotency_key=idempotency_key,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

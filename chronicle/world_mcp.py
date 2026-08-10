from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .crisis import CrisisPack
from .db import ChronicleDB
from .world import WorldAccessError, WorldService

mcp = FastMCP("chronicle-world")


def _world():
    token = os.environ.get("CHRONICLE_WORLD_TOKEN", "")
    if not token:
        raise WorldAccessError("Chronicle world binding is missing")
    config = load_config(environ=os.environ)
    service = WorldService(ChronicleDB(config.database_path), CrisisPack.load(config.crisis_path))
    return service.session_for_current_token(token)


@mcp.tool()
def communicate(
    recipient: str,
    content: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Send an in-world courier message; delivery follows simulated corridor time."""

    return _world().communicate(recipient, content, idempotency_key=idempotency_key)


@mcp.tool()
def act(
    action: str,
    description: str,
    idempotency_key: str,
    target: str = "",
) -> dict[str, Any]:
    """Request hold, prepare, or move within the Actor's crisis authority."""

    return _world().act(
        action,
        description,
        target=target,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def update_plan(
    objective: str,
    steps: list[str],
    idempotency_key: str,
    rationale: str = "",
    belief_updates: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Replace the private current plan and optionally revise a few private beliefs."""

    return _world().update_plan(
        objective,
        steps,
        rationale=rationale,
        belief_updates=belief_updates,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def schedule_followup(
    after_days: int,
    purpose: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create a private simulated-time commitment that will cause a future Wake."""

    return _world().schedule_followup(
        after_days,
        purpose,
        idempotency_key=idempotency_key,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

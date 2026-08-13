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


def _volume_context(wake_id: str = ""):
    """Return the bound V5 Volume context for the current MCP process."""

    token = os.environ.get("CHRONICLE_WORLD_TOKEN", "")
    if not token:
        raise WorldAccessError("Chronicle world binding is missing")
    config = load_config(environ=os.environ)
    db = ChronicleDB(config.database_path)
    binding = db.agent_binding_for_token_hash(token_hash(token))
    if binding is None:
        raise WorldAccessError("invalid Chronicle world binding")
    worldline_id = str(binding["worldline_id"])
    run = db.worldline(worldline_id)
    if run is None or run["kind"] != "VOLUME" or run["status"] != "ACTIVE":
        raise WorldAccessError("Chronicle Volume is unavailable")
    if not wake_id:
        raise WorldAccessError("wake identity is required")
    wake = db.crisis_wake(wake_id)
    if (
        wake is None
        or str(wake["worldline_id"]) != worldline_id
        or str(wake["actor_id"]) != str(binding["role"])
        or wake["status"] not in {"RUNNING", "STAGED"}
    ):
        raise WorldAccessError("wake identity is not active")
    return config, db, binding, wake


def _volume_tool(
    tool_name: str,
    arguments: dict[str, Any],
    idempotency_key: str,
    wake_id: str = "",
) -> dict[str, Any]:
    """Stage an existing World affordance through the V5 Volume runtime."""

    from .host import ChronicleHost

    config, _db, binding, wake = _volume_context(wake_id)
    existing = [
        operation
        for operation in _db.crisis_wake_operations(wake["id"])
        if operation["status"] == "PROPOSED"
        and operation["payload"].get("moment_id")
        == wake["frozen_perspective"].get("moment_id")
    ]
    if existing and not any(
        operation["idempotency_key"] == idempotency_key for operation in existing
    ):
        raise WorldAccessError("one V5 action is already staged for this Wake")
    return ChronicleHost(config).volume_runtime.stage_actor_tool(
        str(binding["worldline_id"]),
        str(binding["role"]),
        tool_name,
        arguments,
        source="agent",
        idempotency_key=idempotency_key,
        wake_id=str(wake["id"]),
    )


def _is_volume_binding() -> bool:
    token = os.environ.get("CHRONICLE_WORLD_TOKEN", "")
    if not token:
        return False
    config = load_config(environ=os.environ)
    binding = ChronicleDB(config.database_path).agent_binding_for_token_hash(token_hash(token))
    return binding is not None and binding["binding_scope"] == "VOLUME"


@mcp.tool()
def communicate(
    recipient: str | dict[str, Any],
    content: str,
    idempotency_key: str,
    wake_id: str = "",
) -> dict[str, Any]:
    """Send an in-world courier message; delivery follows simulated corridor time."""

    if _is_volume_binding():
        return _volume_tool(
            "communicate", {"recipient": recipient, "content": content}, idempotency_key, wake_id
        )
    return _world().communicate(recipient, content, idempotency_key=idempotency_key)


@mcp.tool()
def investigate(
    question: str,
    target: str | dict[str, Any],
    idempotency_key: str,
    method: str = "",
    wake_id: str = "",
) -> dict[str, Any]:
    """Start a delayed, source-bounded investigation of one available target."""

    if _is_volume_binding():
        return _volume_tool(
            "investigate",
            {"question": question, "target": target, "method": method},
            idempotency_key,
            wake_id,
        )
    return _world().investigate(question, target, method=method, idempotency_key=idempotency_key)


@mcp.tool()
def manage_offer(
    action: str,
    idempotency_key: str,
    offer_id: str | dict[str, Any] = "",
    recipient: str | dict[str, Any] = "",
    terms: list[dict[str, Any]] | None = None,
    message: str = "",
    expires_after_days: int = 0,
    wake_id: str = "",
) -> dict[str, Any]:
    """Propose, counter, accept, reject, or withdraw one structured in-world offer."""

    if _is_volume_binding():
        return _volume_tool(
            "manage_offer",
            {
                "action": action,
                "offer_id": offer_id,
                "recipient": recipient,
                "terms": terms or [],
                "message": message,
                "expires_after_days": expires_after_days,
            },
            idempotency_key,
            wake_id,
        )
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
    wake_id: str = "",
) -> dict[str, Any]:
    """Start one currently available Crisis-defined Operation."""

    if _is_volume_binding():
        return _volume_tool(
            "operate",
            {
                "operation_definition_id": operation_definition_id,
                "targets": targets,
                "description": description,
            },
            idempotency_key,
            wake_id,
        )
    return _world().operate(
        operation_definition_id, targets, description, idempotency_key=idempotency_key
    )


@mcp.tool()
def update_plan(
    objective: str,
    steps: list[str],
    idempotency_key: str,
    rationale: str = "",
    belief_updates: list[dict[str, Any] | str] | None = None,
    rationale_source: str = "",
    belief_source: str = "",
    reconsider_when: list[str] | None = None,
    wake_id: str = "",
) -> dict[str, Any]:
    """Replace the private current plan and optionally revise a few private beliefs."""

    if _is_volume_binding():
        return _volume_tool(
            "update_plan",
            {
                "objective": objective,
                "steps": steps,
                "rationale": rationale,
                "rationale_source": rationale_source,
                "belief_updates": belief_updates or [],
                "belief_source": belief_source,
                "reconsider_when": reconsider_when or [],
            },
            idempotency_key,
            wake_id,
        )
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
    wake_id: str = "",
) -> dict[str, Any]:
    """Create a private simulated-time Revisit that will cause a future Wake."""

    if _is_volume_binding():
        return _volume_tool(
            "schedule_revisit", {"after_days": after_days, "reason": reason}, idempotency_key, wake_id
        )
    return _world().schedule_revisit(after_days, reason, idempotency_key=idempotency_key)


@mcp.tool()
def logical_intent(
    intent: dict[str, Any], idempotency_key: str, wake_id: str = ""
) -> dict[str, Any]:
    """Stage one V5 logical intent without mutating the shared world."""

    from .host import ChronicleHost

    config, db, binding, wake = _volume_context(wake_id)
    logical_key = f"{wake['id']}:{idempotency_key or 'logical-intent'}"
    existing = [
        operation
        for operation in db.crisis_wake_operations(wake["id"])
        if operation["status"] == "PROPOSED"
        and operation["payload"].get("moment_id") == wake["frozen_perspective"].get("moment_id")
    ]
    if existing:
        operation = next(
            (item for item in existing if item["idempotency_key"] == logical_key), None
        )
        if operation is None:
            raise WorldAccessError("one V5 action is already staged for this Wake")
        return {
            "status": "accepted",
            "moment_id": operation["payload"].get("moment_id", ""),
            "operation_id": operation["id"],
            "idempotent": True,
        }
    try:
        staged = ChronicleHost(config).volume_runtime.stage_intent(
            str(binding["worldline_id"]),
            str(binding["role"]),
            dict(intent),
            source="agent",
            idempotency_key=logical_key,
            wake_id=str(wake["id"]),
        )
    except Exception as exc:
        return {
            "status": "rejected",
            "code": type(exc).__name__,
            "message": str(exc)[:400],
        }
    return {
        "status": "accepted",
        "moment_id": staged["moment_id"],
        "operation_id": staged["operation"]["id"],
        "idempotent": bool(staged["idempotent"]),
    }


@mcp.tool()
def commit_deliberation(
    outcome: str,
    idempotency_key: str,
    course: dict[str, Any] | None = None,
    open_dependencies: list[dict[str, Any]] | None = None,
    belief_updates: list[dict[str, Any]] | None = None,
    world_actions: list[dict[str, Any]] | None = None,
    rationale_source: str = "",
    belief_source: str = "",
    wake_id: str = "",
) -> dict[str, Any]:
    """Stage one complete V6 HOLD/REVISE proposal for the frozen Wake."""

    from .host import ChronicleHost

    config, _db, binding, wake = _volume_context(wake_id)
    proposal_payload: dict[str, Any] = {
        "outcome": outcome,
        "course": course or {},
        "belief_updates": belief_updates or [],
        "world_actions": world_actions or [],
        "rationale_source": rationale_source,
        "belief_source": belief_source,
    }
    if open_dependencies is not None:
        proposal_payload["open_dependencies"] = open_dependencies
    try:
        staged = ChronicleHost(config).volume_runtime.stage_deliberation(
            str(binding["worldline_id"]),
            str(binding["role"]),
            proposal_payload,
            source="agent",
            idempotency_key=f"{wake['id']}:{idempotency_key or 'deliberation'}",
            wake_id=str(wake["id"]),
        )
    except Exception as exc:
        return {
            "status": "rejected",
            "code": type(exc).__name__,
            "message": str(exc)[:400],
        }
    if staged.get("rejected") or staged["operation"].get("result", {}).get("status") == "rejected":
        result = staged["operation"].get("result", {})
        return {
            "status": "rejected",
            "code": result.get("code", "deliberation_rejected"),
            "message": result.get("message", "Deliberation proposal was already rejected"),
            "moment_id": staged["moment_id"],
            "operation_id": staged["operation"]["id"],
            "idempotent": bool(staged["idempotent"]),
        }
    return {
        "status": "accepted",
        "moment_id": staged["moment_id"],
        "operation_id": staged["operation"]["id"],
        "outcome": staged["outcome"],
        "idempotent": bool(staged["idempotent"]),
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

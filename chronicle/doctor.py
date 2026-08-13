from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig
from .crisis import VolumePack
from .db import ChronicleDB, content_hash, stable_hash
from .hermes import (
    cli_version,
    lifetime_world_server_name,
    probe,
    probe_mcp_tools,
    read_profile_memory,
)

WORLD_TOOLS = (
    "communicate",
    "investigate",
    "manage_offer",
    "operate",
    "schedule_revisit",
    "update_plan",
)
SCHEMA_VERSION = "10"
PENDING_WAKE_STATUSES = {"QUEUED", "WAITING_HUMAN", "STAGED"}


def doctor(config: AppConfig) -> dict[str, Any]:
    """Inspect the current V6 Volume runtime and its live Hermes seam."""

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

    add("python", True, platform.python_version())
    volume_ok = True
    try:
        volume = VolumePack.load(config.volume_path)
        crisis_count = len(volume.packs)
        lifetime_count = len(volume.lifetimes)
        add(
            "volume_pack",
            True,
            f"{volume.volume.id}: {crisis_count} crises / {lifetime_count} lifetimes",
        )
    except Exception as exc:
        volume_ok = False
        volume = None
        add("volume_pack", False, str(exc))

    database_parent_ok = config.database_path.parent.exists() or _can_create(
        config.database_path.parent
    )
    add("database_parent", database_parent_ok, str(config.database_path.parent))
    hermes_version = cli_version(config)
    hermes_ok = not hermes_version.startswith("unavailable")
    add("hermes", hermes_ok, hermes_version)

    db = ChronicleDB(config.database_path)
    schema_version = db.get_meta("schema_version")
    add("schema_version", schema_version == SCHEMA_VERSION, f"expected={SCHEMA_VERSION}, actual={schema_version or 'missing'}")

    active = db.active_volume_worldline()
    sealed_cleanup = [
        row
        for row in db.worldlines(status="SEALED")
        if row.get("kind") == "VOLUME" and row.get("runtime_phase") == "CLEANUP_PENDING"
    ]
    add(
        "volume_cleanup",
        not sealed_cleanup,
        "no sealed Volume is waiting for cleanup"
        if not sealed_cleanup
        else f"cleanup pending: {[row['id'] for row in sealed_cleanup]}",
    )

    profiles: list[str] = []
    live_volume = active is not None and active.get("runtime_mode") == "live"
    if active is not None:
        if volume is None:
            add("active_volume_content", False, "Volume content could not be loaded")
        else:
            _check_active_volume(db, active, volume, add)
        if live_volume:
            lifetimes = db.worldline_lifetimes(str(active["id"]))
            profiles = [
                str(lifetime["profile_name"])
                for lifetime in lifetimes
                if lifetime["controller"] == "AGENT" and lifetime.get("profile_name")
            ]
            _check_live_volume_profiles(config, db, active, lifetimes, profiles, add)
        else:
            add("volume_runtime_mode", True, "fixture Volume; live Profile checks are not required")
    else:
        add("active_volume", True, "no active Volume Worldline")
        add("volume_runtime_mode", True, "no active Volume; live Profile checks are not required")

    actor_config = config.root / "hermes" / "chronicle-actor" / "config.yaml"
    config_text = actor_config.read_text(encoding="utf-8") if actor_config.exists() else ""
    add(
        "multiplex_config",
        "multiplex_profiles: true" in config_text,
        "gateway.multiplex_profiles=true in actor distribution",
    )
    banned = {"web", "browser", "terminal", "session_search", "delegate_task", "a2a"}
    present = sorted(item for item in banned if item in config_text.casefold())
    add(
        "toolset_declaration",
        not present,
        "memory only" if not present else f"forbidden terms present: {present}",
    )
    runtime_ready = config.llm_configured
    add(
        "llm_config",
        runtime_ready,
        "base URL, key and model configured" if runtime_ready else "setup required",
    )

    if live_volume and hermes_ok and profiles:
        api_probe = probe(config, profiles)
        add("shared_api_listener", api_probe.health, "health reachable" if api_probe.health else "not reachable")
        add(
            "gateway_api_probe",
            not api_probe.errors,
            "root and Lifetime Profile probes passed"
            if not api_probe.errors
            else "; ".join(api_probe.errors),
        )
        routing_ok = all(api_probe.profile_status.get(profile) == 200 for profile in profiles)
        add("profile_routing", routing_ok, "Profile routes reachable" if routing_ok else "Profile routes not verified")
        toolset_ok = all(api_probe.profile_toolsets.get(profile) == ("memory",) for profile in profiles)
        add(
            "toolset_restriction",
            toolset_ok,
            "memory only"
            if toolset_ok
            else str({profile: list(api_probe.profile_toolsets.get(profile, ())) for profile in profiles}),
        )
        add(
            "profile_key_isolation",
            api_probe.valid_profile_status == 200 and api_probe.cross_profile_status in {401, 403},
            f"valid={api_probe.valid_profile_status}, cross_profile={api_probe.cross_profile_status}",
        )
        _check_live_mcp(config, db, active, db.worldline_lifetimes(str(active["id"])), add)
    else:
        add("shared_api_listener", True, "not required until a live Volume is active", required=False)
        add("profile_routing", True, "not required until a live Volume is active", required=False)
        add("toolset_restriction", True, "not required until a live Volume is active", required=False)
        add("profile_key_isolation", True, "not required until a live Volume is active", required=False)
        add("world_mcp_configuration", True, "not required until a live Volume is active", required=False)
        add("world_mcp_discovery", True, "not required until a live Volume is active", required=False)
        add("world_mcp_execution", True, "not required until a live Volume is active", required=False)

    add(
        "memory_evolution",
        "curator" not in config_text.casefold(),
        "automatic curator path is not in actor distribution",
    )
    ready = volume_ok and all(item["ok"] for item in checks if item["required"])
    return {
        "status": "READY" if ready else "NOT_READY",
        "checks": checks,
        "config": {
            "database": str(config.database_path),
            "hermes_home": str(config.hermes_home),
            "llm_configured": config.llm_configured,
            "profiles": profiles,
            "active_volume": str(active["id"]) if active else None,
        },
        "volume_ok": volume_ok,
    }


def _check_active_volume(
    db: ChronicleDB,
    active: dict[str, Any],
    volume: VolumePack,
    add: Any,
) -> None:
    worldline_id = str(active["id"])
    lifetimes = db.worldline_lifetimes(worldline_id)
    expected_lifetimes = set(volume.lifetimes)
    actual_lifetimes = {str(item["seat"]) for item in lifetimes}
    add(
        "volume_lifetimes",
        actual_lifetimes == expected_lifetimes,
        f"expected={sorted(expected_lifetimes)}, actual={sorted(actual_lifetimes)}",
    )

    events = db.worldline_events(worldline_id)
    snapshot = db.worldline_snapshot(worldline_id, int(active["current_tick"]))
    last_sequence = int(events[-1]["sequence"]) if events else 0
    snapshot_ok = (
        snapshot is not None
        and int(snapshot["ledger_cursor"]) == last_sequence
        and snapshot["projection_hash"] == stable_hash(snapshot["projection"])
        and int(snapshot["tick"]) == int(active["current_tick"])
    )
    add(
        "ledger_snapshot_integrity",
        snapshot_ok,
        "latest snapshot matches current tick and ledger cursor"
        if snapshot_ok
        else f"event_cursor={last_sequence}, snapshot={snapshot}",
    )

    memory_ok = all(
        str(lifetime["memory_hash"]) == content_hash(str(lifetime["memory_text"]))
        for lifetime in lifetimes
    )
    add(
        "memory_lineage",
        memory_ok,
        "each Lifetime Memory hash matches its persisted content"
        if memory_ok
        else "a Lifetime Memory hash diverges from its persisted content",
    )

    wakes = db.subject_wakes(worldline_id)
    pending = snapshot["projection"].get("pending_moment") if snapshot else None
    pending_errors: list[str] = []
    if pending is not None:
        if pending.get("phase") != "FROZEN":
            pending_errors.append("pending moment is not frozen")
        for wake_id in pending.get("wake_ids", []):
            wake = db.crisis_wake(str(wake_id))
            if wake is None or wake["status"] not in PENDING_WAKE_STATUSES:
                pending_errors.append(f"invalid pending Wake {wake_id}")
            else:
                operations = db.crisis_wake_operations(str(wake_id))
                if any(operation["payload"].get("moment_id") != pending["id"] for operation in operations):
                    pending_errors.append(f"Wake operation belongs to another moment: {wake_id}")
                if wake["status"] == "STAGED" and len(operations) != 1:
                    pending_errors.append(f"staged Wake has an invalid operation count: {wake_id}")
                if wake["status"] != "STAGED" and operations:
                    pending_errors.append(f"unstaged Wake has a persisted operation: {wake_id}")
    for wake in wakes:
        if wake["status"] == "RUNNING":
            pending_errors.append(f"Wake is still running: {wake['id']}")
        if wake["status"] == "STAGED" and pending is None:
            pending_errors.append(f"staged Wake has no pending moment: {wake['id']}")
    add(
        "pending_moment_integrity",
        not pending_errors,
        "no orphaned or unrecoverable Pending Logical Moment"
        if not pending_errors
        else "; ".join(pending_errors),
    )
    add(
        "volume_runtime_phase",
        active.get("runtime_phase") in {"READY", "RECONCILING", "BOOTSTRAPPING"},
        f"phase={active.get('runtime_phase') or 'missing'}",
    )


def _check_live_volume_profiles(
    config: AppConfig,
    db: ChronicleDB,
    active: dict[str, Any],
    lifetimes: list[dict[str, Any]],
    profiles: list[str],
    add: Any,
) -> None:
    worldline_id = str(active["id"])
    agent_lifetimes = {
        str(lifetime["seat"]): str(lifetime["profile_name"])
        for lifetime in lifetimes
        if lifetime["controller"] == "AGENT"
    }
    bindings = [
        binding
        for binding in db.agent_bindings(worldline_id)
        if binding["status"] == "ACTIVE"
    ]
    binding_profiles = {str(binding["role"]): str(binding["profile_identity"]) for binding in bindings}
    token_hashes = [str(binding["token_hash"]) for binding in bindings]
    bindings_ok = (
        binding_profiles == agent_lifetimes
        and all(token_hashes)
        and len(token_hashes) == len(set(token_hashes))
    )
    add(
        "agent_binding_integrity",
        bindings_ok,
        f"agent_lifetimes={len(agent_lifetimes)}, active_bindings={len(bindings)}, unique_tokens={len(set(token_hashes))}",
    )

    identity_errors: list[str] = []
    memory_errors: list[str] = []
    bindings_by_actor = {str(binding["role"]): binding for binding in bindings}
    for lifetime in lifetimes:
        if lifetime["controller"] != "AGENT":
            continue
        actor_id = str(lifetime["seat"])
        profile = str(lifetime["profile_name"])
        marker_path = config.hermes_home / "profiles" / profile / "chronicle-genesis.json"
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            binding = bindings_by_actor[actor_id]
            marker_ok = (
                marker.get("profile_scope") == "LIFETIME"
                and marker.get("profile") == profile
                and marker.get("worldline_id") == worldline_id
                and marker.get("volume_id") == active.get("volume_id")
                and marker.get("lifetime_id") == actor_id
                and marker.get("genesis_hash") == lifetime["genesis_hash"]
                and marker.get("runtime_epoch") == active["runtime_epoch"]
                and marker.get("ownership_marker") == binding["ownership_marker"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            marker_ok = False
        if not marker_ok:
            identity_errors.append(actor_id)
        try:
            native_hash = read_profile_memory(config, profile)[1]
        except (OSError, RuntimeError):
            native_hash = ""
        if native_hash != str(lifetime["memory_hash"]):
            memory_errors.append(actor_id)
    add(
        "profile_identity_integrity",
        not identity_errors,
        "Profile markers bind Volume, Lifetime, genesis, ownership and runtime epoch"
        if not identity_errors
        else f"invalid Lifetime Profile identity markers: {identity_errors}",
    )
    add(
        "native_memory_integrity",
        not memory_errors,
        "Hermes native Memory hashes match Lifetime state"
        if not memory_errors
        else f"Hermes native Memory diverges for: {memory_errors}",
    )
    profile_dirs = [config.hermes_home / "profiles" / profile for profile in profiles]
    add(
        "chronicle_profiles",
        all(path.is_dir() and (path / "chronicle-genesis.json").is_file() for path in profile_dirs),
        ", ".join(profile for profile in profiles if (config.hermes_home / "profiles" / profile).exists())
        or "not materialized",
    )


def _check_live_mcp(
    config: AppConfig,
    db: ChronicleDB,
    active: dict[str, Any],
    lifetimes: list[dict[str, Any]],
    add: Any,
) -> None:
    worldline_id = str(active["id"])
    agent_lifetimes = [lifetime for lifetime in lifetimes if lifetime["controller"] == "AGENT"]
    profiles = [str(lifetime["profile_name"]) for lifetime in agent_lifetimes]
    configured_servers: dict[str, str] = {}
    configuration_ok = True
    for lifetime in agent_lifetimes:
        profile = str(lifetime["profile_name"])
        lifetime_id = str(lifetime["seat"])
        profile_config = config.hermes_home / "profiles" / profile / "config.yaml"
        try:
            values = yaml.safe_load(profile_config.read_text(encoding="utf-8")) or {}
            servers = values.get("mcp_servers", {})
            allowlist = values.get("platform_toolsets", {}).get("api_server", [])
            expected_server = lifetime_world_server_name(worldline_id, lifetime_id)
            if allowlist != ["memory", expected_server] or set(servers) != {expected_server}:
                raise ValueError("expected memory plus one identity-specific Volume World MCP")
            configured_servers[profile] = expected_server
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            configuration_ok = False
            configured_servers[profile] = f"invalid: {exc}"
    add(
        "world_mcp_configuration",
        configuration_ok and len(set(configured_servers.values())) == len(profiles),
        str(configured_servers),
    )
    discovered = {
        profile: probe_mcp_tools(config, server)
        for profile, server in configured_servers.items()
        if not server.startswith("invalid:")
    }
    add(
        "world_mcp_discovery",
        len(discovered) == len(profiles)
        and all(tools == WORLD_TOOLS for tools in discovered.values()),
        "Volume MCP tools: " + str({profile: list(tools) for profile, tools in discovered.items()}),
    )
    completed_wakes = [
        wake
        for wake in db.crisis_wakes(worldline_id, status="COMPLETED")
        if wake["actor_id"] in {str(lifetime["seat"]) for lifetime in agent_lifetimes}
    ]
    add(
        "world_mcp_execution",
        True,
        "deferred until a live Lifetime Wake is completed"
        if not completed_wakes
        else "completed live Lifetime Wakes require per-Wake operation inspection",
        required=False,
    )


def _can_create(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False

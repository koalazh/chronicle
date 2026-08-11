from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig
from .crisis import CrisisPack
from .db import ChronicleDB, stable_hash
from .hermes import PROFILE_NAMES, cli_version, probe, probe_mcp_tools, read_profile_memory
from .scenario import ScenarioPack

WORLD_TOOLS = ("communicate", "investigate", "operate", "schedule_revisit", "update_plan")


def doctor(config: AppConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

    add("python", True, platform.python_version())
    scenario_ok = True
    try:
        pack = ScenarioPack.load(config.scenario_path)
        add("source_pack", True, f"{len(pack.sources)} sources / {len(pack.assertions)} assertions")
        add("scenario", True, f"{len(pack.events)} canon events / fork {pack.fork.id}")
    except Exception as exc:
        scenario_ok = False
        add("scenario", False, str(exc))
    try:
        crisis = CrisisPack.load(config.crisis_path)
        add(
            "crisis_pack",
            True,
            f"{len(crisis.crisis.actors)} actors / {len(crisis.sources)} sources / "
            f"{crisis.crisis.simulation_boundary.maximum_tick} simulated days",
        )
    except Exception as exc:
        add("crisis_pack", False, str(exc))
    add("database_parent", config.database_path.parent.exists() or _can_create(config.database_path.parent), str(config.database_path.parent))
    hermes_version = cli_version(config)
    hermes_ok = not hermes_version.startswith("unavailable")
    add("hermes", hermes_ok, hermes_version)
    db = ChronicleDB(config.database_path)
    schema_version = db.get_meta("schema_version")
    add("schema_version", schema_version == "9", f"expected=9, actual={schema_version or 'missing'}")
    active_run = db.active_run()
    live_v3 = active_run is not None and active_run["runtime_mode"] == "live"
    if active_run is not None:
        run_id = str(active_run["id"])
        lifetimes = db.worldline_lifetimes(run_id)
        wakes = db.crisis_wakes(run_id)
        events = db.worldline_events(run_id)
        snapshot = db.worldline_snapshot(run_id)
        maximum_tick = int(active_run["simulation_boundary"]["maximum_tick"])
        controllers = active_run["controller_map"]
        unfinished_statuses = sorted(
            {wake["status"] for wake in wakes if wake["status"] in {"RUNNING", "STAGED", "FAILED"}}
        )
        completed_sessions = [
            str(wake["hermes_session_id"])
            for wake in wakes
            if wake["status"] == "COMPLETED" and wake["hermes_session_id"]
        ]
        agent_sessions_present = all(
            bool(wake["hermes_session_id"])
            for wake in wakes
            if wake["status"] == "COMPLETED"
            and controllers.get(str(wake["actor_id"])) == "AGENT"
        )
        expected_revisit_wakes: dict[tuple[str, int, str], str] = {}
        for lifetime in lifetimes:
            for revisit in lifetime["revisits"]:
                expected_revisit_wakes[
                    (
                        str(lifetime["seat"]),
                        int(revisit["due_tick"]),
                        str(revisit.get("event_id", "")),
                    )
                ] = str(revisit["status"])
        actual_revisit_wakes: dict[tuple[str, int, str], list[str]] = {}
        for wake in wakes:
            if wake["wake_type"] != "REVISIT_DUE":
                continue
            key = (
                str(wake["actor_id"]),
                int(wake["tick"]),
                str(wake["trigger_event_id"]),
            )
            actual_revisit_wakes.setdefault(key, []).append(str(wake["status"]))
        revisit_wakes_ok = (
            set(expected_revisit_wakes) == set(actual_revisit_wakes)
            and all(len(statuses) == 1 for statuses in actual_revisit_wakes.values())
            and all(
                actual_revisit_wakes[key][0]
                == ("QUEUED" if revisit_status == "PENDING" else "COMPLETED")
                for key, revisit_status in expected_revisit_wakes.items()
            )
        )
        scheduler_ok = (
            not unfinished_statuses
            and all(
                int(wake["tick"]) < maximum_tick
                and (
                    wake["status"] != "COMPLETED"
                    or controllers.get(str(wake["actor_id"])) != "AGENT"
                    or bool(wake["hermes_session_id"])
                )
                for wake in wakes
            )
            and agent_sessions_present
            and len(completed_sessions) == len(set(completed_sessions))
            and revisit_wakes_ok
        )
        add(
            "wake_scheduler_integrity",
            scheduler_ok,
            f"wakes={len(wakes)}, completed_sessions={len(completed_sessions)}, "
            f"revisits={len(expected_revisit_wakes)}, "
            f"revisit_wakes={sum(len(items) for items in actual_revisit_wakes.values())}, "
            f"unfinished={unfinished_statuses or 'none'}",
        )
        last_sequence = int(events[-1]["sequence"]) if events else 0
        snapshot_ok = (
            snapshot is not None
            and int(snapshot["ledger_cursor"]) == last_sequence
            and snapshot["projection_hash"] == stable_hash(snapshot["projection"])
            and int(snapshot["tick"]) == int(active_run["current_tick"])
        )
        add(
            "ledger_snapshot_integrity",
            snapshot_ok,
            "latest snapshot matches current tick and ledger cursor"
            if snapshot_ok
            else f"event_cursor={last_sequence}, snapshot={snapshot}",
        )
        memory_lineage_ok = all(
            bool(versions := db.memory_versions(f"{run_id}:{lifetime['seat']}"))
            and versions[0]["mutation_kind"] == "genesis"
            and versions[-1]["memory_hash"] == lifetime["memory_hash"]
            for lifetime in lifetimes
        )
        add(
            "memory_lineage",
            memory_lineage_ok,
            "each Life State matches its append-only Memory lineage"
            if memory_lineage_ok
            else "a Life State is missing or diverges from its Memory lineage",
        )
    if live_v3:
        run_id = str(active_run["id"])
        lifetimes = db.worldline_lifetimes(run_id)
        profiles = [
            str(lifetime["profile_name"])
            for lifetime in lifetimes
            if lifetime["controller"] == "AGENT"
        ]
        agent_lifetimes = {
            str(lifetime["seat"]): str(lifetime["profile_name"])
            for lifetime in lifetimes
            if lifetime["controller"] == "AGENT"
        }
        bindings = [
            binding
            for binding in db.agent_bindings(run_id)
            if binding["status"] == "ACTIVE"
        ]
        binding_profiles = {
            str(binding["role"]): str(binding["profile_identity"])
            for binding in bindings
        }
        token_hashes = [str(binding["token_hash"]) for binding in bindings]
        bindings_ok = (
            binding_profiles == agent_lifetimes
            and all(token_hashes)
            and len(token_hashes) == len(set(token_hashes))
        )
        add(
            "agent_binding_integrity",
            bindings_ok,
            f"agent_lifetimes={len(agent_lifetimes)}, active_bindings={len(bindings)}, "
            f"unique_tokens={len(set(token_hashes))}",
        )
        bindings_by_actor = {str(binding["role"]): binding for binding in bindings}
        identity_errors: list[str] = []
        for lifetime in lifetimes:
            if lifetime["controller"] != "AGENT":
                continue
            actor_id = str(lifetime["seat"])
            profile = str(lifetime["profile_name"])
            marker_path = config.hermes_home / "profiles" / profile / "chronicle-genesis.json"
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                genesis = db.memory_versions(f"{run_id}:{actor_id}")[0]
                initial_memory = marker["initial_memory_snapshot"]
                binding = bindings_by_actor[actor_id]
                marker_ok = (
                    marker["profile"] == profile
                    and marker["actor_id"] == actor_id
                    and marker["crisis_id"] == active_run["crisis_id"]
                    and marker["run_id"] == run_id
                    and marker["worldline_id"] == run_id
                    and marker["genesis_hash"] == lifetime["genesis_hash"]
                    and marker["runtime_epoch"] == active_run["runtime_epoch"]
                    and marker["ownership_marker"] == binding["ownership_marker"]
                    and initial_memory["memory_text"] == genesis["memory_text"]
                    and initial_memory["memory_hash"] == genesis["memory_hash"]
                )
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                marker_ok = False
            if not marker_ok:
                identity_errors.append(actor_id)
        add(
            "profile_identity_integrity",
            not identity_errors,
            "Profile markers bind crisis, Run, Actor, genesis, initial Memory and runtime epoch"
            if not identity_errors
            else f"invalid Profile identity markers: {identity_errors}",
        )
        native_memory = {
            str(lifetime["seat"]): read_profile_memory(
                config, str(lifetime["profile_name"])
            )[1]
            for lifetime in lifetimes
            if lifetime["controller"] == "AGENT" and lifetime["profile_name"]
        }
        lifetime_memory = {
            str(lifetime["seat"]): str(lifetime["memory_hash"])
            for lifetime in lifetimes
            if lifetime["controller"] == "AGENT"
        }
        memory_ok = native_memory == lifetime_memory
        add(
            "native_memory_integrity",
            memory_ok,
            "Hermes native Memory hashes match Life State"
            if memory_ok
            else "Hermes native Memory diverges from Life State",
        )
    else:
        profiles = list(PROFILE_NAMES.values())
    profile_dirs = [config.hermes_home / "profiles" / profile for profile in profiles]
    profiles_ok = all(
        path.is_dir() and (path / "chronicle-genesis.json").is_file() for path in profile_dirs
    )
    add(
        "chronicle_profiles",
        profiles_ok,
        ", ".join(str(path.name) for path in profile_dirs if path.exists()) or "not bootstrapped",
    )
    actor_config = config.root / "hermes" / "chronicle-actor" / "config.yaml"
    config_text = actor_config.read_text(encoding="utf-8") if actor_config.exists() else ""
    add("multiplex_config", "multiplex_profiles: true" in config_text, "gateway.multiplex_profiles=true in actor distribution")
    banned = {"web", "browser", "terminal", "session_search", "delegate_task", "a2a"}
    present = sorted(item for item in banned if item in config_text.casefold())
    add("toolset_declaration", not present, "memory only" if not present else f"forbidden terms present: {present}")
    runtime_ready = config.llm_configured
    add("llm_config", runtime_ready, "base URL, key and model configured" if runtime_ready else "setup required")
    api_probe = probe(config, profiles) if hermes_ok and profiles_ok else None
    if api_probe:
        add("shared_api_listener", api_probe.health, "health reachable" if api_probe.health else "not reachable")
        add(
            "gateway_api_probe",
            not api_probe.errors,
            "root and Profile probes passed"
            if not api_probe.errors
            else "; ".join(api_probe.errors),
        )
        profile_list = profiles
        routing_ok = all(api_probe.profile_status.get(profile) == 200 for profile in profile_list) and all(
            profile in api_probe.profiles for profile in profile_list
        )
        add("profile_routing", routing_ok, "profile routes reachable" if routing_ok else "profile routes not verified")
        toolset_ok = all(api_probe.profile_toolsets.get(profile) == ("memory",) for profile in profile_list)
        toolset_detail = "memory only" if toolset_ok else str(
            {profile: list(api_probe.profile_toolsets.get(profile, ())) for profile in profile_list}
        )
        add("toolset_restriction", toolset_ok, toolset_detail)
        add(
            "profile_key_isolation",
            api_probe.valid_profile_status == 200 and api_probe.cross_profile_status in {401, 403},
            f"valid={api_probe.valid_profile_status}, cross_profile={api_probe.cross_profile_status}",
        )
        if live_v3:
            configured_servers: dict[str, str] = {}
            configuration_ok = True
            for profile in profile_list:
                profile_config = config.hermes_home / "profiles" / profile / "config.yaml"
                try:
                    values = yaml.safe_load(profile_config.read_text(encoding="utf-8")) or {}
                    servers = values.get("mcp_servers", {})
                    allowlist = values.get("platform_toolsets", {}).get("api_server", [])
                    if len(servers) != 1:
                        raise ValueError("expected one identity-specific MCP server")
                    server_name = next(iter(servers))
                    if allowlist != ["memory", server_name]:
                        raise ValueError("API Server allowlist is not memory plus its World MCP")
                    configured_servers[profile] = server_name
                except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
                    configuration_ok = False
                    configured_servers[profile] = f"invalid: {exc}"
            add(
                "world_mcp_configuration",
                configuration_ok and len(set(configured_servers.values())) == len(profile_list),
                str(configured_servers),
            )
            discovered = {
                profile: probe_mcp_tools(config, server)
                for profile, server in configured_servers.items()
                if not server.startswith("invalid:")
            }
            add(
                "world_mcp_discovery",
                len(discovered) == len(profile_list)
                and all(tools == WORLD_TOOLS for tools in discovered.values()),
                "standalone MCP server: "
                + str({profile: list(tools) for profile, tools in discovered.items()})
                + "; this does not prove Gateway Profile execution",
            )
            completed_orients = [
                wake
                for wake in db.crisis_wakes(run_id, status="COMPLETED")
                if wake["wake_type"] == "ORIENT"
                and controllers.get(str(wake["actor_id"])) == "AGENT"
            ]
            world_execution_ok = not completed_orients or all(
                any(
                    operation["tool_name"] in WORLD_TOOLS
                    and operation["status"] == "COMMITTED"
                    for operation in db.crisis_wake_operations(wake["id"])
                )
                for wake in completed_orients
            )
            add(
                "world_mcp_execution",
                world_execution_ok,
                "deferred until the first live Agent ORIENT"
                if not completed_orients
                else "completed live ORIENTs have committed World operations"
                if world_execution_ok
                else "a completed live ORIENT has no committed World operation",
                required=bool(completed_orients),
            )
    else:
        add("shared_api_listener", False, "probe skipped until Chronicle profiles are bootstrapped")
        add("profile_routing", False, "probe skipped until Chronicle profiles are bootstrapped")
        add("toolset_restriction", False, "actual Hermes toolset probe unavailable")
        add("profile_key_isolation", False, "probe skipped until Chronicle profiles are bootstrapped")
        if live_v3:
            add("world_mcp_configuration", False, "probe skipped until V3 Profiles are available")
            add("world_mcp_discovery", False, "live MCP discovery unavailable")
            add("world_mcp_execution", False, "live Gateway execution evidence unavailable")
    add("memory_evolution", "curator" not in config_text.casefold(), "automatic curator path is not in actor distribution")
    ready = all(item["ok"] for item in checks if item["required"])
    return {
        "status": "READY" if ready else "NOT_READY",
        "checks": checks,
        "config": {
            "database": str(config.database_path),
            "hermes_home": str(config.hermes_home),
            "llm_configured": config.llm_configured,
            "profiles": profiles,
        },
        "scenario_ok": scenario_ok,
    }


def _can_create(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .config import AppConfig
from .hermes import PROFILE_NAMES, HermesClient, cli_version, probe, profile_api_key
from .scenario import ScenarioPack


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
    add("database_parent", config.database_path.parent.exists() or _can_create(config.database_path.parent), str(config.database_path.parent))
    hermes_version = cli_version(config)
    hermes_ok = not hermes_version.startswith("unavailable")
    add("hermes", hermes_ok, hermes_version)
    profile_dirs = [config.hermes_home / "profiles" / profile for profile in PROFILE_NAMES.values()]
    profiles_ok = all(
        path.is_dir() and (path / "chronicle-genesis.json").is_file() for path in profile_dirs
    )
    add("chronicle_profiles", profiles_ok, ", ".join(str(path.name) for path in profile_dirs if path.exists()) or "not bootstrapped")
    actor_config = config.root / "hermes" / "chronicle-actor" / "config.yaml"
    config_text = actor_config.read_text(encoding="utf-8") if actor_config.exists() else ""
    add("multiplex_config", "multiplex_profiles: true" in config_text, "gateway.multiplex_profiles=true in actor distribution")
    banned = {"web", "browser", "terminal", "session_search", "delegate_task", "a2a"}
    present = sorted(item for item in banned if item in config_text.casefold())
    add("toolset_restriction", not present, "memory only" if not present else f"forbidden terms present: {present}")
    runtime_ready = config.llm_configured
    add("llm_config", runtime_ready, "base URL, key and model configured" if runtime_ready else "setup required")
    api_probe = probe(config, list(PROFILE_NAMES.values())) if hermes_ok and profiles_ok else None
    if api_probe:
        add("shared_api_listener", api_probe.health, "health reachable" if api_probe.health else "not reachable")
        add("profile_routing", api_probe.multiplex, "profile routes reachable" if api_probe.multiplex else "profile routes not verified", required=False)
        profile_list = list(PROFILE_NAMES.values())
        client = HermesClient(config)
        valid_status, _ = client.get_json(
            "/v1/models", profile=profile_list[1], key=profile_api_key(config, profile_list[1])
        )
        cross_status, _ = client.get_json(
            "/v1/models", profile=profile_list[1], key=profile_api_key(config, profile_list[0])
        )
        add(
            "profile_key_isolation",
            valid_status == 200 and cross_status in {401, 403},
            f"valid={valid_status}, cross_profile={cross_status}",
        )
    else:
        add("shared_api_listener", False, "probe skipped until Chronicle profiles are bootstrapped")
        add("profile_key_isolation", False, "probe skipped until Chronicle profiles are bootstrapped")
    add("memory_evolution", "curator" not in config_text.casefold(), "automatic curator path is not in actor distribution")
    ready = all(item["ok"] for item in checks if item["required"])
    return {
        "status": "READY" if ready else "NOT_READY",
        "checks": checks,
        "config": {
            "database": str(config.database_path),
            "hermes_home": str(config.hermes_home),
            "llm_configured": config.llm_configured,
        },
        "scenario_ok": scenario_ok,
    }


def _can_create(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False

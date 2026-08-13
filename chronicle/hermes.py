from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from .config import AppConfig, generate_secret

ACTOR_DISTRIBUTION = "hermes/chronicle-actor"


def _python_executable() -> str:
    """Use one stable interpreter identity across Profile write/reconcile seams."""

    executable = Path(sys.executable)
    environment_python = executable.parent / "python"
    if executable.parent.name == "bin" and environment_python.exists():
        return str(environment_python.absolute())
    return str(executable.absolute())


@dataclass(frozen=True)
class HermesProbeResult:
    available: bool
    version: str
    cli_output: str
    health: bool
    capabilities: dict[str, Any]
    models: dict[str, Any]
    profiles: list[str]
    multiplex: bool
    profile_status: dict[str, int]
    profile_toolsets: dict[str, tuple[str, ...]]
    valid_profile_status: int
    cross_profile_status: int
    errors: tuple[str, ...] = ()

    def ready_for(self, profile: str) -> bool:
        return (
            self.health
            and not self.errors
            and profile in self.profiles
            and self.profile_status.get(profile) == 200
            and self.profile_toolsets.get(profile) == ("memory",)
        )

    def ready_for_all(self, profiles: list[str] | None = None) -> bool:
        required = profiles or list(self.profile_status)
        return (
            bool(required)
            and not self.errors
            and all(self.ready_for(profile) for profile in required)
            and self.valid_profile_status == 200
            and self.cross_profile_status in {401, 403}
        )

    def summary(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "version": self.version,
            "health": self.health,
            "profiles": self.profiles,
            "multiplex": self.multiplex,
            "profile_status": self.profile_status,
            "profile_toolsets": {profile: list(names) for profile, names in self.profile_toolsets.items()},
            "valid_profile_status": self.valid_profile_status,
            "cross_profile_status": self.cross_profile_status,
            "capabilities": sorted(self.capabilities.keys()),
            "model_count": len(self.models.get("data", [])) if isinstance(self.models, dict) else 0,
            "errors": list(self.errors),
        }


class HermesRuntimeError(RuntimeError):
    """A safe, user-facing failure at the live Hermes boundary."""


class HermesClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def _url(self, profile: str | None, path: str) -> str:
        prefix = ""
        if profile:
            prefix = f"/p/{profile}"
        return f"{self.config.hermes_base_url}{prefix}{path}"

    def _headers(self, key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def get_json(self, path: str, *, profile: str | None = None, key: str = "") -> tuple[int, dict[str, Any]]:
        headers = self._headers(key) if key else {}
        try:
            response = httpx.get(self._url(profile, path), headers=headers, timeout=8, trust_env=False)
            data = response.json() if response.content else {}
            return response.status_code, data if isinstance(data, dict) else {"data": data}
        except (httpx.HTTPError, ValueError) as exc:
            return 0, {"error": str(exc)}

    def create_fresh_session(self, profile: str, key: str, wake_id: str) -> str | None:
        session_id = f"chronicle-{wake_id}"
        title = f"Chronicle {session_id}"
        if len(title) > 100:
            title = f"Chronicle {session_id[:72]}-{hashlib.sha256(session_id.encode()).hexdigest()[:16]}"
        for attempt in range(3):
            try:
                response = httpx.post(
                    self._url(profile, "/api/sessions"),
                    headers=self._headers(key),
                    json={"id": session_id, "title": title},
                    timeout=15,
                    trust_env=False,
                )
            except httpx.HTTPError:
                if attempt == 2:
                    return None
            else:
                if response.status_code in {200, 201, 409}:
                    return session_id
                if not 500 <= response.status_code < 600:
                    return None
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
        return None

    def chat(
        self,
        profile: str,
        key: str,
        messages: list[dict[str, str]],
        session_id: str,
        memory_key: str,
    ) -> tuple[str, str]:
        headers = self._headers(key)
        headers["X-Hermes-Session-Id"] = session_id
        headers["X-Hermes-Session-Key"] = memory_key
        payload: dict[str, Any] = {
            "model": profile,
            "messages": messages,
            "temperature": 0,
            "stream": False,
        }
        if self.config.llm_reasoning_effort:
            payload["reasoning_effort"] = self.config.llm_reasoning_effort
        endpoint = "/v1/responses" if self.config.llm_api_mode == "responses" else "/v1/chat/completions"
        if endpoint.endswith("responses"):
            payload = {
                "model": profile,
                "input": [{"role": item["role"], "content": item["content"]} for item in messages],
                "store": False,
            }
            if self.config.llm_reasoning_effort:
                payload["reasoning_effort"] = self.config.llm_reasoning_effort
        response = httpx.post(
            self._url(profile, endpoint),
            headers=headers,
            json=payload,
            timeout=self.config.llm_timeout,
            trust_env=False,
        )
        response.raise_for_status()
        body = response.json()
        if endpoint.endswith("responses"):
            text = ""
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        text += content.get("text", "")
            return text, response.headers.get("X-Hermes-Session-Id", session_id)
        choices = body.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        return _content_to_text(content), response.headers.get("X-Hermes-Session-Id", session_id)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def enabled_toolset_names(payload: dict[str, Any]) -> tuple[str, ...]:
    entries: Any = payload.get("data", payload.get("toolsets", []))
    if isinstance(entries, dict):
        entries = entries.get("data", entries.get("toolsets", []))
    if not isinstance(entries, list):
        return ()
    names: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            names.add(entry)
        elif isinstance(entry, dict) and entry.get("enabled", True) is not False:
            name = entry.get("name") or entry.get("id")
            if name:
                names.add(str(name))
    return tuple(sorted(names))


def _run_cli(config: AppConfig, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HERMES_HOME"] = str(config.hermes_home)
    return subprocess.run(
        [config.hermes_bin, *args],
        cwd=config.root,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def cli_version(config: AppConfig) -> str:
    try:
        result = _run_cli(config, ["--version"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr) else "unknown"


def probe_mcp_tools(config: AppConfig, server_name: str) -> tuple[str, ...]:
    """Discover one configured MCP server through Hermes' own live probe."""

    try:
        result = _run_cli(config, ["mcp", "test", server_name], timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout or result.stderr)
    if "Connected" not in output:
        return ()
    tools: list[str] = []
    for line in output.splitlines():
        match = re.match(r"^\s{4}([A-Za-z_][A-Za-z0-9_.-]*)\s{2,}", line)
        if match:
            tools.append(match.group(1))
    return tuple(sorted(set(tools)))


def profile_api_key(config: AppConfig, profile: str) -> str:
    key_name = f"CHRONICLE_{profile.upper().replace('-', '_')}_API_SERVER_KEY"
    runtime_values = _read_env_file(config.runtime_env_path)
    if runtime_values.get(key_name):
        return runtime_values[key_name]
    return _read_env_file(config.hermes_home / "profiles" / profile / ".env").get("API_SERVER_KEY", "")


def probe(config: AppConfig, profiles: list[str] | None = None) -> HermesProbeResult:
    profiles = profiles or []
    version = cli_version(config)
    available = not version.startswith("unavailable")
    client = HermesClient(config)
    health_status, health = client.get_json("/health")
    gateway_key = _read_env_file(config.hermes_home / ".env").get("API_SERVER_KEY", "")
    capabilities_status, capabilities = client.get_json("/v1/capabilities", key=gateway_key)
    models_status, models = client.get_json("/v1/models", key=gateway_key)
    errors: list[str] = []
    if health_status != 200:
        errors.append(f"shared Hermes health unavailable ({health_status})")
    if capabilities_status != 200:
        errors.append(f"Hermes capabilities unavailable ({capabilities_status})")
    if models_status != 200:
        errors.append(f"Hermes gateway models unavailable ({models_status})")
    multiplex = bool(capabilities.get("multiplex_profiles") or capabilities.get("features", {}).get("multiplex_profiles"))
    served: list[str] = []
    profile_status: dict[str, int] = {}
    profile_toolsets: dict[str, tuple[str, ...]] = {}
    for profile in profiles:
        profile_key = profile_api_key(config, profile)
        profile_model_status, profile_models = client.get_json(
            "/v1/models", profile=profile, key=profile_key
        )
        profile_status[profile] = profile_model_status
        if profile_model_status == 200 and isinstance(profile_models.get("data"), list) and profile_models["data"]:
            served.append(profile)
        else:
            errors.append(f"profile route unavailable for {profile} ({profile_model_status})")
        toolset_status, toolset_payload = client.get_json("/v1/toolsets", profile=profile, key=profile_key)
        profile_toolsets[profile] = enabled_toolset_names(toolset_payload) if toolset_status == 200 else ()
        if toolset_status != 200:
            errors.append(f"profile toolsets unavailable for {profile} ({toolset_status})")
    multiplex = multiplex or len(set(served)) > 1
    valid_profile_status = 0
    cross_profile_status = 0
    if len(profiles) >= 2:
        valid_profile = profiles[1]
        cross_profile = profiles[0]
        valid_profile_status, _ = client.get_json(
            "/v1/models", profile=valid_profile, key=profile_api_key(config, valid_profile)
        )
        cross_profile_status, _ = client.get_json(
            "/v1/models", profile=valid_profile, key=profile_api_key(config, cross_profile)
        )
    return HermesProbeResult(
        available=available,
        version=version,
        cli_output=version,
        health=health_status == 200 and bool(health),
        capabilities=capabilities,
        models=models,
        profiles=sorted(set(served)),
        multiplex=multiplex,
        profile_status=profile_status,
        profile_toolsets=profile_toolsets,
        valid_profile_status=valid_profile_status,
        cross_profile_status=cross_profile_status,
        errors=tuple(dict.fromkeys(errors)),
    )


def _write_profile_env(profile_home: Path, values: dict[str, str]) -> None:
    profile_home.mkdir(parents=True, exist_ok=True)
    path = profile_home / ".env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _write_json_atomic(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(values, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _sync_profile_env(
    profile_home: Path,
    profile_key: str,
    config: AppConfig,
    *,
    extra: dict[str, str] | None = None,
) -> None:
    values = _read_env_file(profile_home / ".env")
    values.update(
        {
            "API_SERVER_KEY": profile_key,
            "API_SERVER_ENABLED": "false",
            "OPENAI_API_KEY": config.llm_api_key,
            "OPENAI_BASE_URL": config.llm_base_url,
            "OPENAI_MODEL": config.llm_model,
            "CHRONICLE_LLM_API_KEY": config.llm_api_key,
            "CHRONICLE_LLM_BASE_URL": config.llm_base_url,
            "CHRONICLE_LLM_MODEL": config.llm_model,
        }
    )
    values.update(extra or {})
    _write_profile_env(profile_home, values)


def _sync_profile_config(
    profile_home: Path,
    config: AppConfig,
    template: Path,
    *,
    world_tools: bool = False,
    world_server_name: str = "chronicle-world",
) -> None:
    path = profile_home / "config.yaml"
    if not path.exists() or not template.exists():
        raise RuntimeError(f"{profile_home.name} is missing config.yaml")
    values = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    values.setdefault("model", {})["default"] = config.llm_model
    provider = values.setdefault("providers", {}).setdefault("chronicle-openai", {})
    provider["base_url"] = config.llm_base_url
    provider["model"] = config.llm_model
    provider["api_mode"] = config.llm_api_mode
    if world_tools:
        values.setdefault("agent", {})["max_turns"] = 8
        values.setdefault("platform_toolsets", {})["api_server"] = [
            "memory",
            world_server_name,
        ]
        values["mcp_servers"] = {
            world_server_name: {
                "command": _python_executable(),
                "args": ["-m", "chronicle.world_mcp"],
                "env": {
                    "CHRONICLE_DATABASE_URL": "${CHRONICLE_DATABASE_URL}",
                    "CHRONICLE_WORLD_TOKEN": "${CHRONICLE_WORLD_TOKEN}",
                },
                "timeout": 30,
                "connect_timeout": 30,
            }
        }
    path.write_text(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8")


def lifetime_profile_name(worldline_id: str, lifetime_id: str) -> str:
    return f"chronicle-{worldline_id}-{lifetime_id}"


def lifetime_world_server_name(worldline_id: str, lifetime_id: str) -> str:
    return f"chronicle-volume-world-{worldline_id}-{lifetime_id}"


def stable_lifetime_profile_marker(worldline_id: str, lifetime_id: str, profile: str) -> str:
    return hashlib.sha256(
        f"{worldline_id}:{lifetime_id}:{profile}:v6".encode()
    ).hexdigest()


def _lifetime_pending_profile_path(config: AppConfig, profile: str) -> Path:
    return config.runtime_dir / "lifetime-profile-pending" / f"{profile}.json"


def _lifetime_marker_values(
    *,
    profile: str,
    worldline_id: str,
    volume_id: str,
    content_version: int,
    content_hash: str,
    lifetime_id: str,
    genesis_hash: str,
    runtime_epoch: str,
    ownership_marker: str,
    world_server_name: str,
) -> dict[str, Any]:
    return {
        "profile_scope": "LIFETIME",
        "profile": profile,
        "worldline_id": worldline_id,
        "volume_id": volume_id,
        "volume_content_version": content_version,
        "volume_content_hash": content_hash,
        "lifetime_id": lifetime_id,
        "genesis_hash": genesis_hash,
        "runtime_epoch": runtime_epoch,
        "ownership_marker": ownership_marker,
        "distribution": "chronicle-actor",
        "toolsets": ["memory", world_server_name],
    }


def _lifetime_marker_matches(
    values: Any,
    *,
    profile: str,
    worldline_id: str,
    volume_id: str,
    content_version: int,
    content_hash: str,
    lifetime_id: str,
    genesis_hash: str,
    runtime_epoch: str,
    ownership_marker: str,
    world_server_name: str,
) -> bool:
    return isinstance(values, dict) and values == _lifetime_marker_values(
        profile=profile,
        worldline_id=worldline_id,
        volume_id=volume_id,
        content_version=content_version,
        content_hash=content_hash,
        lifetime_id=lifetime_id,
        genesis_hash=genesis_hash,
        runtime_epoch=runtime_epoch,
        ownership_marker=ownership_marker,
        world_server_name=world_server_name,
    )


def _lifetime_pending_matches(
    path: Path,
    *,
    profile: str,
    worldline_id: str,
    lifetime_id: str,
    runtime_epoch: str,
    ownership_marker: str,
) -> bool:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(values, dict) and values == {
        "profile": profile,
        "profile_scope": "LIFETIME",
        "worldline_id": worldline_id,
        "lifetime_id": lifetime_id,
        "runtime_epoch": runtime_epoch,
        "ownership_marker": ownership_marker,
    }


def _sync_lifetime_soul(profile_home: Path, lifetime: dict[str, Any]) -> None:
    path = profile_home / "SOUL.md"
    if not path.exists():
        path.write_text("# Chronicle Persistent Lifetime\n", encoding="utf-8")
    common = path.read_text(encoding="utf-8").rstrip()
    context = lifetime.get("genesis_context", {})
    if isinstance(context, dict):
        context_text = "；".join(f"{key}：{value}" for key, value in context.items())
    else:
        context_text = str(context)
    authority = "；".join(str(item) for item in lifetime.get("stable_authority", []))
    stable_section = (
        "\n\n## Persistent Lifetime Genesis\n\n"
        f"主体：{lifetime.get('display_name', lifetime.get('seat', ''))}\n\n"
        f"Genesis context：{context_text}\n\n"
        f"Stable authority：{authority}\n"
        "\nV6 Wake contract：每次唤醒只依据冻结的 Lifetime context 判断；通过一个且只有一个世界写工具提交行动（communicate、investigate、manage_offer、operate、update_plan、schedule_revisit，或用 `logical_intent` 提交 wait/message/update_plan）。普通 Wake 不得调用 memory。\n"
    )
    if "## Persistent Lifetime Genesis" not in common:
        path.write_text(common + stable_section, encoding="utf-8")


def _owned_lifetime_server_names(
    config: AppConfig,
    worldline_ids: set[str],
) -> set[str]:
    """Return MCP names proven by their matching V6 Lifetime markers."""

    profiles_root = config.hermes_home / "profiles"
    if not profiles_root.is_dir():
        return set()
    owned: set[str] = set()
    for profile_home in profiles_root.iterdir():
        if profile_home.is_symlink() or not profile_home.is_dir():
            continue
        marker = profile_home / "chronicle-genesis.json"
        try:
            values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(values, dict) or values.get("profile_scope") != "LIFETIME":
            continue
        worldline_id = str(values.get("worldline_id", ""))
        lifetime_id = str(values.get("lifetime_id", ""))
        profile = str(values.get("profile", ""))
        server_name = lifetime_world_server_name(worldline_id, lifetime_id)
        if (
            worldline_id not in worldline_ids
            or profile != profile_home.name
            or profile != lifetime_profile_name(worldline_id, lifetime_id)
            or values.get("ownership_marker")
            != stable_lifetime_profile_marker(worldline_id, lifetime_id, profile)
            or values.get("toolsets") != ["memory", server_name]
        ):
            continue
        owned.add(server_name)
    return owned


def _gateway_mcp_server_config(token_key: str, database_key: str) -> dict[str, Any]:
    return {
        "command": _python_executable(),
        "args": ["-m", "chronicle.world_mcp"],
        "env": {
            "CHRONICLE_DATABASE_URL": f"${{{database_key}}}",
            "CHRONICLE_WORLD_TOKEN": f"${{{token_key}}}",
        },
        "timeout": 30,
        "connect_timeout": 30,
    }


def _sync_gateway_lifetime_mcp(
    config: AppConfig,
    records: dict[str, dict[str, Any]],
) -> None:
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.setdefault("mcp_servers", {})
    root_env = _read_env_file(config.hermes_home / ".env")
    worldline_ids = {str(record["worldline_id"]) for record in records.values()}
    owned_servers = _owned_lifetime_server_names(config, worldline_ids)
    for record in records.values():
        server_name = str(record["world_server_name"])
        suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
        token_key = f"{suffix}_TOKEN"
        database_key = f"{suffix}_DATABASE_URL"
        existing = servers.get(server_name)
        if server_name not in owned_servers and (
            existing is not None or token_key in root_env or database_key in root_env
        ):
            raise RuntimeError(f"refusing to replace unowned Volume World MCP server {server_name}")
        if server_name in owned_servers and existing is not None:
            if (
                existing != _gateway_mcp_server_config(token_key, database_key)
                or root_env.get(token_key) != str(record["world_token"])
                or root_env.get(database_key) != f"sqlite:///{config.database_path}"
            ):
                raise RuntimeError(f"refusing to replace unverified Volume World MCP server {server_name}")
    managed_servers = [name for name in owned_servers if name in servers]
    for server_name in managed_servers:
        servers.pop(server_name, None)
        suffix = re.sub(r"[^A-Z0-9_]", "_", str(server_name).upper())
        root_env.pop(f"{suffix}_TOKEN", None)
        root_env.pop(f"{suffix}_DATABASE_URL", None)
    for record in records.values():
        server_name = str(record["world_server_name"])
        suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
        token_key = f"{suffix}_TOKEN"
        database_key = f"{suffix}_DATABASE_URL"
        root_env[token_key] = str(record["world_token"])
        root_env[database_key] = f"sqlite:///{config.database_path}"
        servers[server_name] = _gateway_mcp_server_config(token_key, database_key)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    _write_profile_env(config.hermes_home, root_env)


def materialize_lifetime_profiles(
    config: AppConfig,
    worldline_id: str,
    lifetimes: list[dict[str, Any]],
    *,
    volume_id: str,
    content_version: int,
    content_hash: str,
    runtime_epoch: str,
) -> dict[str, dict[str, Any]]:
    """Materialize every V6 Lifetime Profile without starting cognition or a Wake."""

    distribution = config.root / ACTOR_DISTRIBUTION
    records: dict[str, dict[str, Any]] = {}
    installed: list[Path] = []
    try:
        for lifetime in lifetimes:
            lifetime_id = str(lifetime.get("id") or lifetime.get("lifetime_id") or "")
            if not lifetime_id:
                raise RuntimeError("V6 Lifetime is missing its durable id")
            profile = lifetime_profile_name(worldline_id, lifetime_id)
            world_server_name = lifetime_world_server_name(worldline_id, lifetime_id)
            expected_marker = stable_lifetime_profile_marker(worldline_id, lifetime_id, profile)
            profile_home = config.hermes_home / "profiles" / profile
            marker = profile_home / "chronicle-genesis.json"
            pending = _lifetime_pending_profile_path(config, profile)
            marker_values: dict[str, Any] | None = None
            if profile_home.exists():
                if profile_home.is_symlink():
                    raise RuntimeError(f"cannot verify Lifetime Profile {profile}")
                try:
                    parsed_marker = json.loads(marker.read_text(encoding="utf-8"))
                    if isinstance(parsed_marker, dict):
                        marker_values = parsed_marker
                except (OSError, ValueError):
                    marker_values = None
                if marker_values is not None and not _lifetime_marker_matches(
                    marker_values,
                    profile=profile,
                    worldline_id=worldline_id,
                    volume_id=volume_id,
                    content_version=int(content_version),
                    content_hash=content_hash,
                    lifetime_id=lifetime_id,
                    genesis_hash=str(lifetime["genesis_hash"]),
                    runtime_epoch=runtime_epoch,
                    ownership_marker=expected_marker,
                    world_server_name=world_server_name,
                ):
                    marker_values = None
                if marker_values is None:
                    if not _lifetime_pending_matches(
                        pending,
                        profile=profile,
                        worldline_id=worldline_id,
                        lifetime_id=lifetime_id,
                        runtime_epoch=runtime_epoch,
                        ownership_marker=expected_marker,
                    ):
                        raise RuntimeError(f"{profile} does not belong to this Volume Worldline")
                    shutil.rmtree(profile_home)
            fresh = not profile_home.exists()
            if fresh:
                _write_json_atomic(
                    pending,
                    {
                        "profile": profile,
                        "profile_scope": "LIFETIME",
                        "worldline_id": worldline_id,
                        "lifetime_id": lifetime_id,
                        "runtime_epoch": runtime_epoch,
                        "ownership_marker": expected_marker,
                    },
                )
                result = _run_cli(
                    config,
                    ["profile", "install", str(distribution), "--name", profile, "-y"],
                    timeout=90,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"Hermes Lifetime Profile install failed for {profile}: {result.stderr.strip()}"
                    )
                installed.append(profile_home)
                _write_json_atomic(
                    marker,
                    _lifetime_marker_values(
                        profile=profile,
                        worldline_id=worldline_id,
                        volume_id=volume_id,
                        content_version=int(content_version),
                        content_hash=content_hash,
                        lifetime_id=lifetime_id,
                        genesis_hash=str(lifetime["genesis_hash"]),
                        runtime_epoch=runtime_epoch,
                        ownership_marker=expected_marker,
                        world_server_name=world_server_name,
                    ),
                )
            profile_env = _read_env_file(profile_home / ".env")
            profile_key = profile_env.get("API_SERVER_KEY", "") or generate_secret(32)
            world_token = profile_env.get("CHRONICLE_WORLD_TOKEN", "") or generate_secret(40)
            _sync_profile_env(
                profile_home,
                profile_key,
                config,
                extra={
                    "CHRONICLE_DATABASE_URL": f"sqlite:///{config.database_path}",
                    "CHRONICLE_WORLD_TOKEN": world_token,
                },
            )
            _sync_profile_config(
                profile_home,
                config,
                distribution / "config.yaml",
                world_tools=True,
                world_server_name=world_server_name,
            )
            if fresh:
                _sync_lifetime_soul(profile_home, dict(lifetime))
            memory_path = profile_home / "memories" / "MEMORY.md"
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            memory_path.touch(exist_ok=True)
            pending.unlink(missing_ok=True)
            records[lifetime_id] = {
                "profile": profile,
                "profile_scope": "LIFETIME",
                "worldline_id": worldline_id,
                "volume_id": volume_id,
                "lifetime_id": lifetime_id,
                "profile_key": profile_key,
                "world_token": world_token,
                "ownership_marker": expected_marker,
                "world_server_name": world_server_name,
                "controller": str(lifetime.get("controller", "AGENT")),
                "profile_state": str(lifetime.get("profile_state", "DORMANT")),
            }
        if records:
            existing_gateway_key = _read_env_file(config.hermes_home / ".env").get("API_SERVER_KEY", "")
            _write_gateway_env(config, existing_gateway_key or next(iter(records.values()))["profile_key"])
            _sync_gateway_lifetime_mcp(config, records)
    except Exception as exc:
        for profile_home in reversed(installed):
            if profile_home.exists():
                try:
                    shutil.rmtree(profile_home)
                except OSError as cleanup_exc:
                    raise RuntimeError(
                        f"Hermes Lifetime Profile cleanup failed for {profile_home.name}: {cleanup_exc}"
                    ) from exc
        raise
    return records


def load_lifetime_profile_records(
    config: AppConfig,
    worldline_id: str,
    lifetimes: list[dict[str, Any]],
    *,
    volume_id: str,
    content_version: int,
    content_hash: str,
    runtime_epoch: str,
) -> dict[str, dict[str, Any]]:
    """Read V6 Lifetime Profiles without repairing or changing their files."""

    records: dict[str, dict[str, Any]] = {}
    for lifetime in lifetimes:
        lifetime_id = str(
            lifetime.get("lifetime_id") or lifetime.get("seat") or lifetime.get("id") or ""
        )
        profile = lifetime_profile_name(worldline_id, lifetime_id)
        world_server_name = lifetime_world_server_name(worldline_id, lifetime_id)
        ownership_marker = stable_lifetime_profile_marker(worldline_id, lifetime_id, profile)
        marker_path = config.hermes_home / "profiles" / profile / "chronicle-genesis.json"
        try:
            marker_values = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"cannot verify Lifetime Profile {profile}") from exc
        if not _lifetime_marker_matches(
            marker_values,
            profile=profile,
            worldline_id=worldline_id,
            volume_id=volume_id,
            content_version=int(content_version),
            content_hash=content_hash,
            lifetime_id=lifetime_id,
            genesis_hash=str(lifetime["genesis_hash"]),
            runtime_epoch=runtime_epoch,
            ownership_marker=ownership_marker,
            world_server_name=world_server_name,
        ):
            raise RuntimeError(f"{profile} does not belong to this Volume Worldline")
        env = _read_env_file(config.hermes_home / "profiles" / profile / ".env")
        profile_key = env.get("API_SERVER_KEY", "")
        world_token = env.get("CHRONICLE_WORLD_TOKEN", "")
        if not profile_key or not world_token:
            raise RuntimeError(f"{profile} is missing its private runtime credentials")
        records[lifetime_id] = {
            "profile": profile,
            "profile_scope": "LIFETIME",
            "worldline_id": worldline_id,
            "volume_id": volume_id,
            "lifetime_id": lifetime_id,
            "profile_key": profile_key,
            "world_token": world_token,
            "ownership_marker": ownership_marker,
            "world_server_name": world_server_name,
        }
    _verify_lifetime_runtime_configuration(config, records)
    return records


def _verify_lifetime_runtime_configuration(
    config: AppConfig,
    records: dict[str, dict[str, Any]],
) -> None:
    """Verify V6 Profile files and only the V6 Gateway MCP allowlist."""

    expected_servers = {str(record["world_server_name"]) for record in records.values()}
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise RuntimeError("gateway MCP configuration is invalid")
    managed_servers = expected_servers & {str(name) for name in servers}
    if managed_servers != expected_servers:
        raise RuntimeError("current Volume Gateway MCP allowlist is incomplete")
    root_env = _read_env_file(config.hermes_home / ".env")
    database_url = f"sqlite:///{config.database_path}"
    expected_command = _python_executable()
    for record in records.values():
        profile = str(record["profile"])
        server_name = str(record["world_server_name"])
        suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
        expected_server = {
            "command": expected_command,
            "args": ["-m", "chronicle.world_mcp"],
            "env": {
                "CHRONICLE_DATABASE_URL": f"${{{suffix}_DATABASE_URL}}",
                "CHRONICLE_WORLD_TOKEN": f"${{{suffix}_TOKEN}}",
            },
            "timeout": 30,
            "connect_timeout": 30,
        }
        if servers.get(server_name) != expected_server:
            raise RuntimeError(f"{profile} has an incomplete Volume World MCP configuration")
        if (
            root_env.get(f"{suffix}_TOKEN") != str(record["world_token"])
            or root_env.get(f"{suffix}_DATABASE_URL") != database_url
        ):
            raise RuntimeError(f"{profile} is missing its root Volume World MCP credentials")
        profile_home = config.hermes_home / "profiles" / profile
        profile_config_path = profile_home / "config.yaml"
        profile_values = (
            yaml.safe_load(profile_config_path.read_text(encoding="utf-8"))
            if profile_config_path.exists()
            else {}
        ) or {}
        profile_toolsets = profile_values.get("platform_toolsets", {}).get("api_server", [])
        profile_servers = profile_values.get("mcp_servers", {})
        expected_profile_server = {
            "command": expected_command,
            "args": ["-m", "chronicle.world_mcp"],
            "env": {
                "CHRONICLE_DATABASE_URL": "${CHRONICLE_DATABASE_URL}",
                "CHRONICLE_WORLD_TOKEN": "${CHRONICLE_WORLD_TOKEN}",
            },
            "timeout": 30,
            "connect_timeout": 30,
        }
        profile_env = _read_env_file(profile_home / ".env")
        profile_server = (
            profile_servers.get(server_name) if isinstance(profile_servers, dict) else None
        )
        if (
            profile_toolsets != ["memory", server_name]
            or set(profile_servers) != {server_name}
            or profile_server != expected_profile_server
            or profile_env.get("CHRONICLE_DATABASE_URL") != database_url
            or profile_env.get("CHRONICLE_WORLD_TOKEN") != str(record["world_token"])
        ):
            raise RuntimeError(f"{profile} has an incomplete Lifetime tool configuration")


def cleanup_volume_runtime(
    config: AppConfig,
    worldline_id: str,
    profiles: list[str],
    *,
    server_names: list[str] | None = None,
) -> None:
    """Remove V6 Lifetime Profiles only when the owning Volume is sealed."""

    requested_servers = {str(name) for name in (server_names or [])}
    managed_servers: set[str] = set()
    for profile in profiles:
        profile_home = config.hermes_home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        pending = _lifetime_pending_profile_path(config, profile)
        if not profile_home.exists():
            if pending.exists():
                try:
                    pending_values = json.loads(pending.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise RuntimeError(f"cannot verify pending Lifetime Profile {profile}") from exc
                if (
                    not isinstance(pending_values, dict)
                    or pending_values.get("profile_scope") != "LIFETIME"
                    or pending_values.get("profile") != profile
                    or pending_values.get("worldline_id") != worldline_id
                ):
                    raise RuntimeError(f"refusing to remove unrelated pending Profile {profile}")
                lifetime_id = str(pending_values.get("lifetime_id", ""))
                if not lifetime_id or lifetime_profile_name(worldline_id, lifetime_id) != profile:
                    raise RuntimeError(f"refusing to remove unrelated pending Profile {profile}")
                server_name = lifetime_world_server_name(worldline_id, lifetime_id)
                if requested_servers and server_name not in requested_servers:
                    raise RuntimeError(f"refusing to remove unrelated Volume World MCP server {server_name}")
                managed_servers.add(server_name)
                pending.unlink()
            continue
        if profile_home.is_symlink() or not profile_home.is_dir():
            raise RuntimeError(f"cannot verify Lifetime Profile {profile}")
        try:
            values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"cannot verify Lifetime Profile {profile}") from exc
        if not isinstance(values, dict) or values.get("profile_scope") != "LIFETIME":
            raise RuntimeError(f"refusing to remove unrelated Hermes Profile {profile}")
        lifetime_id = str(values.get("lifetime_id", ""))
        if (
            values.get("worldline_id") != worldline_id
            or values.get("profile") != profile
            or not lifetime_id
            or lifetime_profile_name(worldline_id, lifetime_id) != profile
        ):
            raise RuntimeError(f"refusing to remove unrelated Hermes Profile {profile}")
        server_name = lifetime_world_server_name(worldline_id, lifetime_id)
        if requested_servers and server_name not in requested_servers:
            raise RuntimeError(f"refusing to remove unrelated Volume World MCP server {server_name}")
        managed_servers.add(server_name)
        shutil.rmtree(profile_home)
        pending.unlink(missing_ok=True)

    if requested_servers - managed_servers:
        raise RuntimeError("cannot verify ownership of a Volume World MCP server")

    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.get("mcp_servers", {})
    if isinstance(servers, dict):
        root_env = _read_env_file(config.hermes_home / ".env")
        for server_name in managed_servers:
            if server_name not in servers:
                continue
            servers.pop(server_name, None)
            suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
            root_env.pop(f"{suffix}_TOKEN", None)
            root_env.pop(f"{suffix}_DATABASE_URL", None)
        config_path.write_text(
            yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        _write_profile_env(config.hermes_home, root_env)


def profile_memory_path(config: AppConfig, profile: str) -> Path:
    return config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"


def read_profile_memory(config: AppConfig, profile: str) -> tuple[str, str]:
    path = profile_memory_path(config, profile)
    if not path.exists():
        return "", hashlib.sha256(b"").hexdigest()
    return path.read_text(encoding="utf-8"), hashlib.sha256(path.read_bytes()).hexdigest()


def restore_profile_memory(config: AppConfig, profile: str, existed: bool, text: str) -> None:
    path = profile_memory_path(config, profile)
    if existed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    elif path.exists():
        path.unlink()


def _write_gateway_env(config: AppConfig, api_server_key: str) -> Path:
    """Configure the private Gateway on the configured local API port."""

    try:
        configured_port = urlparse(config.hermes_base_url).port
    except ValueError as exc:
        raise RuntimeError("Chronicle Hermes base URL has an invalid port") from exc
    path = config.hermes_home / ".env"
    values = _read_env_file(path)
    values.update(
        {
            "API_SERVER_ENABLED": "true",
            "API_SERVER_KEY": api_server_key,
            "API_SERVER_HOST": "127.0.0.1",
            "API_SERVER_PORT": str(configured_port or 8642),
            "GATEWAY_MULTIPLEX_PROFILES": "true",
        }
    )
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path

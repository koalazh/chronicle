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

from .config import AppConfig, generate_secret, write_runtime_env
from .models import ActorWakeResponse

PROFILE_NAMES = {
    "A": "chronicle-seat-a",
    "B": "chronicle-seat-b",
    "C": "chronicle-seat-c",
}
ACTOR_DISTRIBUTION = "hermes/chronicle-actor"


def _python_executable() -> str:
    """Use one stable interpreter identity across Profile write/reconcile seams."""

    return str(Path(sys.executable).resolve())


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


def parse_actor_response(text: str) -> ActorWakeResponse:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return ActorWakeResponse.model_validate_json(cleaned)
    except Exception as exc:
        raise ValueError(f"Hermes actor response was not valid Chronicle JSON: {exc}") from exc


def actor_protocol_prompt() -> str:
    return (
        "You are a Chronicle historical actor. You are not an omniscient narrator. "
        "Only use the opaque observations, prior beliefs, and subjective memory in this request. "
        "Never infer or name real people, places, dates, later outcomes, alliances, or facts not supplied. "
        "Return only one JSON object matching the requested schema. Keep assessment short. "
        "Normal observation wakes must set memory_action to NO_CHANGE; only a reflection wake may propose UPDATE_MEMORY."
    )


def wake_messages(runtime_input: dict[str, Any], wake_type: str) -> list[dict[str, str]]:
    schema = {
        "assessment": "short interpretation",
        "belief_updates": [{"belief_key": "string", "direction": "up|down|unchanged", "confidence": 0.0, "statement": "short"}],
        "intentions": [{"action": "WAIT", "target": "", "reason": "short", "payload": {}}],
        "uncertainties": ["string"],
        "memory_action": "NO_CHANGE",
        "memory_text": "only for reflection",
    }
    protocol = actor_protocol_prompt()
    if wake_type == "reflection":
        protocol += (
            " This is a Reflection wake. If memory_action is UPDATE_MEMORY, call the built-in "
            "memory tool exactly once with target=memory and the compact memory_text before "
            "returning the final JSON. If memory_action is NO_CHANGE, do not call it."
        )
    else:
        protocol += " This is an ordinary wake; do not call the memory tool."
    return [
        {"role": "system", "content": protocol},
        {
            "role": "user",
            "content": json.dumps(
                {"wake_type": wake_type, "runtime_input": runtime_input, "output_schema": schema},
                ensure_ascii=False,
            ),
        },
    ]


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
    profiles = profiles or list(PROFILE_NAMES.values())
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
    crisis_world: bool = False,
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
    if crisis_world:
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


def _crisis_profile_name(run_id: str, actor_id: str) -> str:
    return f"chronicle-{run_id[-8:]}-{actor_id}"


def _crisis_world_server_name(run_id: str, actor_id: str) -> str:
    return f"chronicle-world-{run_id[-8:]}-{actor_id}"


def _sync_crisis_soul(profile_home: Path, role_charter: dict[str, Any]) -> None:
    path = profile_home / "SOUL.md"
    common = path.read_text(encoding="utf-8") if path.exists() else "# Chronicle Actor\n"
    charter = (
        "\n## 本次危局角色章程\n\n"
        f"你是谁：{role_charter['who']}\n\n"
        f"责任：{'；'.join(role_charter['responsibility'])}\n\n"
        f"权限：{'；'.join(role_charter['authority'])}\n\n"
        f"张力：{'；'.join(role_charter['tensions'])}\n\n"
        "你只能依据当前 Wake 提供的私有视野行动。不要使用后世知识，也不要替世界宣布结果。\n"
    )
    path.write_text(common.rstrip() + "\n" + charter, encoding="utf-8")


def _crisis_pending_profile_path(config: AppConfig, profile: str) -> Path:
    return config.runtime_dir / "profile-pending" / f"{profile}.json"


def _write_json_atomic(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(values, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _pending_profile_matches(
    path: Path,
    *,
    profile: str,
    actor_id: str,
    run_id: str,
    crisis_id: str,
    runtime_epoch: str,
    ownership_marker: str,
) -> bool:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(values, dict) and values == {
        "profile": profile,
        "actor_id": actor_id,
        "run_id": run_id,
        "crisis_id": crisis_id,
        "runtime_epoch": runtime_epoch,
        "ownership_marker": ownership_marker,
    }


def _owned_pending_profile(
    config: AppConfig,
    profile: str,
    run_id: str,
) -> dict[str, Any] | None:
    """Return a pending-install record only when it proves this Run owns it."""

    path = _crisis_pending_profile_path(config, profile)
    if path.is_symlink():
        return None
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(values, dict):
        return None
    actor_id = str(values.get("actor_id", ""))
    if (
        values.get("profile") != profile
        or values.get("run_id") != run_id
        or not actor_id
        or profile != _crisis_profile_name(run_id, actor_id)
        or values.get("ownership_marker")
        != stable_profile_marker(run_id, actor_id, profile)
    ):
        return None
    return values


def materialize_crisis_profiles(
    config: AppConfig,
    run_id: str,
    actors: list[dict[str, Any]],
    *,
    crisis_id: str,
    runtime_epoch: str,
) -> dict[str, dict[str, Any]]:
    """Create or verify the exact Run-scoped Profiles needed by one live Run."""

    distribution = config.root / ACTOR_DISTRIBUTION
    records: dict[str, dict[str, Any]] = {}
    installed: list[Path] = []
    try:
        for actor in actors:
            actor_id = str(actor["id"])
            profile = _crisis_profile_name(run_id, actor_id)
            world_server_name = _crisis_world_server_name(run_id, actor_id)
            if actor.get("profile", profile) != profile or actor.get(
                "world_server_name", world_server_name
            ) != world_server_name:
                raise RuntimeError(f"crisis Profile identity is inconsistent for {actor_id}")
            profile_home = config.hermes_home / "profiles" / profile
            marker = profile_home / "chronicle-genesis.json"
            expected_marker = stable_profile_marker(run_id, actor_id, profile)
            pending = _crisis_pending_profile_path(config, profile)
            marker_values: dict[str, Any] | None = None
            if profile_home.exists():
                if profile_home.is_symlink():
                    raise RuntimeError(f"cannot verify crisis Profile {profile}")
                try:
                    parsed_marker = json.loads(marker.read_text(encoding="utf-8"))
                    if isinstance(parsed_marker, dict):
                        marker_values = parsed_marker
                except (OSError, ValueError):
                    marker_values = None
                marker_mismatch = marker_values is not None and (
                    marker_values.get("profile") != profile
                    or marker_values.get("actor_id") != actor_id
                    or marker_values.get("crisis_id") != crisis_id
                    or marker_values.get("run_id") != run_id
                    or marker_values.get("worldline_id") != run_id
                    or marker_values.get("genesis_hash") != str(actor["genesis_hash"])
                    or marker_values.get("initial_memory_snapshot")
                    != dict(actor["initial_memory_snapshot"])
                    or marker_values.get("runtime_epoch") != runtime_epoch
                    or marker_values.get("ownership_marker") != expected_marker
                    or marker_values.get("toolsets") != ["memory", world_server_name]
                )
                if marker_mismatch and not _pending_profile_matches(
                    pending,
                    profile=profile,
                    actor_id=actor_id,
                    run_id=run_id,
                    crisis_id=crisis_id,
                    runtime_epoch=runtime_epoch,
                    ownership_marker=expected_marker,
                ):
                    raise RuntimeError(f"{profile} does not belong to this Chronicle Run")
                if marker_mismatch:
                    marker_values = None
                if marker_values is None:
                    if not _pending_profile_matches(
                        pending,
                        profile=profile,
                        actor_id=actor_id,
                        run_id=run_id,
                        crisis_id=crisis_id,
                        runtime_epoch=runtime_epoch,
                        ownership_marker=expected_marker,
                    ):
                        raise RuntimeError(f"cannot verify crisis Profile {profile}")
                    if profile_home.is_symlink() or not profile_home.is_dir():
                        raise RuntimeError(f"cannot repair crisis Profile {profile}")
                    shutil.rmtree(profile_home)
            if not profile_home.exists():
                _write_json_atomic(
                    pending,
                    {
                        "profile": profile,
                        "actor_id": actor_id,
                        "run_id": run_id,
                        "crisis_id": crisis_id,
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
                        f"Hermes crisis Profile install failed for {profile}: {result.stderr.strip()}"
                )
                installed.append(profile_home)
                profile_key = generate_secret(32)
                world_token = generate_secret(40)
                ownership_marker = stable_profile_marker(run_id, actor_id, profile)
                _write_json_atomic(
                    marker,
                    {
                        "profile": profile,
                        "actor_id": actor_id,
                        "crisis_id": crisis_id,
                        "run_id": run_id,
                        "worldline_id": run_id,
                        "genesis_hash": str(actor["genesis_hash"]),
                        "initial_memory_snapshot": dict(actor["initial_memory_snapshot"]),
                        "runtime_epoch": runtime_epoch,
                        "ownership_marker": ownership_marker,
                        "distribution": "chronicle-actor",
                        "toolsets": ["memory", world_server_name],
                    },
                )
            else:
                profile_env = _read_env_file(profile_home / ".env")
                profile_key = profile_env.get("API_SERVER_KEY", "") or generate_secret(32)
                world_token = profile_env.get("CHRONICLE_WORLD_TOKEN", "") or generate_secret(40)
                ownership_marker = expected_marker
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
                crisis_world=True,
                world_server_name=world_server_name,
            )
            _sync_crisis_soul(profile_home, dict(actor["role_charter"]))
            memory_path = profile_home / "memories" / "MEMORY.md"
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            memory_path.touch(exist_ok=True)
            pending.unlink(missing_ok=True)
            records[actor_id] = {
                "profile": profile,
                "profile_key": profile_key,
                "world_token": world_token,
                "ownership_marker": ownership_marker,
                "world_server_name": world_server_name,
            }
        if records:
            existing_gateway_key = _read_env_file(config.hermes_home / ".env").get("API_SERVER_KEY", "")
            _write_gateway_env(
                config,
                existing_gateway_key or next(iter(records.values()))["profile_key"],
            )
            _sync_gateway_crisis_mcp(config, records)
    except Exception as exc:
        for profile_home in reversed(installed):
            if profile_home.exists():
                try:
                    shutil.rmtree(profile_home)
                except OSError as cleanup_exc:
                    raise RuntimeError(
                        f"Hermes crisis Profile cleanup failed for {profile_home.name}: {cleanup_exc}"
                    ) from exc
        raise
    return records


def lifetime_profile_name(worldline_id: str, lifetime_id: str) -> str:
    return f"chronicle-{worldline_id}-{lifetime_id}"


def lifetime_world_server_name(worldline_id: str, lifetime_id: str) -> str:
    return f"chronicle-volume-world-{worldline_id}-{lifetime_id}"


def stable_lifetime_profile_marker(worldline_id: str, lifetime_id: str, profile: str) -> str:
    return hashlib.sha256(
        f"{worldline_id}:{lifetime_id}:{profile}:v5".encode()
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
        "\nV5 Wake contract：每次唤醒只依据冻结的 Lifetime context 判断；通过一个且只有一个世界写工具提交行动（communicate、investigate、manage_offer、operate、update_plan、schedule_revisit，或用 `logical_intent` 提交 wait/message/update_plan）。普通 Wake 不得调用 memory。\n"
    )
    if "## Persistent Lifetime Genesis" not in common:
        path.write_text(common + stable_section, encoding="utf-8")


def _sync_gateway_lifetime_mcp(
    config: AppConfig,
    records: dict[str, dict[str, Any]],
) -> None:
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.setdefault("mcp_servers", {})
    root_env = _read_env_file(config.hermes_home / ".env")
    managed_servers = [
        name for name in servers if str(name).startswith("chronicle-volume-world-")
    ]
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
        servers[server_name] = {
            "command": _python_executable(),
            "args": ["-m", "chronicle.world_mcp"],
            "env": {
                "CHRONICLE_DATABASE_URL": f"${{{database_key}}}",
                "CHRONICLE_WORLD_TOKEN": f"${{{token_key}}}",
            },
            "timeout": 30,
            "connect_timeout": 30,
        }
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
    """Materialize every V5 Lifetime Profile without starting cognition or a Wake."""

    distribution = config.root / ACTOR_DISTRIBUTION
    records: dict[str, dict[str, Any]] = {}
    installed: list[Path] = []
    try:
        for lifetime in lifetimes:
            lifetime_id = str(lifetime.get("id") or lifetime.get("lifetime_id") or "")
            if not lifetime_id:
                raise RuntimeError("V5 Lifetime is missing its durable id")
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
                crisis_world=True,
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
    """Read V5 Lifetime Profiles without repairing or changing their files."""

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
    """Verify V5 Profile files and only the V5 Gateway MCP allowlist."""

    expected_servers = {str(record["world_server_name"]) for record in records.values()}
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise RuntimeError("gateway MCP configuration is invalid")
    managed_servers = {
        str(name)
        for name in servers
        if str(name).startswith("chronicle-volume-world-")
    }
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
    """Remove V5 Lifetime Profiles only when the owning Volume is sealed."""

    managed_servers = {
        str(name)
        for name in (server_names or [])
        if str(name).startswith(f"chronicle-volume-world-{worldline_id}-")
    }
    for profile in profiles:
        profile_home = config.hermes_home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        pending = _lifetime_pending_profile_path(config, profile)
        if not profile_home.exists():
            pending.unlink(missing_ok=True)
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
        managed_servers.add(lifetime_world_server_name(worldline_id, lifetime_id))
        shutil.rmtree(profile_home)
        pending.unlink(missing_ok=True)

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


def load_crisis_profile_records(
    config: AppConfig,
    run_id: str,
    actors: list[dict[str, Any]],
    *,
    crisis_id: str,
    runtime_epoch: str,
) -> dict[str, dict[str, Any]]:
    """Read an already-materialized Run without changing Gateway configuration."""

    records: dict[str, dict[str, Any]] = {}
    for actor in actors:
        actor_id = str(actor["id"])
        profile = _crisis_profile_name(run_id, actor_id)
        world_server_name = _crisis_world_server_name(run_id, actor_id)
        if actor.get("profile", profile) != profile or actor.get(
            "world_server_name", world_server_name
        ) != world_server_name:
            raise RuntimeError(f"crisis Profile identity is inconsistent for {actor_id}")
        profile_home = config.hermes_home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        try:
            values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"cannot verify crisis Profile {profile}") from exc
        ownership_marker = stable_profile_marker(run_id, actor_id, profile)
        if (
            values.get("profile") != profile
            or values.get("actor_id") != actor_id
            or values.get("crisis_id") != crisis_id
            or values.get("run_id") != run_id
            or values.get("worldline_id") != run_id
            or values.get("genesis_hash") != str(actor["genesis_hash"])
            or values.get("initial_memory_snapshot") != dict(actor["initial_memory_snapshot"])
            or values.get("runtime_epoch") != runtime_epoch
            or values.get("ownership_marker") != ownership_marker
            or values.get("toolsets") != ["memory", world_server_name]
        ):
            raise RuntimeError(f"{profile} does not belong to this Chronicle Run")
        env = _read_env_file(profile_home / ".env")
        profile_key = env.get("API_SERVER_KEY", "")
        world_token = env.get("CHRONICLE_WORLD_TOKEN", "")
        if not profile_key or not world_token:
            raise RuntimeError(f"{profile} is missing its private runtime credentials")
        records[actor_id] = {
            "profile": profile,
            "profile_key": profile_key,
            "world_token": world_token,
            "ownership_marker": ownership_marker,
            "world_server_name": world_server_name,
        }
    _verify_crisis_runtime_configuration(config, records)
    return records


def _verify_crisis_runtime_configuration(
    config: AppConfig,
    records: dict[str, dict[str, Any]],
) -> None:
    """Verify the current Run's Profile files and root MCP allowlist without repairing them."""

    expected_servers = {str(record["world_server_name"]) for record in records.values()}
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.get("mcp_servers", {})
    managed_servers = {
        str(name) for name in servers if str(name).startswith("chronicle-world-")
    } if isinstance(servers, dict) else set()
    if managed_servers != expected_servers:
        raise RuntimeError("current crisis Gateway MCP allowlist is incomplete")
    root_env = _read_env_file(config.hermes_home / ".env")
    database_url = f"sqlite:///{config.database_path}"
    expected_command = _python_executable()
    for record in records.values():
        profile = str(record["profile"])
        server_name = str(record["world_server_name"])
        suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
        server = servers.get(server_name)
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
        if server != expected_server:
            raise RuntimeError(f"{profile} has an incomplete World MCP configuration")
        if (
            root_env.get(f"{suffix}_TOKEN") != str(record["world_token"])
            or root_env.get(f"{suffix}_DATABASE_URL") != database_url
        ):
            raise RuntimeError(f"{profile} is missing its root World MCP credentials")
        profile_home = config.hermes_home / "profiles" / profile
        profile_config_path = profile_home / "config.yaml"
        profile_values = (
            yaml.safe_load(profile_config_path.read_text(encoding="utf-8"))
            if profile_config_path.exists()
            else {}
        ) or {}
        profile_toolsets = profile_values.get("platform_toolsets", {}).get("api_server", [])
        profile_servers = profile_values.get("mcp_servers", {})
        profile_server = profile_servers.get(server_name) if isinstance(profile_servers, dict) else None
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
        if (
            profile_toolsets != ["memory", server_name]
            or set(profile_servers) != {server_name}
            or profile_server != expected_profile_server
            or profile_env.get("CHRONICLE_DATABASE_URL") != database_url
            or profile_env.get("CHRONICLE_WORLD_TOKEN") != str(record["world_token"])
        ):
            raise RuntimeError(f"{profile} has an incomplete Profile tool configuration")


def _sync_gateway_crisis_mcp(
    config: AppConfig,
    records: dict[str, dict[str, Any]],
) -> None:
    """Register identity-specific MCP servers in the shared multiplex process."""

    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.setdefault("mcp_servers", {})
    root_env = _read_env_file(config.hermes_home / ".env")
    managed_servers = [name for name in servers if str(name).startswith("chronicle-world-")]
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
        servers[server_name] = {
            "command": _python_executable(),
            "args": ["-m", "chronicle.world_mcp"],
            "env": {
                "CHRONICLE_DATABASE_URL": f"${{{database_key}}}",
                "CHRONICLE_WORLD_TOKEN": f"${{{token_key}}}",
            },
            "timeout": 30,
            "connect_timeout": 30,
        }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(values, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _write_profile_env(config.hermes_home, root_env)


def stable_profile_marker(run_id: str, actor_id: str, profile: str) -> str:
    return hashlib.sha256(f"{run_id}:{actor_id}:{profile}:v3".encode()).hexdigest()


def remove_crisis_profiles(config: AppConfig, run_id: str, profiles: list[str]) -> None:
    """Compensate only Profiles whose marker proves ownership by an uncommitted Run."""

    for profile in profiles:
        pending = _crisis_pending_profile_path(config, profile)
        pending_values = _owned_pending_profile(config, profile, run_id)
        profile_home = config.hermes_home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        if not profile_home.exists():
            if pending_values is not None:
                pending.unlink(missing_ok=True)
            continue
        if profile_home.is_symlink() or not profile_home.is_dir():
            raise RuntimeError(f"cannot verify crisis Profile {profile}")
        try:
            values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            if pending_values is None:
                raise RuntimeError(f"cannot verify crisis Profile {profile}") from exc
            shutil.rmtree(profile_home)
            pending.unlink(missing_ok=True)
            continue
        if not isinstance(values, dict):
            if pending_values is None:
                raise RuntimeError(f"cannot verify crisis Profile {profile}")
            shutil.rmtree(profile_home)
            pending.unlink(missing_ok=True)
            continue
        if values.get("worldline_id") != run_id or values.get("profile") != profile:
            if pending_values is None:
                raise RuntimeError(f"refusing to remove unrelated Hermes Profile {profile}")
            shutil.rmtree(profile_home)
            pending.unlink(missing_ok=True)
            continue
        shutil.rmtree(profile_home)
        pending.unlink(missing_ok=True)


def cleanup_crisis_runtime(
    config: AppConfig,
    run_id: str,
    profiles: list[str],
    *,
    server_names: list[str] | None = None,
) -> None:
    """Remove only this sealed Run's managed root MCP entries and verified Profiles."""

    managed_servers = {
        str(name)
        for name in (server_names or [])
        if str(name).startswith("chronicle-world-")
    }
    for profile in profiles:
        profile_home = config.hermes_home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        pending_values = _owned_pending_profile(config, profile, run_id)
        if not profile_home.exists():
            if pending_values is not None:
                managed_servers.add(
                    _crisis_world_server_name(run_id, str(pending_values["actor_id"]))
                )
            continue
        if profile_home.is_symlink() or not profile_home.is_dir():
            raise RuntimeError(f"cannot verify crisis Profile {profile}")
        try:
            values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            if pending_values is None:
                raise RuntimeError(f"cannot verify crisis Profile {profile}") from exc
            managed_servers.add(
                _crisis_world_server_name(run_id, str(pending_values["actor_id"]))
            )
            continue
        if not isinstance(values, dict):
            if pending_values is None:
                raise RuntimeError(f"cannot verify crisis Profile {profile}")
            managed_servers.add(
                _crisis_world_server_name(run_id, str(pending_values["actor_id"]))
            )
            continue
        if values.get("worldline_id") != run_id or values.get("profile") != profile:
            if pending_values is None:
                raise RuntimeError(f"refusing to clean unrelated Hermes Profile {profile}")
            managed_servers.add(
                _crisis_world_server_name(run_id, str(pending_values["actor_id"]))
            )
            continue
        tools = values.get("toolsets", [])
        managed_servers.update(
            str(name) for name in tools if str(name).startswith("chronicle-world-")
        )
    _remove_gateway_crisis_mcp(config, sorted(managed_servers))
    remove_crisis_profiles(config, run_id, profiles)


def _remove_gateway_crisis_mcp(config: AppConfig, server_names: list[str]) -> None:
    config_path = config.hermes_home / "config.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    values = values or {}
    servers = values.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise RuntimeError("gateway MCP configuration is invalid")
    root_env = _read_env_file(config.hermes_home / ".env")
    changed = False
    for server_name in server_names:
        if server_name in servers:
            servers.pop(server_name)
            changed = True
        suffix = re.sub(r"[^A-Z0-9_]", "_", server_name.upper())
        changed = root_env.pop(f"{suffix}_TOKEN", None) is not None or changed
        changed = root_env.pop(f"{suffix}_DATABASE_URL", None) is not None or changed
    if not changed:
        return
    values["mcp_servers"] = servers
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(values, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
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


def _write_runtime_config(config: AppConfig, keys: dict[str, str]) -> Path:
    values = {
        "CHRONICLE_LLM_BASE_URL": config.llm_base_url,
        "CHRONICLE_LLM_API_KEY": config.llm_api_key,
        "CHRONICLE_LLM_MODEL": config.llm_model,
        "CHRONICLE_LLM_API_MODE": config.llm_api_mode,
        "CHRONICLE_LLM_REASONING_EFFORT": config.llm_reasoning_effort,
        **{f"CHRONICLE_{profile.upper().replace('-', '_')}_API_SERVER_KEY": key for profile, key in keys.items()},
    }
    return write_runtime_env(config, values)


def bootstrap(config: AppConfig, *, force_reset: bool = False) -> dict[str, Any]:
    if not config.llm_configured:
        raise RuntimeError("LLM is not configured; use Chronicle Setup or set the three CHRONICLE_LLM_* values")
    home = config.hermes_home
    home.mkdir(parents=True, exist_ok=True)
    distribution = config.root / ACTOR_DISTRIBUTION
    keys: dict[str, str] = {}
    installed: list[str] = []
    for seat, profile in PROFILE_NAMES.items():
        profile_home = home / "profiles" / profile
        marker = profile_home / "chronicle-genesis.json"
        if marker.exists():
            if force_reset:
                raise RuntimeError(f"{profile} already has Chronicle genesis; explicit reset is not implemented in V1")
            existing_key = _read_env_file(profile_home / ".env").get("API_SERVER_KEY", "")
            if not existing_key:
                raise RuntimeError(f"{profile} has a genesis marker but no API_SERVER_KEY")
            keys[profile] = existing_key
            _sync_profile_env(profile_home, existing_key, config)
            _sync_profile_config(profile_home, config, distribution / "config.yaml")
            continue
        if profile_home.exists():
            raise RuntimeError(f"{profile} exists without Chronicle genesis; inspect it before continuing")
        marker_tmp: Path | None = None
        try:
            result = _run_cli(
                config,
                ["profile", "install", str(distribution), "--name", profile, "-y"],
                timeout=90,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Hermes profile install failed for {profile}: {result.stderr.strip()}")
            keys[profile] = generate_secret(32)
            _sync_profile_env(profile_home, keys[profile], config)
            _sync_profile_config(profile_home, config, distribution / "config.yaml")
            marker_values = {
                "profile": profile,
                "seat": seat,
                "distribution": "chronicle-actor",
                "genesis": "opaque-actor-v1",
                "toolsets": ["memory"],
            }
            marker_tmp = profile_home / f".chronicle-genesis.{uuid.uuid4().hex}.tmp"
            marker_tmp.write_text(
                json.dumps(marker_values, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(marker_tmp, marker)
        except Exception as exc:
            if marker_tmp is not None:
                marker_tmp.unlink(missing_ok=True)
            if profile_home.exists():
                try:
                    shutil.rmtree(profile_home)
                except OSError as cleanup_exc:
                    raise RuntimeError(
                        f"Hermes Profile setup failed for {profile}; cleanup failed: {cleanup_exc}"
                    ) from exc
            raise
        installed.append(profile)
    gateway_env = _write_gateway_env(config, keys[PROFILE_NAMES["A"]])
    runtime_env = _write_runtime_config(config, keys)
    readiness = probe(config, list(PROFILE_NAMES.values()))
    return {
        "status": "GENESIS CONSISTENT",
        "ready": readiness.ready_for_all(list(PROFILE_NAMES.values())),
        "readiness": readiness.summary(),
        "profiles": list(PROFILE_NAMES.values()),
        "installed": installed,
        "runtime_env": str(runtime_env),
        "gateway_env": str(gateway_env),
        "hermes_home": str(home),
        "keys_generated": len(keys),
    }


def create_lazy_profile(
    config: AppConfig,
    seat: str,
    worldline_id: str,
    *,
    memory_text: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create one branch-scoped actor Profile at the first branch observation."""

    profile = f"chronicle-{worldline_id[-8:]}-seat-{seat.lower()}"
    profile_home = config.hermes_home / "profiles" / profile
    marker = profile_home / "chronicle-genesis.json"
    distribution = config.root / ACTOR_DISTRIBUTION
    profile_existed = profile_home.exists()
    if marker.exists():
        try:
            marker_values = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"{profile} has an invalid Chronicle genesis marker") from exc
        if marker_values.get("profile") != profile or marker_values.get("seat") != seat or marker_values.get("worldline_id") != worldline_id:
            raise RuntimeError(f"{profile} Chronicle genesis does not match this Worldline")
        if memory_text is not None:
            try:
                seed_profile_memory(config, profile, memory_text)
            except Exception as exc:
                try:
                    remove_lazy_profile(config, seat, worldline_id)
                except Exception as cleanup_exc:
                    raise RuntimeError(
                        f"Hermes lazy Profile memory seed failed for {profile}; cleanup failed: {cleanup_exc}"
                    ) from exc
                raise
        return profile, {
            "mode": "live",
            "created_on_observation": True,
            "worldline_id": worldline_id,
            "seat": seat,
            "genesis": "opaque-actor-v2-lazy",
            "toolsets": ["memory"],
        }
    if profile_home.exists():
        raise RuntimeError(f"{profile} exists without Chronicle genesis; inspect it before continuing")
    marker_tmp: Path | None = None
    try:
        result = _run_cli(
            config,
            ["profile", "install", str(distribution), "--name", profile, "-y"],
            timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Hermes lazy Profile install failed for {profile}: {result.stderr.strip()}")
        key = generate_secret(32)
        _sync_profile_env(profile_home, key, config)
        _sync_profile_config(profile_home, config, distribution / "config.yaml")
        marker_values = {
            "profile": profile,
            "seat": seat,
            "worldline_id": worldline_id,
            "distribution": "chronicle-actor",
            "genesis": "opaque-actor-v2-lazy",
            "toolsets": ["memory"],
        }
        marker_tmp = profile_home / f".chronicle-genesis.{uuid.uuid4().hex}.tmp"
        marker_tmp.write_text(
            json.dumps(marker_values, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(marker_tmp, marker)
        if memory_text is not None:
            seed_profile_memory(config, profile, memory_text)
    except Exception as exc:
        if marker_tmp is not None:
            marker_tmp.unlink(missing_ok=True)
        if not profile_existed and profile_home.exists():
            try:
                shutil.rmtree(profile_home)
            except OSError as cleanup_exc:
                raise RuntimeError(
                    f"Hermes lazy Profile setup failed for {profile}; cleanup failed: {cleanup_exc}"
                ) from exc
        raise
    return profile, {
        "mode": "live",
        "created_on_observation": True,
        "worldline_id": worldline_id,
        "seat": seat,
        "genesis": "opaque-actor-v2-lazy",
        "toolsets": ["memory"],
    }


def remove_lazy_profile(config: AppConfig, seat: str, worldline_id: str) -> None:
    """Remove an uncommitted branch Profile after its owning moment failed."""

    profile = f"chronicle-{worldline_id[-8:]}-seat-{seat.lower()}"
    profile_home = config.hermes_home / "profiles" / profile
    marker = profile_home / "chronicle-genesis.json"
    if not profile_home.exists():
        return
    try:
        marker_values = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot verify uncommitted Hermes Profile {profile}") from exc
    if (
        marker_values.get("profile") != profile
        or marker_values.get("seat") != seat
        or marker_values.get("worldline_id") != worldline_id
    ):
        raise RuntimeError(f"refusing to remove an unrelated Hermes Profile {profile}")
    shutil.rmtree(profile_home)


def seed_profile_memory(config: AppConfig, profile: str, memory_text: str) -> str:
    """Seed a branch Profile from its explicit Entry-time memory snapshot."""

    memory_path = profile_memory_path(config, profile)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = memory_path.with_name(f".{memory_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(memory_text, encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, memory_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return str(memory_path)

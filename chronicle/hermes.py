from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    errors: tuple[str, ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "version": self.version,
            "health": self.health,
            "profiles": self.profiles,
            "multiplex": self.multiplex,
            "capabilities": sorted(self.capabilities.keys()),
            "model_count": len(self.models.get("data", [])) if isinstance(self.models, dict) else 0,
            "errors": list(self.errors),
        }


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
            response = httpx.get(self._url(profile, path), headers=headers, timeout=8)
            data = response.json() if response.content else {}
            return response.status_code, data if isinstance(data, dict) else {"data": data}
        except (httpx.HTTPError, ValueError) as exc:
            return 0, {"error": str(exc)}

    def create_fresh_session(self, profile: str, key: str, wake_id: str) -> str | None:
        session_id = f"chronicle-{wake_id}-{uuid.uuid4().hex[:8]}"
        try:
            response = httpx.post(
                self._url(profile, "/api/sessions"),
                headers=self._headers(key),
                json={"id": session_id, "title": f"Chronicle {wake_id}"},
                timeout=15,
            )
            if response.status_code in {200, 201, 409}:
                return session_id
        except httpx.HTTPError:
            return None
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
        response = httpx.post(
            self._url(profile, endpoint),
            headers=headers,
            json=payload,
            timeout=self.config.llm_timeout,
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


def _profile_names(config: AppConfig) -> list[str]:
    try:
        result = _run_cli(config, ["profile", "list"])
    except (OSError, subprocess.TimeoutExpired):
        return []
    names: list[str] = []
    for line in result.stdout.splitlines():
        for name in PROFILE_NAMES.values():
            if name in line:
                names.append(name)
    return sorted(set(names))


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
    _, capabilities = client.get_json("/v1/capabilities", key=gateway_key)
    _, models = client.get_json("/v1/models", key=gateway_key)
    errors: list[str] = []
    if health_status != 200:
        errors.append(f"shared Hermes health unavailable ({health_status})")
    multiplex = bool(capabilities.get("multiplex_profiles") or capabilities.get("features", {}).get("multiplex_profiles"))
    served = _profile_names(config)
    if profiles:
        for profile in profiles:
            _, profile_models = client.get_json(
                "/v1/models", profile=profile, key=profile_api_key(config, profile)
            )
            if profile_models:
                served_model = profile_models.get("data", [])
                if served_model:
                    served.append(profile)
    multiplex = multiplex or len(set(served)) > 1
    return HermesProbeResult(
        available=available,
        version=version,
        cli_output=version,
        health=health_status == 200 and bool(health),
        capabilities=capabilities,
        models=models,
        profiles=sorted(set(served)),
        multiplex=multiplex,
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


def _sync_profile_env(profile_home: Path, profile_key: str, config: AppConfig) -> None:
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
    _write_profile_env(profile_home, values)


def _sync_profile_config(profile_home: Path, config: AppConfig, template: Path) -> None:
    path = profile_home / "config.yaml"
    if not path.exists() or not template.exists():
        raise RuntimeError(f"{profile_home.name} is missing config.yaml")
    values = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    values.setdefault("model", {})["default"] = config.llm_model
    provider = values.setdefault("providers", {}).setdefault("chronicle-openai", {})
    provider["base_url"] = config.llm_base_url
    provider["model"] = config.llm_model
    path.write_text(yaml.safe_dump(values, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_gateway_env(home: Path, api_server_key: str) -> Path:
    path = home / ".env"
    values = _read_env_file(path)
    values.update(
        {
            "API_SERVER_ENABLED": "true",
            "API_SERVER_KEY": api_server_key,
            "API_SERVER_HOST": "127.0.0.1",
            "API_SERVER_PORT": "8642",
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
        result = _run_cli(
            config,
            ["profile", "install", str(distribution), "--name", profile, "-y"],
            timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Hermes profile install failed for {profile}: {result.stderr.strip()}")
        installed.append(profile)
        keys[profile] = generate_secret(32)
        _sync_profile_env(profile_home, keys[profile], config)
        _sync_profile_config(profile_home, config, distribution / "config.yaml")
        marker.write_text(
            json.dumps(
                {
                    "profile": profile,
                    "seat": seat,
                    "distribution": "chronicle-actor",
                    "genesis": "opaque-actor-v1",
                    "toolsets": ["memory"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    gateway_env = _write_gateway_env(home, keys[PROFILE_NAMES["A"]])
    runtime_env = _write_runtime_config(config, keys)
    return {
        "status": "GENESIS CONSISTENT",
        "profiles": list(PROFILE_NAMES.values()),
        "installed": installed,
        "runtime_env": str(runtime_env),
        "gateway_env": str(gateway_env),
        "hermes_home": str(home),
        "keys_generated": len(keys),
    }

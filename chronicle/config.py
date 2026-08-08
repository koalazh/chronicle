from __future__ import annotations

import hashlib
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path_from_database_url(value: str, root: Path) -> Path:
    prefix = "sqlite:///"
    if value.startswith(prefix):
        raw = value[len(prefix) :]
        path = Path(raw)
        return path if path.is_absolute() else root / path
    raise ValueError("Chronicle V1 supports only sqlite:/// database URLs")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    root: Path
    database_path: Path
    scenario_path: Path
    runtime_dir: Path
    hermes_home: Path
    hermes_base_url: str
    hermes_bin: str
    host: str
    port: int
    dev: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_api_mode: str
    llm_reasoning_effort: str
    llm_timeout: float

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def runtime_env_path(self) -> Path:
        return self.runtime_dir / "runtime.env"

    def provider_hash(self) -> str:
        return hashlib.sha256(self.llm_base_url.encode()).hexdigest()[:16]

    def masked_api_key(self) -> str:
        if not self.llm_api_key:
            return ""
        return "••••••••••••"


def load_config(root: Path | None = None, environ: Mapping[str, str] | None = None) -> AppConfig:
    root = (root or project_root()).resolve()
    env = dict(os.environ if environ is None else environ)
    load_dotenv(root / ".env", override=False)
    if environ is None:
        runtime_env = root / ".chronicle" / "runtime.env"
        if runtime_env.exists():
            load_dotenv(runtime_env, override=True)
        env = dict(os.environ)

    db_url = env.get("CHRONICLE_DATABASE_URL", "sqlite:///./data/chronicle.db")
    hermes_home = Path(env.get("CHRONICLE_HERMES_HOME", str(root / ".chronicle" / "hermes-home")))
    if not hermes_home.is_absolute():
        hermes_home = root / hermes_home
    return AppConfig(
        root=root,
        database_path=_path_from_database_url(db_url, root),
        scenario_path=root / "scenarios" / "jiashen",
        runtime_dir=root / ".chronicle",
        hermes_home=hermes_home,
        hermes_base_url=env.get("CHRONICLE_HERMES_BASE_URL", "http://127.0.0.1:8642").rstrip("/"),
        hermes_bin=env.get("CHRONICLE_HERMES_BIN") or shutil.which("hermes") or "hermes",
        host=env.get("CHRONICLE_HOST", "127.0.0.1"),
        port=int(env.get("CHRONICLE_PORT", "8711")),
        dev=_bool(env.get("CHRONICLE_DEV")),
        llm_base_url=env.get("CHRONICLE_LLM_BASE_URL", "").rstrip("/"),
        llm_api_key=env.get("CHRONICLE_LLM_API_KEY", ""),
        llm_model=env.get("CHRONICLE_LLM_MODEL", ""),
        llm_api_mode=env.get("CHRONICLE_LLM_API_MODE", "chat_completions"),
        llm_reasoning_effort=env.get("CHRONICLE_LLM_REASONING_EFFORT", ""),
        llm_timeout=float(env.get("CHRONICLE_LLM_TIMEOUT", "180")),
    )


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def write_runtime_env(config: AppConfig, values: Mapping[str, str]) -> Path:
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    path = config.runtime_env_path
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path

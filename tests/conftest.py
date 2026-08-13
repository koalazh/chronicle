from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from chronicle.config import AppConfig, load_config
from chronicle.crisis import VolumePack
from chronicle.host import ChronicleHost

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    base = load_config(PROJECT_ROOT, environ={})
    return replace(
        base,
        database_path=tmp_path / "chronicle.db",
        runtime_dir=tmp_path / ".chronicle",
        hermes_home=tmp_path / "hermes-home",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
    )


@pytest.fixture
def pack() -> VolumePack:
    return VolumePack.load(PROJECT_ROOT / "scenarios" / "jiashen")


@pytest.fixture
def host(app_config: AppConfig) -> ChronicleHost:
    return ChronicleHost(app_config)

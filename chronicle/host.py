from __future__ import annotations

from typing import TYPE_CHECKING

from .config import AppConfig
from .db import ChronicleDB

if TYPE_CHECKING:
    from .volume_runtime import VolumeRuntime


class ChronicleHost:
    """Own the current V6 database and its single Volume runtime."""

    def __init__(self, config: AppConfig, db: ChronicleDB | None = None):
        self.config = config
        self.db = db or ChronicleDB(config.database_path)
        from .volume_runtime import VolumeRuntime

        self.volume_runtime: VolumeRuntime = VolumeRuntime(self)

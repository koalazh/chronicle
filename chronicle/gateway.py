from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .config import AppConfig
from .hermes import HermesClient


class GatewayRuntimeError(RuntimeError):
    """A fail-closed error while managing Chronicle's private Gateway child."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GatewayController:
    """Own one project-private Hermes Gateway child, or leave unknown processes untouched."""

    def __init__(
        self,
        config: AppConfig,
        *,
        spawn: Callable[..., Any] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        start_timeout: float = 12.0,
    ):
        self.config = config
        self._spawn = spawn
        self._monotonic = monotonic
        self._sleep = sleep
        self._start_timeout = start_timeout

    @property
    def owner_path(self) -> Path:
        return self.config.runtime_dir / "gateway-owner.json"

    @property
    def pid_path(self) -> Path:
        return self.config.hermes_home / "gateway.pid"

    @property
    def log_path(self) -> Path:
        return self.config.runtime_dir / "gateway.log"

    def ensure(self, run_id: str, runtime_epoch: str) -> dict[str, Any]:
        """Reuse a provably owned ready child or start a new private one."""

        owner = self._read_owner()
        if owner is not None:
            if self._owner_matches(owner, run_id, runtime_epoch):
                if self._wait_until_healthy():
                    return owner
                self._stop_verified(owner)
                return self._start(run_id, runtime_epoch)
            if self._owner_process_matches(owner):
                self._stop_verified(owner)
                return self._start(run_id, runtime_epoch)
            if (
                owner.get("config_fingerprint") != self.config_fingerprint()
                and self._owner_process_is_live(owner)
            ):
                raise GatewayRuntimeError("runtime_config_mismatch")
            if self._owner_process_is_live(owner) or self._port_is_occupied():
                raise GatewayRuntimeError("runtime_owner_unknown")
            self.owner_path.unlink(missing_ok=True)
        elif self._gateway_pid_is_live():
            raise GatewayRuntimeError("runtime_owner_unknown")
        elif self._port_is_occupied():
            raise GatewayRuntimeError("runtime_port_occupied")
        return self._start(run_id, runtime_epoch)

    def stop(self, run_id: str, runtime_epoch: str) -> None:
        """Stop only the exact child recorded for the active or cleanup-pending Run."""

        owner = self._read_owner()
        if owner is None:
            if self._gateway_pid_is_live() or self._port_is_occupied():
                raise GatewayRuntimeError("runtime_owner_unknown")
            return
        if not self._owner_matches(owner, run_id, runtime_epoch):
            if (
                self._owner_identity_matches(owner, run_id, runtime_epoch)
                and not self._owner_process_is_live(owner)
                and not self._gateway_pid_is_live()
                and not self._port_is_occupied()
            ):
                self.owner_path.unlink(missing_ok=True)
                return
            raise GatewayRuntimeError("runtime_owner_unknown")
        self._stop_verified(owner)

    def config_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name, path in (
            ("gateway-config", self.config.hermes_home / "config.yaml"),
            ("gateway-env", self.config.hermes_home / ".env"),
        ):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes() if path.exists() else b"")
            digest.update(b"\0")
        return digest.hexdigest()

    def _start(self, run_id: str, runtime_epoch: str) -> dict[str, Any]:
        if self._gateway_pid_is_live() or self._port_is_occupied():
            raise GatewayRuntimeError("runtime_port_occupied")
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.config.hermes_home.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ)
        environment["HERMES_HOME"] = str(self.config.hermes_home.resolve())
        log = self.log_path.open("a", encoding="utf-8")
        try:
            process = self._spawn(
                [
                    self.config.hermes_bin,
                    "gateway",
                    "run",
                    "--external-supervisor",
                    "--accept-hooks",
                ],
                cwd=str(self.config.root),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log.close()
        pid = int(getattr(process, "pid", 0) or 0)
        if pid <= 0:
            raise GatewayRuntimeError("runtime_gateway_unavailable")
        process_start_marker = self._process_start_marker(pid)
        owner = self._wait_for_owned_start(
            pid,
            run_id,
            runtime_epoch,
            process_start_marker,
        )
        if owner is None:
            self._terminate_if_same_process(pid, process_start_marker)
            raise GatewayRuntimeError("runtime_gateway_unavailable")
        try:
            self._write_owner(owner)
        except Exception as exc:
            self._terminate_if_same_process(pid, process_start_marker)
            raise GatewayRuntimeError("runtime_owner_record_unavailable") from exc
        return owner

    def _wait_for_owned_start(
        self,
        spawned_pid: int,
        run_id: str,
        runtime_epoch: str,
        process_start_marker: str,
    ) -> dict[str, Any] | None:
        if not process_start_marker:
            return None
        deadline = self._monotonic() + self._start_timeout
        while self._monotonic() <= deadline:
            record = self._read_gateway_pid()
            if (
                record is not None
                and int(record.get("pid", 0) or 0) == spawned_pid
                and record.get("kind") == "hermes-gateway"
                and self._same_path(record.get("hermes_home"), self.config.hermes_home)
                and self._process_alive(spawned_pid)
            ):
                start_marker = self._process_start_marker(spawned_pid)
                if start_marker == process_start_marker and self._wait_until_healthy():
                    return {
                        "version": 1,
                        "root": str(self.config.root.resolve()),
                        "hermes_home": str(self.config.hermes_home.resolve()),
                        "run_id": run_id,
                        "runtime_epoch": runtime_epoch,
                        "pid": spawned_pid,
                        "gateway_start_time": record.get("start_time"),
                        "process_start_marker": start_marker,
                        "config_fingerprint": self.config_fingerprint(),
                    }
            self._sleep(0.1)
        return None

    def _terminate_if_same_process(self, pid: int, process_start_marker: str) -> None:
        """Terminate a failed child only while its original process marker remains."""

        if (
            process_start_marker
            and self._process_alive(pid)
            and self._process_start_marker(pid) == process_start_marker
        ):
            self._terminate(pid)

    def _wait_until_healthy(self) -> bool:
        deadline = self._monotonic() + self._start_timeout
        client = HermesClient(self.config)
        while self._monotonic() <= deadline:
            status, _body = client.get_json("/health")
            if status == 200:
                return True
            self._sleep(0.1)
        return False

    def _owner_matches(self, owner: dict[str, Any], run_id: str, runtime_epoch: str) -> bool:
        if (
            owner.get("run_id") != run_id
            or owner.get("runtime_epoch") != runtime_epoch
            or owner.get("config_fingerprint") != self.config_fingerprint()
            or not self._owner_process_matches(owner)
        ):
            return False
        return True

    def _owner_process_matches(self, owner: dict[str, Any]) -> bool:
        try:
            pid = int(owner["pid"])
        except (KeyError, TypeError, ValueError):
            return False
        if (
            owner.get("version") != 1
            or not self._same_path(owner.get("root"), self.config.root)
            or not self._same_path(owner.get("hermes_home"), self.config.hermes_home)
            or not self._process_alive(pid)
            or owner.get("process_start_marker") != self._process_start_marker(pid)
        ):
            return False
        gateway_pid = self._read_gateway_pid()
        return bool(
            gateway_pid
            and gateway_pid.get("kind") == "hermes-gateway"
            and int(gateway_pid.get("pid", 0) or 0) == pid
            and gateway_pid.get("start_time") == owner.get("gateway_start_time")
            and self._same_path(gateway_pid.get("hermes_home"), self.config.hermes_home)
        )

    def _owner_identity_matches(self, owner: dict[str, Any], run_id: str, runtime_epoch: str) -> bool:
        try:
            int(owner["pid"])
        except (KeyError, TypeError, ValueError):
            return False
        return bool(
            owner.get("version") == 1
            and owner.get("run_id") == run_id
            and owner.get("runtime_epoch") == runtime_epoch
            and self._same_path(owner.get("root"), self.config.root)
            and self._same_path(owner.get("hermes_home"), self.config.hermes_home)
        )

    def _owner_process_is_live(self, owner: dict[str, Any]) -> bool:
        try:
            return self._process_alive(int(owner["pid"]))
        except (KeyError, TypeError, ValueError):
            return False

    def _stop_verified(self, owner: dict[str, Any]) -> None:
        pid = int(owner["pid"])
        if not self._process_alive(pid):
            self.owner_path.unlink(missing_ok=True)
            self._mark_owned_gateway_state_exited(pid)
            return
        if owner.get("process_start_marker") != self._process_start_marker(pid):
            raise GatewayRuntimeError("runtime_owner_unknown")
        self._terminate(pid)
        deadline = self._monotonic() + self._start_timeout
        while self._process_alive(pid) and self._monotonic() <= deadline:
            self._sleep(0.1)
        if self._process_alive(pid):
            if self._process_start_marker(pid) != owner.get("process_start_marker"):
                raise GatewayRuntimeError("runtime_owner_unknown")
            self._kill(pid)
            kill_deadline = self._monotonic() + min(self._start_timeout, 2.0)
            while self._process_alive(pid) and self._monotonic() <= kill_deadline:
                self._sleep(0.1)
        if self._process_alive(pid):
            raise GatewayRuntimeError("runtime_gateway_stop_failed")
        self.owner_path.unlink(missing_ok=True)
        self._mark_owned_gateway_state_exited(pid)

    def _mark_owned_gateway_state_exited(self, pid: int) -> None:
        """Normalize Hermes' owned state file after the exact child has stopped."""

        path = self.config.hermes_home / "gateway_state.json"
        if not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(state, dict):
            return
        if (
            state.get("kind") != "hermes-gateway"
            or state.get("hermes_home")
            != str(self.config.hermes_home.resolve())
            or int(state.get("pid", 0) or 0) != pid
        ):
            return
        state["gateway_state"] = "exited"
        state["active_agents"] = 0
        state["exit_reason"] = "chronicle_cleanup"
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError:
            temporary.unlink(missing_ok=True)

    def _read_owner(self) -> dict[str, Any] | None:
        return self._read_json(self.owner_path)

    def _read_gateway_pid(self) -> dict[str, Any] | None:
        return self._read_json(self.pid_path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _write_owner(self, owner: dict[str, Any]) -> None:
        self.owner_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.owner_path.with_name(f".{self.owner_path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(owner, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            os.replace(temporary, self.owner_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _process_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            result = subprocess.run(
                ["ps", "-o", "state=", "-p", str(pid)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip().startswith("Z"):
                return False
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _process_start_marker(pid: int) -> str:
        try:
            result = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else ""

    @staticmethod
    def _terminate(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise GatewayRuntimeError("runtime_gateway_stop_failed") from exc

    @staticmethod
    def _kill(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise GatewayRuntimeError("runtime_gateway_stop_failed") from exc

    def _gateway_pid_is_live(self) -> bool:
        record = self._read_gateway_pid()
        if record is None or record.get("kind") != "hermes-gateway":
            return False
        try:
            pid = int(record.get("pid", 0))
        except (TypeError, ValueError):
            return False
        return self._process_alive(pid)

    def _port_is_occupied(self) -> bool:
        parsed = urlparse(self.config.hermes_base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            return False

    @staticmethod
    def _same_path(value: Any, expected: Path) -> bool:
        if not isinstance(value, str) or not value:
            return False
        return Path(value).expanduser().resolve(strict=False) == expected.expanduser().resolve(strict=False)

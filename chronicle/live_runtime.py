from __future__ import annotations

import threading
from typing import Any, Callable

from .config import AppConfig
from .crisis_runtime import CrisisRunConflict, CrisisRunEngine, CrisisRunError, RunMode
from .db import ChronicleDB
from .gateway import GatewayController, GatewayRuntimeError
from .hermes import cleanup_crisis_runtime, load_crisis_profile_records, materialize_crisis_profiles
from .world import token_hash


class LiveRuntimeManager:
    """The small product runtime: one active Run and one replaceable private Gateway child."""

    def __init__(
        self,
        config: AppConfig,
        *,
        controller: GatewayController | None = None,
        engine_factory: Callable[[AppConfig], CrisisRunEngine] = CrisisRunEngine,
    ):
        self.config = config
        self.controller = controller or GatewayController(config)
        self._engine_factory = engine_factory
        self._lock = threading.RLock()

    def create(self, mode: RunMode | str) -> dict[str, Any]:
        with self._lock:
            db = ChronicleDB(self.config.database_path)
            for sealed in db.worldlines(status="SEALED"):
                if (
                    sealed.get("kind") == "CRISIS"
                    and sealed.get("runtime_mode") == "live"
                    and sealed.get("runtime_phase") == "CLEANUP_PENDING"
                    and sealed.get("runtime_error_code")
                ):
                    cleaned = self._cleanup(str(sealed["id"]))
                    if cleaned.get("runtime_error_code") in {
                        "runtime_owner_unknown",
                        "runtime_port_occupied",
                        "runtime_gateway_stop_failed",
                    }:
                        raise CrisisRunConflict(
                            "上一局的本地主体尚未安全收束，暂不能新开一局。",
                            code="runtime_cleanup_pending",
                            state="CLEANUP_PENDING",
                        )
            engine = self._engine()
            created = engine.create(mode, runtime_mode="live")
            return self._bootstrap(engine, str(created["run"]["id"]))

    def reconcile_active(self) -> dict[str, Any] | None:
        with self._lock:
            db = ChronicleDB(self.config.database_path)
            active = db.active_run()
            if active is not None:
                return self.reconcile(str(active["id"]))
            for sealed in db.worldlines(status="SEALED"):
                if (
                    sealed.get("kind") == "CRISIS"
                    and sealed.get("runtime_mode") == "live"
                    and sealed.get("runtime_phase") == "CLEANUP_PENDING"
                    and sealed.get("runtime_error_code")
                ):
                    self._cleanup(str(sealed["id"]))
            return None

    def reconcile(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            engine = self._engine()
            run = engine.db.worldline(run_id)
            if run is None or run["kind"] != "CRISIS":
                raise CrisisRunError("Run not found")
            if run["runtime_mode"] != "live":
                return engine.run_summary(run_id)
            if run["status"] == "SEALED":
                return self._cleanup(run_id)
            if run.get("runtime_phase") == "SEALING":
                return self._finish_sealing(engine, run_id)
            if run.get("runtime_phase") == "READY":
                return self._reconcile_ready(engine, run_id)
            return self._bootstrap(engine, run_id)

    def retry(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            engine = self._engine()
            run = engine.db.worldline(run_id)
            if run is None or run["kind"] != "CRISIS":
                raise CrisisRunError("Run not found")
            if run["runtime_mode"] != "live":
                return engine.run_summary(run_id)
            if run["status"] == "SEALED":
                return self._cleanup(run_id)
            if run["status"] != "ACTIVE":
                raise CrisisRunError("Run is not active")
            if run.get("runtime_phase") == "SEALING":
                return self._finish_sealing(engine, run_id)
            if run.get("runtime_phase") not in {"BOOTSTRAPPING", "RECONCILING", "FAILED"}:
                return engine.run_summary(run_id)
            if self._has_unrecoverable_wake(engine, run_id):
                return engine.run_summary(run_id)
            self._retry_safe_initial_orients(engine, run_id)
            engine.db.set_crisis_runtime_state(run_id, "RECONCILING")
            return self._bootstrap(engine, run_id)

    def advance_one(self, run_id: str) -> bool:
        with self._lock:
            engine = self._engine()
            try:
                return engine.advance_one(run_id)
            except CrisisRunError:
                run = engine.db.worldline(run_id)
                if run and run.get("runtime_mode") == "live" and run["status"] == "ACTIVE":
                    engine.mark_live_runtime_failed(run_id, "runtime_wake_failed")
                raise

    def submit_human_decision(self, run_id: str, text: str) -> dict[str, Any]:
        """Keep a live Human decision in the same mutation gate as continue and seal."""

        with self._lock:
            engine = self._engine()
            try:
                return engine.submit_human_decision(run_id, text)
            except CrisisRunConflict:
                raise
            except CrisisRunError:
                run = engine.db.worldline(run_id)
                if run and run.get("runtime_mode") == "live" and run["status"] == "ACTIVE":
                    engine.mark_live_runtime_failed(run_id, "runtime_decision_failed")
                raise

    def seal(self, run_id: str, reason: str = "user_exit") -> dict[str, Any]:
        with self._lock:
            engine = self._engine()
            sealed = engine.seal(run_id, reason)
            if sealed["runtime_mode"] == "live":
                return self._cleanup(run_id)
            return sealed

    def _bootstrap(self, engine: CrisisRunEngine, run_id: str) -> dict[str, Any]:
        run = engine.db.worldline(run_id)
        if run is None:
            raise CrisisRunError("Run not found")
        try:
            engine.db.set_crisis_runtime_state(run_id, "BOOTSTRAPPING")
            self._mark_unresolved_wakes(engine, run_id)
            if self._has_unrecoverable_wake(engine, run_id):
                engine.mark_live_runtime_failed(run_id, "runtime_wake_unresolved")
                return engine.run_summary(run_id)
            specs = engine.live_profile_specs(run_id)
            records = materialize_crisis_profiles(
                self.config,
                run_id,
                specs,
                crisis_id=str(run["crisis_id"]),
                runtime_epoch=str(run["runtime_epoch"]),
            )
            self.controller.ensure(run_id, str(run["runtime_epoch"]))
            engine.activate_live_runtime(run_id, records)
            if not engine.initial_orient_completed(run_id):
                engine.advance_one(run_id, allow_runtime_bootstrap=True)
            if engine.initial_orient_completed(run_id):
                engine.mark_live_runtime_ready(run_id)
            else:
                engine.mark_live_runtime_failed(run_id, "runtime_orient_incomplete")
        except GatewayRuntimeError as exc:
            engine.mark_live_runtime_failed(run_id, exc.code)
        except CrisisRunError:
            engine.mark_live_runtime_failed(run_id, "runtime_orient_failed")
        except Exception:
            engine.mark_live_runtime_failed(run_id, "runtime_bootstrap_failed")
        return engine.run_summary(run_id)

    def _reconcile_ready(self, engine: CrisisRunEngine, run_id: str) -> dict[str, Any]:
        run = engine.db.worldline(run_id)
        if run is None:
            raise CrisisRunError("Run not found")
        if self._mark_unresolved_wakes(engine, run_id):
            return engine.mark_live_runtime_failed(run_id, "runtime_wake_unresolved")
        try:
            engine.db.set_crisis_runtime_state(run_id, "RECONCILING")
            self.controller.ensure(run_id, str(run["runtime_epoch"]))
            specs = engine.live_profile_specs(run_id)
            bindings = {
                str(binding["role"]): binding
                for binding in engine.db.agent_bindings(run_id)
                if binding["status"] == "ACTIVE"
            }
            expected_actors = {str(spec["id"]) for spec in specs}
            if set(bindings) != expected_actors or any(
                str(bindings[actor_id]["profile_identity"]) != str(spec["profile"])
                or str(bindings[actor_id]["ownership_marker"]) != str(spec["ownership_marker"])
                for spec in specs
                for actor_id in [str(spec["id"])]
            ):
                return engine.mark_live_runtime_failed(run_id, "runtime_binding_mismatch")
            records = load_crisis_profile_records(
                self.config,
                run_id,
                specs,
                crisis_id=str(run["crisis_id"]),
                runtime_epoch=str(run["runtime_epoch"]),
            )
            if any(
                actor_id not in records
                or token_hash(str(records[actor_id].get("world_token", "")))
                != str(bindings[actor_id]["token_hash"])
                for actor_id in expected_actors
            ):
                return engine.mark_live_runtime_failed(run_id, "runtime_binding_mismatch")
            return engine.db.set_crisis_runtime_state(run_id, "READY")
        except GatewayRuntimeError as exc:
            return engine.mark_live_runtime_failed(run_id, exc.code)
        except Exception:
            return engine.mark_live_runtime_failed(run_id, "runtime_reconcile_failed")

    def _finish_sealing(self, engine: CrisisRunEngine, run_id: str) -> dict[str, Any]:
        self._mark_unresolved_wakes(engine, run_id)
        if any(
            wake["status"] in {"RUNNING", "STAGED"}
            for wake in engine.db.nonterminal_crisis_wakes(run_id)
        ):
            return engine.run_summary(run_id)
        try:
            engine.seal(run_id)
        except CrisisRunConflict:
            return engine.run_summary(run_id)
        return self._cleanup(run_id)

    @staticmethod
    def _mark_unresolved_wakes(engine: CrisisRunEngine, run_id: str) -> bool:
        changed = False
        for wake in engine.db.nonterminal_crisis_wakes(run_id):
            if wake["status"] not in {"RUNNING", "STAGED"}:
                continue
            engine.db.update_crisis_wake(
                wake["id"],
                status="FAILED",
                error={"code": "runtime_wake_unresolved", "wake_status": wake["status"]},
            )
            changed = True
        return changed

    @staticmethod
    def _has_unrecoverable_wake(engine: CrisisRunEngine, run_id: str) -> bool:
        for wake in engine.db.crisis_wakes(run_id):
            if (
                wake["status"] != "FAILED"
                or wake.get("error", {}).get("code") != "runtime_wake_unresolved"
            ):
                continue
            if wake["wake_type"] != "ORIENT" or engine.db.crisis_wake_operations(wake["id"]):
                return True
        return False

    def _cleanup(self, run_id: str) -> dict[str, Any]:
        engine = self._engine()
        run = engine.db.worldline(run_id)
        if run is None:
            raise CrisisRunError("Run not found")
        if run["status"] != "SEALED" or run.get("runtime_phase") != "CLEANUP_PENDING":
            return engine.run_summary(run_id)
        if not run.get("runtime_error_code"):
            return engine.run_summary(run_id)
        try:
            self.controller.stop(run_id, str(run["runtime_epoch"]))
            agent_lifetimes = [
                lifetime
                for lifetime in engine.db.worldline_lifetimes(run_id)
                if lifetime["controller"] == "AGENT" and lifetime["profile_name"]
            ]
            cleanup_crisis_runtime(
                self.config,
                run_id,
                [str(lifetime["profile_name"]) for lifetime in agent_lifetimes],
                server_names=[
                    str(lifetime["profile_metadata"].get("world_server_name", ""))
                    for lifetime in agent_lifetimes
                ],
            )
            return engine.db.set_crisis_runtime_state(run_id, "CLEANUP_PENDING")
        except GatewayRuntimeError as exc:
            return engine.db.set_crisis_runtime_state(
                run_id, "CLEANUP_PENDING", error_code=exc.code
            )
        except Exception:
            return engine.db.set_crisis_runtime_state(
                run_id, "CLEANUP_PENDING", error_code="runtime_cleanup_failed"
            )

    @staticmethod
    def _retry_safe_initial_orients(engine: CrisisRunEngine, run_id: str) -> None:
        for wake in engine.db.crisis_wakes(run_id, tick=0):
            if wake["wake_type"] != "ORIENT" or wake["status"] != "FAILED":
                continue
            if engine.db.crisis_wake_operations(wake["id"]):
                continue
            engine.db.update_crisis_wake(wake["id"], status="QUEUED", error={})

    def _engine(self) -> CrisisRunEngine:
        return self._engine_factory(self.config)

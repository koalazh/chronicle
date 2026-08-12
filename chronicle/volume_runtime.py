from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any

from . import hermes
from .crisis import (
    AgreementStatus,
    AgreementTerm,
    CrisisActivationPreconditionKind,
    CrisisPack,
    CrisisReference,
    OfferAction,
    OfferStatus,
    VolumePack,
)
from .db import content_hash, stable_hash
from .decision_horizon import (
    DecisionHorizonError,
    build_current_course,
    current_course_from_plan,
    normalize_open_dependencies,
)
from .deliberation import (
    DELIBERATION_WORLD_TOOLS,
    DeliberationError,
    normalize_deliberation,
)
from .models import CrisisInstanceStatus, Provenance, WorldlineKind, WorldlineStatus
from .subject_attention import AttentionDecision, evaluate_attention
from .subject_continuity import LifetimeContextBuilder
from .volume_boundary import VolumeBoundaryPolicy
from .world import token_hash

if TYPE_CHECKING:
    from .host import ChronicleHost


class VolumeRuntimeError(ValueError):
    """A user-visible error at the V5 Volume runtime boundary."""


class VolumeRuntimeConflict(VolumeRuntimeError):
    """A V5 Volume operation conflicts with the current global state."""


VOLUME_WORLD_TOOLS = frozenset(
    {
        "communicate",
        "investigate",
        "manage_offer",
        "operate",
        "schedule_revisit",
        "update_plan",
    }
)


class VolumeRuntime:
    """Deterministic V5 runtime for one shared Volume Worldline."""

    def __init__(self, host: ChronicleHost):
        self.host = host
        self.db = host.db
        self.pack = VolumePack.load(host.config.volume_path)

    @property
    def volume_id(self) -> str:
        return self.pack.volume.id

    def create(self, *, runtime_mode: str = "fixture") -> dict[str, Any]:
        """Create the one V5 Volume Worldline and its persistent Lifetime rows."""

        if runtime_mode not in {"fixture", "live"}:
            raise VolumeRuntimeError("runtime_mode must be fixture or live")
        if self.db.active_volume_worldline() is not None:
            raise VolumeRuntimeConflict("an active Volume Worldline already exists")

        worldline_id = f"worldline-{uuid.uuid4().hex[:16]}"
        content_version = 1
        volume_content_hash = self._volume_content_hash()
        runtime_epoch = f"volume-{uuid.uuid4().hex[:12]}"
        initial_projection = self._initial_projection(worldline_id)
        created = self._event(
            worldline_id,
            0,
            "WORLDLINE_CREATED",
            {
                "volume_id": self.volume_id,
                "volume_content_version": content_version,
                "volume_content_hash": volume_content_hash,
                "worldline_phase": "READY",
                "runtime_mode": runtime_mode,
                "base_projection": initial_projection,
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            event_id=f"{worldline_id}:created",
            runtime_epoch=runtime_epoch,
        )
        initialized = self._event(
            worldline_id,
            0,
            "WORLD_INITIALIZED",
            {
                "volume_id": self.volume_id,
                "lifetime_ids": sorted(self.pack.lifetimes),
                "shared_location_ids": [location.id for location in self.pack.world.locations],
                "shared_entity_ids": [entity.id for entity in self.pack.world.entities],
                "institutional_state": dict(self.pack.world.institutional_state),
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[created["id"]],
            event_id=f"{worldline_id}:world-initialized",
            runtime_epoch=runtime_epoch,
        )
        events = [created, initialized]
        lifetime_values: list[dict[str, Any]] = []
        for lifetime_id in sorted(self.pack.lifetimes):
            definition = self.pack.lifetimes[lifetime_id]
            profile = hermes.lifetime_profile_name(worldline_id, lifetime_id)
            ownership_marker = hermes.stable_lifetime_profile_marker(
                worldline_id, lifetime_id, profile
            )
            world_server_name = hermes.lifetime_world_server_name(worldline_id, lifetime_id)
            genesis = {
                "worldline_id": worldline_id,
                "volume_id": self.volume_id,
                "lifetime_id": lifetime_id,
                "display_name": definition.display_name,
                "genesis_context": definition.genesis_context,
                "starting_location": self.pack.world.resolve_location(definition.starting_location),
                "initial_knowledge": definition.initial_knowledge,
                "initial_beliefs": definition.initial_beliefs,
                "initial_resources": definition.initial_resources,
                "stable_authority": definition.stable_authority,
            }
            lifetime_db_id = self._lifetime_db_id(worldline_id, lifetime_id)
            lifetime_values.append(
                {
                    "id": lifetime_db_id,
                    "worldline_id": worldline_id,
                    "seat": lifetime_id,
                    "controller": "AGENT",
                    "lifetime_kind": "ACTOR",
                    "profile_state": "ACTIVE",
                    "profile_name": profile,
                    "profile_metadata": {
                        "profile_scope": "LIFETIME",
                        "ownership_marker": ownership_marker,
                        "world_server_name": world_server_name,
                        "volume_id": self.volume_id,
                        "content_version": content_version,
                        "content_hash": volume_content_hash,
                        "runtime_epoch": runtime_epoch,
                        "runtime_mode": runtime_mode,
                    },
                    "parent_canon_lifetime": f"{self.volume_id}:{lifetime_id}",
                    "genesis_hash": stable_hash(genesis),
                    "memory_text": "",
                    "memory_hash": content_hash(""),
                    "knowledge": list(definition.initial_knowledge),
                    "beliefs": dict(definition.initial_beliefs),
                    "authority": list(definition.stable_authority),
                    "resources": dict(definition.initial_resources),
                    "plan": [],
                    "commitments": [],
                    "revisits": [],
                    "last_perspective": {},
                    "genesis_context": dict(definition.genesis_context),
                }
            )
            events.append(
                self._event(
                    worldline_id,
                    0,
                    "LIFETIME_GENESIS_ESTABLISHED",
                    {
                        "lifetime_id": lifetime_id,
                        "display_name": definition.display_name,
                        "profile_name": profile,
                        "genesis_hash": lifetime_values[-1]["genesis_hash"],
                        "starting_location": self.pack.world.resolve_location(
                            definition.starting_location
                        ),
                    },
                    seat_id=lifetime_id,
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[initialized["id"]],
                    event_id=f"{worldline_id}:lifetime:{lifetime_id}:genesis",
                    runtime_epoch=runtime_epoch,
                )
            )
        for field_event in initial_projection["field_events"]:
            events.append(
                self._event(
                    worldline_id,
                    0,
                    "FIELD_EVENT_SCHEDULED",
                    field_event,
                    provenance=Provenance.HISTORICAL.value,
                    causal_parent_ids=[initialized["id"]],
                    event_id=f"{worldline_id}:field:{field_event['id']}:scheduled",
                    runtime_epoch=runtime_epoch,
                )
            )
        envelope_instances = []
        for reference in self.pack.volume.crises:
            pack = self.pack.pack(reference.id)
            events.append(
                self._event(
                    worldline_id,
                    0,
                    "CRISIS_ENVELOPE_REGISTERED",
                    {
                        "crisis_id": reference.id,
                        "earliest_activation_tick": reference.earliest_activation_tick,
                        "activation_preconditions": [
                            item.model_dump(mode="json")
                            for item in reference.activation_preconditions
                        ],
                        "participants": list(reference.participants or pack.participant_ids),
                        "local_horizon": reference.local_horizon,
                    },
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[initialized["id"]],
                    event_id=f"{worldline_id}:envelope:{reference.id}:registered",
                    runtime_epoch=runtime_epoch,
                )
            )
            envelope_instances.append(
                self._envelope_instance(worldline_id, reference, pack, runtime_epoch)
            )

        values = {
            "id": worldline_id,
            "scenario_id": self.volume_id,
            "kind": WorldlineKind.VOLUME.value,
            "status": WorldlineStatus.ACTIVE.value,
            "current_tick": 0,
            "runtime_epoch": runtime_epoch,
            "runtime_mode": runtime_mode,
            "volume_id": self.volume_id,
            "volume_content_version": content_version,
            "volume_content_hash": volume_content_hash,
            "worldline_phase": "READY",
            "runtime_phase": "BOOTSTRAPPING" if runtime_mode == "live" else "READY",
            "boundary_policy_id": "volume-global-clock",
            "safety_horizon_tick": self._volume_horizon(),
            "human_lifetime_id": "",
        }
        profile_records: dict[str, dict[str, Any]] = {}
        if runtime_mode == "live":
            profile_inputs = [
                {
                    **lifetime,
                    "id": lifetime["seat"],
                    "lifetime_id": lifetime["seat"],
                }
                for lifetime in lifetime_values
            ]
            try:
                profile_records = hermes.materialize_lifetime_profiles(
                    self.host.config,
                    worldline_id,
                    profile_inputs,
                    volume_id=self.volume_id,
                    content_version=content_version,
                    content_hash=volume_content_hash,
                    runtime_epoch=runtime_epoch,
                )
            except RuntimeError as exc:
                raise hermes.HermesRuntimeError(str(exc)) from exc
        try:
            worldline = self.db.create_worldline_bundle(
                values,
                events,
                lifetime_values,
                initial_projection,
                instance_creates=envelope_instances,
            )
            bindings = []
            for lifetime in lifetime_values:
                metadata = lifetime["profile_metadata"]
                profile_record = profile_records.get(lifetime["seat"], {})
                world_token = str(profile_record.get("world_token", ""))
                bindings.append(
                    self.db.create_agent_binding(
                        {
                            "worldline_id": worldline_id,
                            "actor_id": lifetime["seat"],
                            "lifetime_id": lifetime["id"],
                            "binding_scope": "VOLUME",
                            "volume_id": self.volume_id,
                            "content_version": content_version,
                            "content_hash": volume_content_hash,
                            "genesis_hash": lifetime["genesis_hash"],
                            "runtime_epoch": runtime_epoch,
                            "profile_name": lifetime["profile_name"],
                            "ownership_marker": metadata["ownership_marker"],
                            "distribution_version": "chronicle-actor-v5",
                            "token_hash": token_hash(world_token) if world_token else "",
                        }
                    )
                )
        except sqlite3.IntegrityError as exc:
            if profile_records:
                hermes.cleanup_volume_runtime(
                    self.host.config,
                    worldline_id,
                    [record["profile"] for record in profile_records.values()],
                    server_names=[record["world_server_name"] for record in profile_records.values()],
                )
            raise VolumeRuntimeConflict("an active Volume Worldline already exists") from exc
        return {
            "worldline": worldline,
            "lifetimes": self.db.worldline_lifetimes(worldline_id),
            "bindings": bindings,
            "projection": initial_projection,
            "profile_records": profile_records,
        }

    def reconcile_live_runtime(self, worldline_id: str) -> dict[str, Any]:
        """Reconcile a live Volume without repairing identity or pending work."""

        from .gateway import GatewayController, GatewayRuntimeError

        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        if row["runtime_mode"] != "live":
            return row
        if row["status"] == WorldlineStatus.SEALED.value:
            if row.get("runtime_phase") == "CLEANUP_PENDING":
                self._cleanup_profiles_after_seal(row)
            return self.db.worldline(worldline_id) or row
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise VolumeRuntimeConflict("Volume Worldline is not active")

        try:
            active_volumes = [
                item
                for item in self.db.worldlines(status=WorldlineStatus.ACTIVE.value)
                if item.get("kind") == WorldlineKind.VOLUME.value
            ]
            if len(active_volumes) != 1 or active_volumes[0]["id"] != worldline_id:
                raise VolumeRuntimeError("V5 Volume Worldline owner is not unique")
            lifetimes = self.db.worldline_lifetimes(worldline_id)
            expected_lifetimes = set(self.pack.lifetimes)
            if {str(item["seat"]) for item in lifetimes} != expected_lifetimes:
                raise VolumeRuntimeError("V5 Lifetime binding set is incomplete")
            bindings = self.db.agent_bindings(worldline_id)
            if {str(item["role"]) for item in bindings} != expected_lifetimes:
                raise VolumeRuntimeError("V5 agent binding set is incomplete")
            if any(str(item.get("status")) != "ACTIVE" for item in bindings):
                raise VolumeRuntimeError("V5 agent binding is not active")
            profile_records = hermes.load_lifetime_profile_records(
                self.host.config,
                worldline_id,
                lifetimes,
                volume_id=str(row.get("volume_id") or self.volume_id),
                content_version=int(row.get("volume_content_version") or 0),
                content_hash=str(row.get("volume_content_hash") or ""),
                runtime_epoch=str(row.get("runtime_epoch") or ""),
            )
            records_by_seat = {
                str(record["lifetime_id"]): record for record in profile_records.values()
            }
            for binding in bindings:
                seat = str(binding["role"])
                lifetime = self.db.worldline_lifetime(worldline_id, seat)
                record = records_by_seat.get(seat)
                if lifetime is None or record is None:
                    raise VolumeRuntimeError(f"V5 binding is missing for {seat}")
                if (
                    str(binding["profile_identity"]) != str(record["profile"])
                    or str(lifetime.get("profile_name")) != str(record["profile"])
                    or str(binding["ownership_marker"]) != str(record["ownership_marker"])
                    or str(binding["token_hash"]) != token_hash(str(record["world_token"]))
                ):
                    raise VolumeRuntimeError(f"V5 binding identity is inconsistent for {seat}")
            self._validate_pending_reconcile(worldline_id)
            GatewayController(self.host.config).ensure(
                worldline_id, str(row["runtime_epoch"])
            )
        except (GatewayRuntimeError, hermes.HermesRuntimeError, VolumeRuntimeError, RuntimeError) as exc:
            self.db.set_volume_runtime_state(
                worldline_id, "FAILED", error_code="volume_reconcile_failed"
            )
            if isinstance(exc, VolumeRuntimeError):
                raise
            raise VolumeRuntimeError(f"V5 Volume reconcile failed: {exc}") from exc
        return self.db.set_volume_runtime_state(worldline_id, "READY")

    def _validate_pending_reconcile(self, worldline_id: str) -> None:
        row = self.db.worldline(worldline_id)
        if row is None:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        snapshot = self.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        pending = snapshot["projection"].get("pending_moment")
        if pending:
            if pending.get("phase") != "FROZEN":
                raise VolumeRuntimeError("Pending Logical Moment is not recoverable")
            for wake_id in pending.get("wake_ids", []):
                wake = self.db.crisis_wake(str(wake_id))
                if wake is None or wake["status"] not in {
                    "QUEUED",
                    "WAITING_HUMAN",
                    "STAGED",
                }:
                    raise VolumeRuntimeError("Pending Logical Moment contains an invalid Wake")
                operations = self.db.crisis_wake_operations(str(wake_id))
                if any(item["payload"].get("moment_id") != pending["id"] for item in operations):
                    raise VolumeRuntimeError("Wake operation belongs to another Logical Moment")
                if wake["status"] == "STAGED" and len(operations) != 1:
                    raise VolumeRuntimeError("staged Wake operation is not recoverable")
                if wake["status"] != "STAGED" and operations:
                    raise VolumeRuntimeError("unstaged Wake has a persisted operation")
        for wake in self.db.subject_wakes(worldline_id):
            if wake["status"] == "RUNNING":
                raise VolumeRuntimeError("a live Wake was interrupted while running")
            if wake["status"] == "STAGED" and not pending:
                raise VolumeRuntimeError("staged Wake is not attached to a Pending Logical Moment")

    def ensure_live_runtime(self, worldline_id: str) -> dict[str, Any]:
        """Ensure the exact V5 Volume Gateway is ready before live cognition."""
        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        if row["runtime_mode"] != "live":
            return row
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise VolumeRuntimeConflict("Volume Worldline is sealed")
        return self.reconcile_live_runtime(worldline_id)

    def worldline(self, worldline_id: str) -> dict[str, Any]:
        row = self._active_worldline(worldline_id)
        snapshot = self.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        return {
            "worldline": row,
            "lifetimes": self.db.worldline_lifetimes(worldline_id),
            "crisis_instances": self.db.crisis_instances(worldline_id),
            "projection": snapshot["projection"],
        }

    def boundary(self, worldline_id: str) -> dict[str, Any]:
        """Evaluate the Volume boundary without turning it into an auto-ending tick."""

        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        snapshot = self.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        next_tick = self.next_tick(worldline_id) if row["status"] == WorldlineStatus.ACTIVE.value else None
        due_wakes = [
            wake
            for wake in self.db.subject_wakes(worldline_id, tick=int(row["current_tick"]))
            if wake["status"] in {"QUEUED", "WAITING_HUMAN", "STAGED"}
        ]
        required_field_event_ids = tuple(
            str(item.get("id"))
            for item in self.pack.world.historical_field
            if str(item.get("id", "")) == "north-south-recognition-bridge"
        )
        decision = VolumeBoundaryPolicy().evaluate(
            current_tick=int(row["current_tick"]),
            projection=snapshot["projection"],
            events=self.db.worldline_events(worldline_id),
            instances=self.db.crisis_instances(worldline_id),
            due_wakes=due_wakes,
            next_tick=next_tick,
            safety_horizon_tick=row.get("safety_horizon_tick"),
            required_field_event_ids=required_field_event_ids,
        )
        return {"worldline": row, "boundary": decision.as_dict()}

    def seal(self, worldline_id: str, reason: str = "volume_boundary") -> dict[str, Any]:
        """Seal a Volume only after its structural boundary has been reached."""

        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        if row["status"] == WorldlineStatus.SEALED.value:
            self._cleanup_profiles_after_seal(row)
            event = next(
                (
                    item
                    for item in reversed(self.db.worldline_events(worldline_id))
                    if item["event_type"] == "VOLUME_SEALED"
                ),
                None,
            )
            return {"worldline": self.db.worldline(worldline_id), "event": event, "idempotent": True}
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise VolumeRuntimeConflict("Volume Worldline cannot be sealed from its current state")

        boundary = self.boundary(worldline_id)["boundary"]
        if not boundary["ready"]:
            raise VolumeRuntimeConflict(boundary["message"])
        tick = int(row["current_tick"])
        snapshot = self.db.worldline_snapshot(worldline_id, tick)
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        projection = snapshot["projection"]
        projection["volume_state"] = {
            "status": "SEALED",
            "boundary_policy_id": VolumeBoundaryPolicy.id,
            "boundary": boundary,
        }
        events = self.db.worldline_events(worldline_id)
        parent_ids = [str(events[-1]["id"])] if events else []
        event = self._event(
            worldline_id,
            tick,
            "VOLUME_SEALED",
            {
                "volume_id": self.volume_id,
                "boundary_policy_id": VolumeBoundaryPolicy.id,
                "boundary": boundary,
                "reason": reason,
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=parent_ids,
            event_id=f"{worldline_id}:sealed",
            runtime_epoch=row["runtime_epoch"],
        )
        committed = self.db.commit_worldline_seal(
            worldline_id,
            event,
            reason=reason,
            outcome="VOLUME_ARCHIVED",
            snapshot=projection,
            revoke_agent_bindings=True,
            cancel_queued_wakes=True,
            current_tick=tick,
            worldline_phase="ARCHIVED",
        )
        sealed = self.db.worldline(worldline_id) or {}
        self._cleanup_profiles_after_seal(sealed)
        return {"worldline": sealed, "event": committed, "boundary": boundary, "idempotent": False}

    def _cleanup_profiles_after_seal(self, row: dict[str, Any]) -> None:
        if row.get("runtime_mode") != "live":
            return
        from .gateway import GatewayController, GatewayRuntimeError

        try:
            GatewayController(self.host.config).stop(
                str(row["id"]), str(row["runtime_epoch"])
            )
            lifetimes = self.db.worldline_lifetimes(str(row["id"]))
            profiles = [
                str(
                    lifetime.get("profile_name")
                    or hermes.lifetime_profile_name(row["id"], lifetime["seat"])
                )
                for lifetime in lifetimes
            ]
            server_names = [
                hermes.lifetime_world_server_name(row["id"], str(lifetime["seat"]))
                for lifetime in lifetimes
            ]
            hermes.cleanup_volume_runtime(
                self.host.config,
                str(row["id"]),
                profiles,
                server_names=server_names,
            )
        except (GatewayRuntimeError, RuntimeError, OSError) as exc:
            error_code = getattr(exc, "code", "volume_cleanup_failed")
            self.db.set_volume_runtime_state(
                str(row["id"]), "CLEANUP_PENDING", error_code=error_code
            )
            raise VolumeRuntimeError(f"V5 Volume cleanup failed: {error_code}") from exc

    def lifetime_context(
        self, worldline_id: str, lifetime_id: str, *, wake_id: str | None = None
    ) -> dict[str, Any]:
        row = self._active_worldline(worldline_id)
        snapshot = self.db.worldline_snapshot(worldline_id, int(row["current_tick"]))
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        wake = self.db.crisis_wake(wake_id) if wake_id else None
        return LifetimeContextBuilder(self.db, self.pack).build(
            worldline_id,
            lifetime_id,
            snapshot["projection"],
            wake=wake,
        )

    def causal_trace(self, worldline_id: str, event_id: str) -> dict[str, Any]:
        self._active_worldline(worldline_id)
        return LifetimeContextBuilder(self.db, self.pack).causal_trace(worldline_id, event_id)

    def _envelope_instance(
        self,
        worldline_id: str,
        reference: CrisisReference,
        pack: CrisisPack,
        runtime_epoch: str,
    ) -> dict[str, Any]:
        return {
            "id": self._instance_db_id(worldline_id, reference.id),
            "worldline_id": worldline_id,
            "crisis_id": reference.id,
            "content_version": pack.crisis.version,
            "content_hash": pack.content_hash,
            "status": CrisisInstanceStatus.DORMANT.value,
            "phase": "DORMANT",
            "activation_tick": 0,
            "local_origin_tick": 0,
            "resolution_contract_id": pack.crisis.resolution_contract.id,
            "resolution_contract_version": pack.crisis.resolution_contract.version,
            "resolution_seed": stable_hash(
                {"worldline_id": worldline_id, "crisis_id": reference.id, "envelope": True}
            )[:32],
            "outcome": {},
            "runtime_epoch": runtime_epoch,
        }

    @staticmethod
    def _envelope_projection_state(reference: CrisisReference, pack: CrisisPack) -> dict[str, Any]:
        return {
            "crisis_id": reference.id,
            "status": CrisisInstanceStatus.DORMANT.value,
            "phase": "DORMANT",
            "activation_tick": 0,
            "local_origin_tick": 0,
            "participants": list(reference.participants or pack.participant_ids),
            "envelope": {
                "earliest_activation_tick": reference.earliest_activation_tick,
                "activation_preconditions": [
                    item.model_dump(mode="json") for item in reference.activation_preconditions
                ],
                "participants": list(reference.participants or pack.participant_ids),
                "local_horizon": reference.local_horizon,
            },
            "entities": {},
            "message_ids": [],
            "operations": [],
            "investigations": [],
            "offers": [],
            "agreements": [],
            "available_affordances": {},
            "pressures": [],
            "resolution": {"status": "DORMANT"},
            "resolution_reports": [],
            "settlement": {"status": "DORMANT"},
        }

    def _envelope_reference(self, crisis_id: str) -> CrisisReference:
        for reference in self.pack.volume.crises:
            if reference.id == crisis_id:
                return reference
        raise VolumeRuntimeError(f"unknown Crisis envelope: {crisis_id}")

    def _envelope_decision(
        self,
        worldline_id: str,
        crisis_id: str,
        projection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reference = self._envelope_reference(crisis_id)
        row = self.db.worldline(worldline_id)
        if row is None:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        current_tick = int(row["current_tick"])
        if current_tick < reference.earliest_activation_tick:
            return {
                "status": CrisisInstanceStatus.DORMANT.value,
                "reason": "earliest_activation_tick",
            }
        projection = projection or self._snapshot_projection(worldline_id, current_tick)
        for precondition in reference.activation_preconditions:
            if precondition.kind == CrisisActivationPreconditionKind.CRISIS_STATUS:
                source = next(
                    (
                        item
                        for item in self.db.crisis_instances(worldline_id)
                        if item["crisis_id"] == precondition.crisis_id
                    ),
                    None,
                )
                source_status = str(source["status"]) if source else "MISSING"
                if source_status in set(precondition.suppressed_statuses):
                    return {
                        "status": CrisisInstanceStatus.SUPPRESSED.value,
                        "reason": f"precondition {precondition.id}: {source_status}",
                    }
                if source_status not in set(precondition.required_statuses):
                    return {
                        "status": CrisisInstanceStatus.DORMANT.value,
                        "reason": f"precondition {precondition.id}: {source_status}",
                    }
            elif precondition.kind == CrisisActivationPreconditionKind.SHARED_ENTITY_STATE:
                entity = projection.get("entities", {}).get(precondition.entity_id, {})
                state = str(entity.get("state", "MISSING")) if isinstance(entity, dict) else "MISSING"
                if state not in set(precondition.required_states):
                    return {
                        "status": CrisisInstanceStatus.DORMANT.value,
                        "reason": f"precondition {precondition.id}: {state}",
                    }
        return {"status": "ELIGIBLE", "reason": "all preconditions satisfied"}

    def reconcile_crisis_envelopes(self, worldline_id: str) -> dict[str, Any]:
        """Apply deterministic activation/suppression policy to dormant envelopes."""

        row = self._active_worldline(worldline_id)
        projection = self._snapshot_projection(worldline_id, int(row["current_tick"]))
        if projection.get("pending_moment"):
            raise VolumeRuntimeConflict("Crisis envelopes cannot reconcile during a Pending Logical Moment")
        events: list[dict[str, Any]] = []
        for reference in self.pack.volume.crises:
            existing = next(
                (
                    item
                    for item in self.db.crisis_instances(worldline_id)
                    if item["crisis_id"] == reference.id
                ),
                None,
            )
            if existing is None or existing["status"] != CrisisInstanceStatus.DORMANT.value:
                continue
            decision = self._envelope_decision(worldline_id, reference.id, projection)
            if decision["status"] == CrisisInstanceStatus.SUPPRESSED.value:
                result = self._suppress_dormant_crisis(
                    worldline_id, reference.id, str(decision["reason"])
                )
                events.extend(result["events"])
            elif decision["status"] == "ELIGIBLE":
                result = self.activate_crisis(worldline_id, reference.id)
                events.extend(result.get("events", []))
            if events:
                projection = self._snapshot_projection(
                    worldline_id, int(self.db.worldline(worldline_id)["current_tick"])
                )
        return {"worldline": self.db.worldline(worldline_id), "events": events}

    def _suppress_dormant_crisis(
        self, worldline_id: str, crisis_id: str, reason: str
    ) -> dict[str, Any]:
        row = self._active_worldline(worldline_id)
        instance = self._instance_for_crisis(worldline_id, crisis_id)
        if instance["status"] == CrisisInstanceStatus.SUPPRESSED.value:
            return {"worldline": row, "events": [], "idempotent": True}
        if instance["status"] != CrisisInstanceStatus.DORMANT.value:
            raise VolumeRuntimeConflict(f"Crisis Instance {crisis_id} cannot be suppressed from {instance['status']}")
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        state = projection.get("crisis_instances", {}).get(crisis_id)
        if state is None:
            raise VolumeRuntimeError(f"Crisis envelope projection is missing: {crisis_id}")
        state.update(
            {
                "status": CrisisInstanceStatus.SUPPRESSED.value,
                "phase": "SUPPRESSED",
                "suppression_reason": reason,
                "resolution": {"status": "SUPPRESSED", "reason": reason},
                "settlement": {"status": "SUPPRESSED", "reason": reason},
            }
        )
        event = self._event(
            worldline_id,
            tick,
            "CRISIS_SUPPRESSED",
            {"crisis_id": crisis_id, "reason": reason},
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=row["runtime_epoch"],
        )
        projection["last_event_id"] = event["id"]
        self.db.commit_volume_moment(
            worldline_id,
            [event],
            current_tick=tick,
            instance_updates=[
                {
                    "id": instance["id"],
                    "status": CrisisInstanceStatus.SUPPRESSED.value,
                    "phase": "SUPPRESSED",
                    "outcome": {"reason": reason},
                    "suppression_reason": reason,
                }
            ],
            snapshot=projection,
            expected_current_tick=tick,
        )
        return {
            "worldline": self.db.worldline(worldline_id),
            "events": [event],
            "idempotent": False,
        }

    def activate_crisis(self, worldline_id: str, crisis_id: str) -> dict[str, Any]:
        row = self._active_worldline(worldline_id)
        try:
            pack = self.pack.pack(crisis_id)
        except Exception as exc:
            raise VolumeRuntimeError(f"unknown Crisis: {crisis_id}") from exc
        existing = next(
            (
                item
                for item in self.db.crisis_instances(worldline_id)
                if item["crisis_id"] == crisis_id
            ),
            None,
        )
        if existing is not None:
            if existing["status"] == CrisisInstanceStatus.ACTIVE.value:
                return self._activation_response(worldline_id, existing, idempotent=True)
            if existing["status"] == CrisisInstanceStatus.DORMANT.value:
                decision = self._envelope_decision(worldline_id, crisis_id)
                if decision["status"] == CrisisInstanceStatus.SUPPRESSED.value:
                    return self._suppress_dormant_crisis(
                        worldline_id, crisis_id, str(decision["reason"])
                    )
                if decision["status"] != "ELIGIBLE":
                    raise VolumeRuntimeConflict(
                        f"Crisis Instance {crisis_id} is dormant: {decision['reason']}"
                    )
            else:
                raise VolumeRuntimeConflict(
                    f"Crisis Instance {crisis_id} cannot be activated from {existing['status']}"
                )

        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        instance_id = self._instance_db_id(worldline_id, crisis_id)
        state = self._crisis_state(crisis_id, pack, tick)
        projection.setdefault("crisis_instances", {})[crisis_id] = state
        projection["active_crisis_ids"] = sorted(
            set(projection.get("active_crisis_ids", [])) | {crisis_id}
        )
        projection.setdefault("affordances", {})[crisis_id] = state["available_affordances"]

        activated = self._event(
            worldline_id,
            tick,
            "CRISIS_ACTIVATED",
            {
                "instance_id": instance_id,
                "crisis_id": crisis_id,
                "content_version": pack.crisis.version,
                "content_hash": pack.content_hash,
                "activation_tick": tick,
                "local_origin_tick": 0,
                "phase": "OPEN",
                "participants": list(pack.participant_ids),
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            event_id=f"{instance_id}:activated:{tick}",
            runtime_epoch=row["runtime_epoch"],
        )
        checkpoint = self._event(
            worldline_id,
            tick,
            "CRISIS_CHECKPOINT_ENTERED",
            {
                "crisis_id": crisis_id,
                "native_date_window": pack.crisis.checkpoint.native_date_window,
                "fact_assertion_ids": list(pack.crisis.checkpoint.facts),
                "unresolved": list(pack.crisis.checkpoint.unresolved),
            },
            provenance=Provenance.HISTORICAL.value,
            causal_parent_ids=[activated["id"]],
            event_id=f"{instance_id}:checkpoint:{tick}",
            runtime_epoch=row["runtime_epoch"],
        )
        events = [activated, checkpoint]
        for entity in state["entities"].values():
            events.append(
                self._event(
                    worldline_id,
                    tick,
                    "CRISIS_ENTITY_INITIALIZED",
                    {"crisis_id": crisis_id, **entity},
                    provenance=Provenance.SCENARIO_ASSUMPTION.value,
                    causal_parent_ids=[checkpoint["id"]],
                    event_id=f"{instance_id}:entity:{entity['id']}:{tick}",
                    runtime_epoch=row["runtime_epoch"],
                )
            )
        for pressure in state["pressures"]:
            events.append(
                self._event(
                    worldline_id,
                    tick,
                    "CRISIS_PRESSURE_SCHEDULED",
                    {"crisis_id": crisis_id, "pressure": pressure},
                    provenance=pressure["provenance"],
                    causal_parent_ids=[checkpoint["id"]],
                    event_id=f"{instance_id}:pressure:{pressure['id']}:{tick}",
                    runtime_epoch=row["runtime_epoch"],
                )
            )
        for checkpoint_message in pack.crisis.checkpoint.in_transit:
            message = self._checkpoint_message(crisis_id, checkpoint_message, tick)
            state["message_ids"].append(message["id"])
            projection.setdefault("messages", []).append(message)
            dispatch = self._event(
                worldline_id,
                tick,
                "MESSAGE_DISPATCHED",
                message,
                seat_id=message["sender"],
                provenance=Provenance.SCENARIO_ASSUMPTION.value,
                causal_parent_ids=[checkpoint["id"]],
                event_id=f"{instance_id}:message:{checkpoint_message.id}:dispatch",
                runtime_epoch=row["runtime_epoch"],
            )
            message["dispatch_event_id"] = dispatch["id"]
            dispatch["payload"] = message
            events.append(dispatch)

        instance = {
            "id": instance_id,
            "crisis_id": crisis_id,
            "content_version": pack.crisis.version,
            "content_hash": pack.content_hash,
            "status": CrisisInstanceStatus.ACTIVE.value,
            "phase": "OPEN",
            "activation_tick": tick,
            "local_origin_tick": 0,
            "resolution_contract_id": pack.crisis.resolution_contract.id,
            "resolution_contract_version": pack.crisis.resolution_contract.version,
            "resolution_seed": stable_hash(
                {"worldline_id": worldline_id, "crisis_id": crisis_id, "activation_tick": tick}
            )[:32],
            "outcome": {},
        }
        instance_update = {
            "id": instance_id,
            "status": CrisisInstanceStatus.ACTIVE.value,
            "phase": "OPEN",
            "activation_tick": tick,
            "local_origin_tick": 0,
            "resolution_contract_id": pack.crisis.resolution_contract.id,
            "resolution_contract_version": pack.crisis.resolution_contract.version,
            "resolution_seed": instance["resolution_seed"],
        }
        try:
            self.db.commit_volume_moment(
                worldline_id,
                events,
                current_tick=tick,
                instance_creates=[] if existing is not None else [instance],
                instance_updates=[instance_update] if existing is not None else [],
                snapshot=projection,
                expected_current_tick=tick,
            )
        except sqlite3.IntegrityError as exc:
            raise VolumeRuntimeConflict(
                "Crisis activation raced with another Volume moment"
            ) from exc
        created = self.db.crisis_instance(instance_id) or instance
        response = self._activation_response(worldline_id, created, idempotent=False)
        response["events"] = events
        return response

    def dispatch_message(
        self,
        worldline_id: str,
        *,
        crisis_id: str,
        sender: str,
        recipient: str,
        content: str,
        delivery_tick: int | None = None,
    ) -> dict[str, Any]:
        """Dispatch one global message, including across two active Crisis Instances."""

        row = self._active_worldline(worldline_id)
        instance = self._instance_for_crisis(worldline_id, crisis_id)
        if instance["status"] not in {
            CrisisInstanceStatus.ACTIVE.value,
            CrisisInstanceStatus.RESOLUTION_PENDING.value,
            CrisisInstanceStatus.AFTERMATH.value,
        }:
            raise VolumeRuntimeConflict("messages require an active Crisis Instance")
        if self.db.worldline_lifetime(worldline_id, sender) is None:
            raise VolumeRuntimeError(f"unknown sender Lifetime: {sender}")
        if self.db.worldline_lifetime(worldline_id, recipient) is None:
            raise VolumeRuntimeError(f"unknown recipient Lifetime: {recipient}")
        current = int(row["current_tick"])
        arrival = current + 1 if delivery_tick is None else int(delivery_tick)
        if arrival <= current:
            raise VolumeRuntimeError("message delivery must be after the current global tick")
        message_id = f"{worldline_id}:message:{uuid.uuid4().hex[:16]}"
        message = {
            "id": message_id,
            "source_crisis_id": crisis_id,
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "dispatch_tick": current,
            "delivery_tick": arrival,
            "arrival_tick": arrival,
            "status": "in_transit",
            "source": "volume",
            "disputed": False,
            "assertion_ids": [],
        }
        projection = self._snapshot_projection(worldline_id, current)
        projection.setdefault("messages", []).append(message)
        event = self._event(
            worldline_id,
            current,
            "MESSAGE_DISPATCHED",
            message,
            seat_id=sender,
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=row["runtime_epoch"],
        )
        message["dispatch_event_id"] = event["id"]
        event["payload"] = message
        self.db.commit_volume_moment(
            worldline_id,
            [event],
            current_tick=current,
            snapshot=projection,
            expected_current_tick=current,
        )
        return {"worldline": self.db.worldline(worldline_id), "message": message, "event": event}

    def next_tick(self, worldline_id: str) -> int | None:
        """Return the next significant tick on the one authoritative Volume clock."""

        row = self._active_worldline(worldline_id)
        current = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, current)
        if projection.get("pending_moment"):
            return None
        candidates: list[int] = []
        candidates.extend(
            int(message.get("delivery_tick", message.get("arrival_tick", 0)))
            for message in projection.get("messages", [])
            if message.get("status") == "in_transit"
            and int(message.get("delivery_tick", message.get("arrival_tick", 0))) > current
        )
        candidates.extend(
            int(field_event["tick"])
            for field_event in projection.get("field_events", [])
            if field_event.get("status") == "PENDING" and int(field_event["tick"]) > current
        )
        for crisis in projection.get("crisis_instances", {}).values():
            if crisis.get("status") not in {
                CrisisInstanceStatus.ACTIVE.value,
                CrisisInstanceStatus.RESOLUTION_PENDING.value,
                CrisisInstanceStatus.AFTERMATH.value,
            }:
                continue
            for pressure in crisis.get("pressures", []):
                trigger_tick = int(pressure.get("global_trigger_tick", 0))
                if pressure.get("status") == "PENDING" and trigger_tick > current:
                    candidates.append(trigger_tick)
            for item in [*crisis.get("operations", []), *crisis.get("investigations", [])]:
                for key in ("expected_complete_tick", "expected_result_tick", "due_tick"):
                    value = item.get(key)
                    if value is not None and int(value) > current:
                        candidates.append(int(value))
            for offer in crisis.get("offers", []):
                expires_tick = offer.get("expires_tick")
                if (
                    offer.get("status") == OfferStatus.PROPOSED.value
                    and expires_tick is not None
                    and int(expires_tick) > current
                ):
                    candidates.append(int(expires_tick))
        for reference in self.pack.volume.crises:
            instance = next(
                (
                    item
                    for item in self.db.crisis_instances(worldline_id)
                    if item["crisis_id"] == reference.id
                ),
                None,
            )
            if (
                instance is not None
                and instance["status"] == CrisisInstanceStatus.DORMANT.value
                and reference.earliest_activation_tick > current
            ):
                candidates.append(reference.earliest_activation_tick)
        candidates.extend(
            int(wake["tick"])
            for wake in self.db.subject_wakes(worldline_id)
            if wake["status"] in {"QUEUED", "WAITING_HUMAN"} and int(wake["tick"]) > current
        )
        for lifetime in self.db.worldline_lifetimes(worldline_id):
            course = current_course_from_plan(list(lifetime.get("plan", [])), fallback_tick=current)
            if course is None or course.get("status") != "IN_FORCE":
                continue
            candidates.extend(
                int(dependency["due_tick"])
                for dependency in course.get("open_dependencies", [])
                if dependency.get("type") == "DEADLINE"
                and int(dependency["due_tick"]) > current
            )
        return min(candidates) if candidates else None

    def _next_tick(self, worldline_id: str) -> int | None:
        """Compatibility spelling for the Host-owned global clock boundary."""

        return self.next_tick(worldline_id)

    def advance_one(self, worldline_id: str) -> dict[str, Any]:
        """Advance the shared Volume clock and commit all effects due at that tick."""

        row = self._active_worldline(worldline_id)
        current = int(row["current_tick"])
        current_projection = self._snapshot_projection(worldline_id, current)
        if current_projection.get("pending_moment"):
            raise VolumeRuntimeConflict(
                "a Pending Logical Moment must be staged and committed first"
            )
        target = self._next_tick(worldline_id)
        if target is None:
            return {
                "worldline": row,
                "advanced": False,
                "tick": current,
                "events": [],
                "delivered_messages": [],
                "field_events": [],
                "pressures": [],
            }
        projection = self._snapshot_projection(worldline_id, current)
        previous_events = self.db.worldline_events(worldline_id)
        parent_ids = [previous_events[-1]["id"]] if previous_events else []
        advanced = self._event(
            worldline_id,
            target,
            "TIME_ADVANCED",
            {"from_tick": current, "to_tick": target, "clock": "volume_global"},
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=parent_ids,
            runtime_epoch=row["runtime_epoch"],
        )
        events = [advanced]
        delivered_messages: list[dict[str, Any]] = []
        field_events: list[dict[str, Any]] = []
        applied_pressures: list[dict[str, Any]] = []
        lifetime_updates: dict[str, dict[str, Any]] = {}
        wake_creates: list[dict[str, Any]] = []
        attention_admissions: dict[str, list[dict[str, Any]]] = {}

        def append_knowledge(actor_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
            lifetime = self.db.worldline_lifetime(worldline_id, actor_id)
            if lifetime is None:
                return None
            pending_update = lifetime_updates.get(actor_id)
            if pending_update is not None and "knowledge_json" in pending_update:
                knowledge = json.loads(str(pending_update["knowledge_json"]))
            else:
                knowledge = list(lifetime.get("knowledge", []))
            knowledge.append(item)
            lifetime_updates[actor_id] = {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
            }
            return lifetime

        def admit_knowledge(
            actor_id: str, item: dict[str, Any], attention_event: dict[str, Any]
        ) -> dict[str, Any] | None:
            lifetime = append_knowledge(actor_id, item)
            if lifetime is not None:
                attention_admissions.setdefault(actor_id, []).append(attention_event)
            return lifetime

        for lifetime in self.db.worldline_lifetimes(worldline_id):
            course = current_course_from_plan(list(lifetime.get("plan", [])), fallback_tick=current)
            if course is None or course.get("status") != "IN_FORCE":
                continue
            for dependency in course.get("open_dependencies", []):
                if (
                    dependency.get("type") != "DEADLINE"
                    or int(dependency.get("due_tick", -1)) != target
                ):
                    continue
                due = self._event(
                    worldline_id,
                    target,
                    "DECISION_DEPENDENCY_DUE",
                    {
                        "seat": lifetime["seat"],
                        "dependency_id": dependency["id"],
                        "dependency_type": "DEADLINE",
                        "due_tick": target,
                    },
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[advanced["id"]],
                    event_id=(
                        f"{worldline_id}:course:{lifetime['seat']}:dependency:"
                        f"{dependency['id']}:due:{target}"
                    ),
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(due)
                admit_knowledge(
                    lifetime["seat"],
                    {
                        "kind": "decision_dependency",
                        "event_id": due["id"],
                        "dependency_id": dependency["id"],
                        "dependency_type": "DEADLINE",
                        "due_tick": target,
                    },
                    {
                        "event_id": due["id"],
                        "event_type": "DECISION_DEPENDENCY_DUE",
                        "wake_type": "REVISIT_DUE",
                        "wake_id": f"{worldline_id}:wake:{due['id']}:{lifetime['seat']}",
                        "due_tick": target,
                    },
                )

        for field_event in projection.get("field_events", []):
            if field_event.get("status") != "PENDING" or int(field_event["tick"]) != target:
                continue
            field_event["status"] = "APPLIED"
            field_event["applied_tick"] = target
            self._apply_effects(projection, None, field_event.get("effects", []))
            applied = self._event(
                worldline_id,
                target,
                "FIELD_EVENT_APPLIED",
                {"field_event": field_event, "global_tick": target},
                provenance=Provenance.HISTORICAL.value,
                causal_parent_ids=[advanced["id"]],
                event_id=f"{worldline_id}:field:{field_event['id']}:applied:{target}",
                runtime_epoch=row["runtime_epoch"],
            )
            events.append(applied)
            field_events.append(field_event)
            for field_message in field_event.get("messages", []):
                recipients = field_message.get("recipients")
                if recipients is None:
                    recipients = [field_message.get("recipient", "")]
                for recipient in recipients:
                    recipient_id = str(recipient)
                    if self.db.worldline_lifetime(worldline_id, recipient_id) is None:
                        raise VolumeRuntimeError(
                            f"historical field message recipient is missing: {recipient_id}"
                        )
                    message_id = str(field_message.get("id", "field-message"))
                    arrival = target + max(1, int(field_message.get("delivery_offset", 1)))
                    message = {
                        "id": f"{worldline_id}:field:{field_event['id']}:message:{message_id}:{recipient_id}",
                        "source_crisis_id": str(field_message.get("source_crisis_id", "")),
                        "sender": str(field_message.get("sender", "public-record")),
                        "recipient": recipient_id,
                        "content": str(field_message.get("content", "")),
                        "dispatch_tick": target,
                        "delivery_tick": arrival,
                        "arrival_tick": arrival,
                        "status": "in_transit",
                        "source": str(field_message.get("source", "historical_field")),
                        "disputed": bool(field_message.get("disputed", False)),
                        "assertion_ids": list(
                            field_message.get("assertion_ids", field_event.get("assertion_ids", []))
                            or []
                        ),
                    }
                    projection.setdefault("messages", []).append(message)
                    dispatch = self._event(
                        worldline_id,
                        target,
                        "MESSAGE_DISPATCHED",
                        message,
                        provenance=Provenance.HISTORICAL.value,
                        causal_parent_ids=[applied["id"]],
                        event_id=(
                            f"{worldline_id}:field:{field_event['id']}:message:{message_id}:"
                            f"{recipient_id}:dispatch"
                        ),
                        runtime_epoch=row["runtime_epoch"],
                    )
                    message["dispatch_event_id"] = dispatch["id"]
                    dispatch["payload"] = message
                    events.append(dispatch)

        for message in sorted(projection.get("messages", []), key=lambda item: item["id"]):
            arrival = int(message.get("delivery_tick", message.get("arrival_tick", 0)))
            if message.get("status") != "in_transit" or arrival != target:
                continue
            message["status"] = "delivered"
            message["delivered_tick"] = target
            delivered = self._event(
                worldline_id,
                target,
                "MESSAGE_DELIVERED",
                {
                    "message_id": message["id"],
                    "crisis_id": message.get("source_crisis_id", ""),
                    "from": message["sender"],
                    "recipient": message["recipient"],
                    "content": message["content"],
                    "delivery_tick": target,
                    "source": message.get("source", ""),
                    "assertion_ids": list(message.get("assertion_ids", [])),
                    "disputed": bool(message.get("disputed", False)),
                },
                seat_id=message["recipient"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[advanced["id"], message.get("dispatch_event_id", "")],
                runtime_epoch=row["runtime_epoch"],
            )
            events.append(delivered)
            delivered_messages.append(message)
            lifetime = self.db.worldline_lifetime(worldline_id, message["recipient"])
            if lifetime is None:
                raise VolumeRuntimeError(
                    f"message recipient Lifetime is missing: {message['recipient']}"
                )
            knowledge_item = {
                "type": "MESSAGE",
                "message_id": message["id"],
                "from": message["sender"],
                "content": message["content"],
                "tick": target,
                "disputed": bool(message.get("disputed", False)),
                "source": message.get("source", ""),
                "assertion_ids": list(message.get("assertion_ids", [])),
            }
            admit_knowledge(
                message["recipient"],
                knowledge_item,
                {
                    "event_id": delivered["id"],
                    "event_type": "MESSAGE_DELIVERED",
                    "wake_type": "OBSERVATION",
                    "wake_id": f"{worldline_id}:wake:{message['id']}",
                    "actor_id": message["sender"],
                    "message_id": message["id"],
                },
            )

        for crisis_id in sorted(projection.get("crisis_instances", {})):
            crisis = projection["crisis_instances"][crisis_id]
            if crisis.get("status") not in {
                CrisisInstanceStatus.ACTIVE.value,
                CrisisInstanceStatus.RESOLUTION_PENDING.value,
                CrisisInstanceStatus.AFTERMATH.value,
            }:
                continue
            pack = self.pack.pack(crisis_id)
            for item in crisis.get("operations", []):
                if item.get("status") != "IN_PROGRESS" or int(item.get("expected_complete_tick", -1)) != target:
                    continue
                definition = pack.operation_by_id.get(str(item.get("definition_id", "")))
                if definition is None:
                    raise VolumeRuntimeError(f"operation definition is missing: {item.get('definition_id')}")
                item["status"] = "COMPLETED"
                visible = (
                    sorted(pack.participant_ids)
                    if definition.visibility.value == "PUBLIC"
                    else [str(item["actor_id"])]
                )
                completed = self._event(
                    worldline_id,
                    target,
                    "OPERATION_COMPLETED",
                    {"operation": item, "visibility": visible},
                    seat_id=item["actor_id"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[item["start_event_id"]],
                    runtime_epoch=row["runtime_epoch"],
                )
                item["completion_event_id"] = completed["id"]
                events.append(completed)
                for effect in definition.completion_effects:
                    entity_id = item["target_map"].get(effect.subject, effect.subject)
                    entity = crisis["entities"].get(entity_id)
                    if entity is None or entity["state"] == effect.state:
                        continue
                    before = entity["state"]
                    entity["state"] = effect.state
                    item["result_state"][entity_id] = effect.state
                    events.append(
                        self._event(
                            worldline_id,
                            target,
                            "ENTITY_STATE_CHANGED",
                            {
                                "operation_id": item["id"],
                                "crisis_id": crisis_id,
                                "entity_id": entity_id,
                                "before": before,
                                "after": effect.state,
                                "phase": "completion",
                                "visibility": visible,
                            },
                            seat_id=item["actor_id"],
                            provenance=Provenance.BRANCH_DERIVED.value,
                            causal_parent_ids=[completed["id"]],
                            runtime_epoch=row["runtime_epoch"],
                        )
                    )
                movement_target = item["target_map"].get(definition.movement_destination_target, "")
                if movement_target:
                    projection["positions"][item["actor_id"]] = movement_target
                for actor_id in visible:
                    lifetime = admit_knowledge(
                        actor_id,
                        {
                            "kind": "observation",
                            "event_id": completed["id"],
                            "observation": f"{definition.display_name}已经完成。",
                            "received_tick": target,
                            "provenance": "branch_derived",
                            "crisis_id": crisis_id,
                        },
                        {
                            "event_id": completed["id"],
                            "event_type": "OPERATION_COMPLETED",
                            "wake_type": "OPERATION_RESULT",
                            "wake_id": f"{worldline_id}:wake:{completed['id']}:{actor_id}",
                            "actor_id": item["actor_id"],
                            "operation_id": item["id"],
                            "entity_ids": sorted(item.get("result_state", {})),
                        },
                    )
                    if lifetime is None:
                        continue
            for item in crisis.get("investigations", []):
                if item.get("status") != "IN_PROGRESS" or int(item.get("expected_result_tick", -1)) != target:
                    continue
                definition = pack.investigation_by_id.get(str(item.get("definition_id", "")))
                if definition is None:
                    raise VolumeRuntimeError(f"investigation definition is missing: {item.get('definition_id')}")
                item["status"] = "COMPLETED"
                visible = (
                    sorted(pack.participant_ids)
                    if definition.visibility.value == "PUBLIC"
                    else [str(item["actor_id"])]
                )
                completed = self._event(
                    worldline_id,
                    target,
                    "INVESTIGATION_COMPLETED",
                    {"investigation": item, "visibility": visible},
                    seat_id=item["actor_id"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[item["start_event_id"]],
                    runtime_epoch=row["runtime_epoch"],
                )
                item["completion_event_id"] = completed["id"]
                observation = {
                    "id": f"{item['id']}:observation",
                    "investigation_id": item["id"],
                    "content": definition.observation.content,
                    "source": definition.observation.source,
                    "source_ids": list(definition.observation.source_ids),
                    "reliability": definition.observation.reliability.value,
                    "obtained_tick": target,
                    "related_assertions": list(definition.observation.related_assertion_ids),
                }
                item["observation"] = observation
                observed = self._event(
                    worldline_id,
                    target,
                    "OBSERVATION_OBTAINED",
                    {"observation": observation, "visibility": visible},
                    seat_id=item["actor_id"],
                    provenance=Provenance.HISTORICAL.value,
                    causal_parent_ids=[completed["id"]],
                    runtime_epoch=row["runtime_epoch"],
                )
                observation["event_id"] = observed["id"]
                events.extend([completed, observed])
                for actor_id in visible:
                    lifetime = admit_knowledge(
                        actor_id,
                        {
                            "kind": "observation",
                            "event_id": observed["id"],
                            "observation": observation["content"],
                            "source": observation["source"],
                            "source_ids": observation["source_ids"],
                            "reliability": observation["reliability"],
                            "obtained_tick": target,
                            "related_assertions": observation["related_assertions"],
                            "investigation_id": item["id"],
                            "crisis_id": crisis_id,
                        },
                        {
                            "event_id": observed["id"],
                            "event_type": "OBSERVATION_OBTAINED",
                            "wake_type": "INVESTIGATION_RESULT",
                            "wake_id": f"{worldline_id}:wake:{observed['id']}:{actor_id}",
                            "actor_id": item["actor_id"],
                            "investigation_id": item["id"],
                        },
                    )
                    if lifetime is None:
                        continue
            for offer in crisis.get("offers", []):
                if offer.get("status") != OfferStatus.PROPOSED.value or offer.get("expires_tick") is None:
                    continue
                if int(offer["expires_tick"]) != target:
                    continue
                offer["status"] = OfferStatus.EXPIRED.value
                expired = self._event(
                    worldline_id,
                    target,
                    "OFFER_EXPIRED",
                    {"offer": offer, "visibility": [offer["issuer"], offer["recipient"]]},
                    seat_id=offer["issuer"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[offer.get("proposal_event_id", "")],
                    runtime_epoch=row["runtime_epoch"],
                )
                offer["expiry_event_id"] = expired["id"]
                events.append(expired)

        for crisis_id in sorted(projection.get("crisis_instances", {})):
            crisis = projection["crisis_instances"][crisis_id]
            if crisis.get("status") not in {
                CrisisInstanceStatus.ACTIVE.value,
                CrisisInstanceStatus.RESOLUTION_PENDING.value,
                CrisisInstanceStatus.AFTERMATH.value,
            }:
                continue
            crisis["local_tick"] = target - int(crisis["activation_tick"])
            for pressure in crisis.get("pressures", []):
                if (
                    pressure.get("status") != "PENDING"
                    or int(pressure.get("global_trigger_tick", 0)) != target
                ):
                    continue
                applies = self._pressure_preconditions_met(projection, crisis, pressure)
                pressure["status"] = "APPLIED" if applies else "SKIPPED"
                pressure["applied_tick"] = target
                if applies:
                    self._apply_effects(projection, crisis, pressure.get("effects", []))
                pressure_event = self._event(
                    worldline_id,
                    target,
                    "CRISIS_PRESSURE_APPLIED" if applies else "CRISIS_PRESSURE_SKIPPED",
                    {
                        "crisis_id": crisis_id,
                        "pressure": pressure,
                        "global_tick": target,
                        "local_tick": crisis["local_tick"],
                    },
                    provenance=pressure["provenance"],
                    causal_parent_ids=[advanced["id"]],
                    event_id=f"{worldline_id}:crisis:{crisis_id}:pressure:{pressure['id']}:{target}",
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(pressure_event)
                applied_pressures.append(pressure)

        projection["tick"] = target
        for actor_id in sorted(attention_admissions):
            lifetime = self.db.worldline_lifetime(worldline_id, actor_id)
            if lifetime is None:
                continue
            admissions = attention_admissions[actor_id]
            attention = evaluate_attention(lifetime, admissions, projection)
            attention_event = self._event(
                worldline_id,
                target,
                "ATTENTION_EVALUATED",
                {
                    "seat": lifetime["seat"],
                    "new_known_event_ids": list(
                        dict.fromkeys(
                            str(admission.get("event_id", ""))
                            for admission in admissions
                            if str(admission.get("event_id", ""))
                        )
                    ),
                    **attention.as_dict(),
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=list(attention.trigger_event_ids),
                event_id=(
                    f"{worldline_id}:attention:{target}:{lifetime['seat']}:"
                    f"{stable_hash(attention.as_dict())[:12]}"
                ),
                runtime_epoch=row["runtime_epoch"],
            )
            events.append(attention_event)
            if attention.decision != AttentionDecision.REOPEN:
                continue
            wake_types = {
                str(admission.get("wake_type", "ATTENTION")) for admission in admissions
            }
            wake_type = wake_types.pop() if len(wake_types) == 1 else "ATTENTION"
            wake_id = (
                str(admissions[0].get("wake_id", ""))
                if len(admissions) == 1
                else ""
            ) or f"{worldline_id}:wake:{attention_event['id']}:{lifetime['seat']}"
            wake_creates.append(
                {
                    "id": wake_id,
                    "actor_id": lifetime["seat"],
                    "wake_type": wake_type,
                    "tick": target,
                    "status": "WAITING_HUMAN" if lifetime["controller"] == "HUMAN" else "QUEUED",
                    "source": "v6-attention",
                    "trigger_event_id": attention_event["id"],
                    "result": {"attention": attention.as_dict()},
                }
            )
        projection["last_event_id"] = events[-1]["id"]
        self.db.commit_volume_moment(
            worldline_id,
            events,
            current_tick=target,
            lifetime_updates=list(lifetime_updates.values()),
            wake_creates=wake_creates,
            snapshot=projection,
            expected_current_tick=current,
        )
        envelope_result = self.reconcile_crisis_envelopes(worldline_id)
        events.extend(envelope_result.get("events", []))
        return {
            "worldline": self.db.worldline(worldline_id),
            "advanced": True,
            "tick": target,
            "events": events,
            "delivered_messages": delivered_messages,
            "field_events": field_events,
            "pressures": applied_pressures,
        }

    def settle_crisis(
        self,
        worldline_id: str,
        crisis_id: str,
        *,
        outcome: dict[str, Any] | None = None,
        reason: str = "settled",
    ) -> dict[str, Any]:
        """Settle one Crisis Instance while preserving the active Volume Worldline."""

        row = self._active_worldline(worldline_id)
        instance = self._instance_for_crisis(worldline_id, crisis_id)
        if instance["status"] == CrisisInstanceStatus.SETTLED.value:
            return {
                "worldline": row,
                "instance": instance,
                "idempotent": True,
            }
        if instance["status"] not in {
            CrisisInstanceStatus.ACTIVE.value,
            CrisisInstanceStatus.RESOLUTION_PENDING.value,
            CrisisInstanceStatus.AFTERMATH.value,
        }:
            raise VolumeRuntimeConflict(
                f"Crisis Instance {crisis_id} cannot settle from {instance['status']}"
            )
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        crisis = projection.get("crisis_instances", {}).get(crisis_id)
        if crisis is None:
            raise VolumeRuntimeError(f"Crisis projection is missing: {crisis_id}")
        outcome_data = dict(outcome or {})
        local_tick = tick - int(instance["activation_tick"])
        crisis.update(
            {
                "status": CrisisInstanceStatus.SETTLED.value,
                "phase": "SETTLED",
                "settled_tick": tick,
                "local_tick": local_tick,
                "outcome": outcome_data,
                "settlement": {
                    "status": "SETTLED",
                    "reason": reason,
                    "global_tick": tick,
                    "local_tick": local_tick,
                },
            }
        )
        projection["active_crisis_ids"] = [
            item for item in projection.get("active_crisis_ids", []) if item != crisis_id
        ]
        event = self._event(
            worldline_id,
            tick,
            "CRISIS_SETTLED",
            {
                "instance_id": instance["id"],
                "crisis_id": crisis_id,
                "global_tick": tick,
                "local_tick": local_tick,
                "reason": reason,
                "outcome": outcome_data,
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=row["runtime_epoch"],
        )
        projection["last_event_id"] = event["id"]
        self.db.commit_volume_moment(
            worldline_id,
            [event],
            current_tick=tick,
            instance_updates=[
                {
                    "id": instance["id"],
                    "status": CrisisInstanceStatus.SETTLED.value,
                    "phase": "SETTLED",
                    "settled_tick": tick,
                    "outcome": outcome_data,
                }
            ],
            snapshot=projection,
            expected_current_tick=tick,
        )
        envelope_result = self.reconcile_crisis_envelopes(worldline_id)
        return {
            "worldline": self.db.worldline(worldline_id),
            "instance": self.db.crisis_instance(instance["id"]),
            "event": event,
            "events": [event, *envelope_result.get("events", [])],
            "idempotent": False,
        }

    def freeze_pending_moment(self, worldline_id: str) -> dict[str, Any]:
        """Freeze all due Subject Wakes at the current global tick."""

        row = self._active_worldline(worldline_id)
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        existing = projection.get("pending_moment")
        if existing:
            return {
                "worldline": row,
                "moment_id": existing["id"],
                "pending_moment": existing,
                "idempotent": True,
            }
        wakes = [
            wake
            for wake in self.db.subject_wakes(worldline_id, tick=tick)
            if wake["status"] in {"QUEUED", "WAITING_HUMAN"}
        ]
        if not wakes:
            raise VolumeRuntimeConflict("there are no due Subject Wakes to freeze")
        wake_ids = sorted(str(wake["id"]) for wake in wakes)
        moment_id = f"{worldline_id}:moment:{tick}:{stable_hash(wake_ids)[:12]}"
        frozen_updates: list[dict[str, Any]] = []
        for wake in sorted(wakes, key=lambda item: item["id"]):
            lifetime = self._lifetime_for_actor(worldline_id, str(wake["actor_id"]))
            if lifetime is None:
                raise VolumeRuntimeError(f"Subject Wake Lifetime is missing: {wake['actor_id']}")
            perspective = {
                "moment_id": moment_id,
                "worldline_id": worldline_id,
                "lifetime_id": lifetime["id"],
                "seat": lifetime["seat"],
                "tick": tick,
                "controller": lifetime["controller"],
                "trigger_event_id": wake["trigger_event_id"],
                "wake_type": wake["wake_type"],
                "context": LifetimeContextBuilder(self.db, self.pack).build(
                    worldline_id,
                    lifetime["id"],
                    projection,
                    wake=wake,
                ),
            }
            frozen_updates.append(
                {
                    "id": wake["id"],
                    "frozen_perspective": perspective,
                }
            )
        pending = {
            "id": moment_id,
            "tick": tick,
            "wake_ids": wake_ids,
            "phase": "FROZEN",
        }
        projection["pending_moment"] = pending
        frozen = self._event(
            worldline_id,
            tick,
            "MOMENT_FROZEN",
            {"moment_id": moment_id, "tick": tick, "wake_ids": wake_ids},
            provenance=Provenance.BRANCH_DERIVED.value,
            event_id=f"{moment_id}:frozen",
            runtime_epoch=row["runtime_epoch"],
        )
        projection["last_event_id"] = frozen["id"]
        self.db.commit_volume_moment(
            worldline_id,
            [frozen],
            current_tick=tick,
            wake_updates=frozen_updates,
            snapshot=projection,
            expected_current_tick=tick,
        )
        return {
            "worldline": self.db.worldline(worldline_id),
            "moment_id": moment_id,
            "pending_moment": pending,
            "idempotent": False,
        }

    def stage_intent(
        self,
        worldline_id: str,
        lifetime_id: str,
        intent: dict[str, Any],
        *,
        source: str | None = None,
        idempotency_key: str | None = None,
        wake_id: str = "",
    ) -> dict[str, Any]:
        """Stage one Human or Agent intent without changing the Volume projection."""

        row = self._active_worldline(worldline_id)
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        pending = projection.get("pending_moment")
        if not pending:
            raise VolumeRuntimeConflict("freeze the current logical moment before staging intent")
        lifetime = self._lifetime_for_actor(worldline_id, lifetime_id)
        if lifetime is None:
            raise VolumeRuntimeError(f"Lifetime not found: {lifetime_id}")
        seat = str(lifetime["seat"])
        expected_source = "human" if lifetime["controller"] == "HUMAN" else "agent"
        actual_source = source or expected_source
        if actual_source != expected_source:
            raise VolumeRuntimeConflict(
                f"{seat} is controlled by {lifetime['controller']}, not {actual_source}"
            )
        if wake_id:
            wake = self.db.crisis_wake(wake_id)
            if (
                wake is None
                or str(wake["worldline_id"]) != worldline_id
                or str(wake["actor_id"]) != seat
                or wake_id not in pending["wake_ids"]
            ):
                raise VolumeRuntimeConflict("wake identity is not in this Pending Logical Moment")
        else:
            wake = next(
                (
                    candidate
                    for candidate_id in pending["wake_ids"]
                    if (candidate := self.db.crisis_wake(candidate_id)) is not None
                    and (
                        candidate_lifetime := self._lifetime_for_actor(
                            worldline_id, str(candidate["actor_id"])
                        )
                    )
                    is not None
                    and candidate_lifetime["seat"] == seat
                ),
                None,
            )
        if wake is None:
            raise VolumeRuntimeConflict(f"{seat} has no Wake in Pending Logical Moment")
        if wake["status"] == "COMPLETED":
            raise VolumeRuntimeConflict("this Wake has already completed")
        if wake["status"] not in {"QUEUED", "WAITING_HUMAN", "RUNNING", "STAGED"}:
            raise VolumeRuntimeConflict(f"Wake is not stageable: {wake['status']}")
        if not isinstance(intent, dict) or str(intent.get("type", "wait")) not in {
            "wait",
            "message",
            "update_plan",
        }:
            raise VolumeRuntimeError("V5 supports wait, message, and update_plan intents")
        intent = dict(intent)
        intent.setdefault("type", "wait")
        if intent["type"] == "update_plan":
            intent = self._normalize_plan_intent(
                worldline_id,
                lifetime,
                wake,
                intent,
                source=actual_source,
            )
        elif intent["type"] == "message":
            self._logical_message(worldline_id, pending["id"], seat, intent, tick)
        belief_keys = [
            str(item).strip() for item in intent.get("belief_keys", []) if str(item).strip()
        ]
        unknown_belief_keys = set(belief_keys) - set(lifetime["beliefs"])
        if unknown_belief_keys:
            raise VolumeRuntimeError(
                "unknown expectation keys: " + ", ".join(sorted(unknown_belief_keys))
            )
        intent["belief_keys"] = list(dict.fromkeys(belief_keys))
        key = idempotency_key or stable_hash(
            {"moment_id": pending["id"], "seat": seat, "intent": intent}
        )
        existing = next(
            (
                operation
                for operation in self.db.crisis_wake_operations(wake["id"])
                if operation["idempotency_key"] == key
            ),
            None,
        )
        operation = existing or self.db.add_crisis_wake_operation(
            {
                "wake_id": wake["id"],
                "tool_name": "logical_intent",
                "payload": {
                    "moment_id": pending["id"],
                    "lifetime_id": lifetime["id"],
                    "seat": seat,
                    "source": actual_source,
                    "intent": intent,
                },
                "result": {"status": "accepted", "moment_id": pending["id"]},
                "status": "PROPOSED",
                "idempotency_key": key,
            }
        )
        if wake["status"] != "STAGED":
            self.db.update_crisis_wake(wake["id"], status="STAGED")
        return {
            "moment_id": pending["id"],
            "lifetime_id": lifetime["id"],
            "seat": seat,
            "source": actual_source,
            "operation": operation,
            "idempotent": existing is not None,
        }

    def stage_deliberation(
        self,
        worldline_id: str,
        lifetime_id: str,
        proposal: dict[str, Any],
        *,
        source: str | None = None,
        idempotency_key: str | None = None,
        wake_id: str = "",
    ) -> dict[str, Any]:
        """Stage one complete V6 Deliberation proposal without World mutation."""

        try:
            normalized = normalize_deliberation(proposal)
        except DeliberationError as exc:
            raise VolumeRuntimeError(str(exc)) from exc

        row = self._active_worldline(worldline_id)
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        pending = projection.get("pending_moment")
        if not pending:
            raise VolumeRuntimeConflict("freeze the current logical moment before staging deliberation")
        lifetime = self._lifetime_for_actor(worldline_id, lifetime_id)
        if lifetime is None:
            raise VolumeRuntimeError(f"Lifetime not found: {lifetime_id}")
        seat = str(lifetime["seat"])
        expected_source = "human" if lifetime["controller"] == "HUMAN" else "agent"
        actual_source = source or expected_source
        if actual_source != expected_source:
            raise VolumeRuntimeConflict(
                f"{seat} is controlled by {lifetime['controller']}, not {actual_source}"
            )

        wake = self.db.crisis_wake(wake_id) if wake_id else self._pending_wake_for_lifetime(
            worldline_id, pending, seat
        )
        if wake is None:
            raise VolumeRuntimeConflict(f"{seat} has no Wake in Pending Logical Moment")
        if (
            str(wake["worldline_id"]) != worldline_id
            or str(wake["actor_id"]) not in {seat, str(lifetime["id"])}
            or str(wake["id"]) not in {str(item) for item in pending.get("wake_ids", [])}
        ):
            raise VolumeRuntimeConflict("wake identity is not in this Pending Logical Moment")
        if wake["status"] == "COMPLETED":
            raise VolumeRuntimeConflict("this Wake has already completed")
        if wake["status"] not in {"QUEUED", "WAITING_HUMAN", "RUNNING", "STAGED"}:
            raise VolumeRuntimeConflict(f"Wake is not stageable: {wake['status']}")

        current_course = current_course_from_plan(list(lifetime.get("plan", [])), fallback_tick=tick)
        if normalized.outcome == "HOLD" and current_course is None:
            raise VolumeRuntimeError("HOLD requires an existing Current Course")

        course = normalized.course
        if normalized.outcome == "HOLD":
            objective = str(current_course.get("course") or current_course.get("objective") or "")
            steps = list(current_course.get("steps") or [objective])
            evidence_event_ids = list(current_course.get("evidence_event_ids", []))
            dependencies = (
                normalized.open_dependencies
                if "open_dependencies" in proposal
                else list(current_course.get("open_dependencies", []))
            )
            rationale = ""
            rationale_source = ""
        else:
            objective = str(course.get("summary", course.get("objective", ""))).strip()
            steps = [str(step).strip() for step in course.get("steps", []) if str(step).strip()]
            if not steps:
                steps = [objective]
            evidence_event_ids = [
                str(event_id)
                for event_id in course.get("evidence_event_ids", [])
                if str(event_id)
            ]
            if actual_source == "agent" and not evidence_event_ids:
                if current_course is None and wake.get("trigger_event_id"):
                    evidence_event_ids = [str(wake["trigger_event_id"])]
                else:
                    raise VolumeRuntimeConflict(
                        "Agent REVISE requires actor-visible evidence_event_ids"
                    )
            dependencies = normalized.open_dependencies
            rationale = str(course.get("rationale", "")).strip()
            rationale_source = normalized.rationale_source or str(
                course.get("rationale_source", "")
            ).strip()

        course_intent = self._normalize_plan_intent(
            worldline_id,
            lifetime,
            wake,
            {
                "type": "update_plan",
                "objective": objective,
                "steps": steps,
                "rationale": rationale,
                "rationale_source": rationale_source,
                "belief_source": normalized.belief_source,
                "belief_updates": normalized.belief_updates,
                "evidence_event_ids": evidence_event_ids,
                "open_dependencies": dependencies,
            },
            source=actual_source,
        )

        action_projection = self._action_projection(projection)
        staged_action: dict[str, Any] | None = None
        if normalized.world_actions:
            action = normalized.world_actions[0]
            action_tool = action["tool"]
            arguments = action["arguments"]
            active_packs = self._active_packs_for_actor(worldline_id, seat, projection)
            if action_tool not in DELIBERATION_WORLD_TOOLS:
                raise VolumeRuntimeError(f"unsupported Deliberation world action: {action_tool}")
            if action_tool not in set(lifetime.get("authority", [])):
                raise VolumeRuntimeConflict(
                    f"Deliberation world action is outside {seat} authority: {action_tool}"
                )
            if action_tool == "communicate":
                action_payload, action_result = self._prepare_volume_communication(
                    worldline_id, lifetime, arguments, action_projection, tick
                )
            elif action_tool == "schedule_revisit":
                action_payload, action_result = self._prepare_volume_revisit(
                    lifetime, arguments, tick
                )
            elif action_tool == "investigate":
                action_payload, action_result = self._prepare_volume_investigation(
                    lifetime, arguments, active_packs, action_projection, tick
                )
            elif action_tool == "operate":
                action_payload, action_result = self._prepare_volume_operation(
                    lifetime, arguments, active_packs, action_projection, tick
                )
            else:
                action_payload, action_result = self._prepare_volume_offer(
                    lifetime, arguments, active_packs, action_projection, tick
                )
            if action_result.get("status") != "accepted":
                raise VolumeRuntimeConflict(
                    f"Deliberation world action is invalid: {action_result.get('code', 'rejected')}"
                )
            staged_action = {
                "tool": action_tool,
                "payload": action_payload,
                "result": action_result,
            }

        stored_proposal = {
            **normalized.as_dict(),
            "course": course_intent,
            "open_dependencies": list(course_intent["open_dependencies"]),
            "belief_updates": list(course_intent["belief_updates"]),
        }
        payload = {
            "proposal": stored_proposal,
            "course_intent": course_intent,
            "world_action": staged_action,
        }
        key = idempotency_key or stable_hash(
            {"moment_id": pending["id"], "seat": seat, "proposal": stored_proposal}
        )
        existing = next(
            (
                operation
                for operation in self.db.crisis_wake_operations(wake["id"])
                if operation["idempotency_key"] == key
            ),
            None,
        )
        operation = existing or self.db.add_crisis_wake_operation(
            {
                "wake_id": wake["id"],
                "tool_name": "commit_deliberation",
                "payload": {
                    "moment_id": pending["id"],
                    "lifetime_id": lifetime["id"],
                    "seat": seat,
                    "source": actual_source,
                    **payload,
                },
                "result": {"status": "accepted", "moment_id": pending["id"]},
                "status": "PROPOSED",
                "idempotency_key": key,
            }
        )
        if wake["status"] != "STAGED":
            self.db.update_crisis_wake(wake["id"], status="STAGED")
        return {
            "moment_id": pending["id"],
            "lifetime_id": lifetime["id"],
            "seat": seat,
            "source": actual_source,
            "outcome": normalized.outcome,
            "operation": operation,
            "idempotent": existing is not None,
        }

    def stage_actor_tool(
        self,
        worldline_id: str,
        lifetime_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        source: str = "agent",
        idempotency_key: str = "",
        wake_id: str = "",
    ) -> dict[str, Any]:
        """Stage one of the existing World tools in the V5 logical moment.

        The Volume keeps the old crisis affordances, but their writes are still
        staged against the same frozen moment as Human and Agent plans.
        """

        tool_name = str(tool_name).strip()
        if tool_name not in VOLUME_WORLD_TOOLS:
            raise VolumeRuntimeError(f"unsupported V5 World tool: {tool_name}")
        row = self._active_worldline(worldline_id)
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        pending = projection.get("pending_moment")
        if not pending:
            raise VolumeRuntimeConflict("freeze the current logical moment before staging tool")
        lifetime = self._lifetime_for_actor(worldline_id, lifetime_id)
        if lifetime is None:
            raise VolumeRuntimeError(f"Lifetime not found: {lifetime_id}")
        if wake_id:
            wake = self.db.crisis_wake(wake_id)
            if (
                wake is None
                or str(wake["worldline_id"]) != worldline_id
                or str(wake["actor_id"]) != lifetime["seat"]
                or wake_id not in pending["wake_ids"]
            ):
                raise VolumeRuntimeConflict("wake identity is not in this Pending Logical Moment")
        else:
            wake = self._pending_wake_for_lifetime(worldline_id, pending, lifetime["seat"])
        if wake is None:
            raise VolumeRuntimeConflict(f"{lifetime['seat']} has no Wake in Pending Logical Moment")
        expected_source = "human" if lifetime["controller"] == "HUMAN" else "agent"
        if source != expected_source:
            raise VolumeRuntimeConflict(
                f"{lifetime['seat']} is controlled by {lifetime['controller']}, not {source}"
            )
        arguments = dict(arguments or {})
        if tool_name not in set(lifetime.get("authority", [])):
            return self._stage_volume_operation(
                wake,
                lifetime,
                tool_name,
                arguments,
                {"status": "rejected", "code": "authority_denied"},
                idempotency_key=idempotency_key,
                source=source,
            )
        active_packs = self._active_packs_for_actor(worldline_id, lifetime["seat"], projection)
        action_projection = self._action_projection(projection)

        if tool_name == "update_plan":
            intent = self._normalize_plan_intent(
                worldline_id,
                lifetime,
                wake,
                {"type": "update_plan", **arguments},
                source=source,
            )
            self._validate_belief_keys(lifetime, intent)
            payload = intent
            result = {"status": "accepted", "moment_id": pending["id"]}
        elif tool_name == "communicate":
            payload, result = self._prepare_volume_communication(
                worldline_id, lifetime, arguments, action_projection, tick
            )
        elif tool_name == "schedule_revisit":
            payload, result = self._prepare_volume_revisit(lifetime, arguments, tick)
        elif tool_name == "investigate":
            payload, result = self._prepare_volume_investigation(
                lifetime, arguments, active_packs, action_projection, tick
            )
        elif tool_name == "operate":
            payload, result = self._prepare_volume_operation(
                lifetime, arguments, active_packs, action_projection, tick
            )
        else:
            payload, result = self._prepare_volume_offer(
                lifetime, arguments, active_packs, action_projection, tick
            )
        return self._stage_volume_operation(
            wake,
            lifetime,
            tool_name,
            payload,
            result,
            idempotency_key=idempotency_key,
            source=source,
        )

    def _pending_wake_for_lifetime(
        self, worldline_id: str, pending: dict[str, Any], seat: str
    ) -> dict[str, Any] | None:
        for wake_id in pending.get("wake_ids", []):
            wake = self.db.crisis_wake(str(wake_id))
            if wake is None:
                continue
            lifetime = self._lifetime_for_actor(worldline_id, str(wake["actor_id"]))
            if lifetime is not None and lifetime["seat"] == seat:
                return wake
        return None

    def _active_packs_for_actor(
        self, worldline_id: str, seat: str, projection: dict[str, Any]
    ) -> list[tuple[str, CrisisPack]]:
        result: list[tuple[str, CrisisPack]] = []
        for crisis_id in projection.get("active_crisis_ids", []):
            pack = self.pack.pack(str(crisis_id))
            if seat in pack.participant_ids:
                result.append((str(crisis_id), pack))
        return result

    def _action_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        action = copy.deepcopy(projection)
        action["entities"] = {}
        for key in ("operations", "investigations", "offers", "agreements"):
            action[key] = []
        for crisis_id in projection.get("active_crisis_ids", []):
            state = projection.get("crisis_instances", {}).get(str(crisis_id), {})
            for entity_id, entity in state.get("entities", {}).items():
                action["entities"][entity_id] = copy.deepcopy(entity)
            for key in ("operations", "investigations", "offers", "agreements"):
                action[key].extend(
                    {**copy.deepcopy(item), "crisis_id": str(crisis_id)}
                    for item in state.get(key, [])
                )
        return action

    @staticmethod
    def _validate_belief_keys(lifetime: dict[str, Any], intent: dict[str, Any]) -> None:
        belief_keys = [
            str(item).strip() for item in intent.get("belief_keys", []) if str(item).strip()
        ]
        unknown = set(belief_keys) - set(lifetime["beliefs"])
        if unknown:
            raise VolumeRuntimeError("unknown expectation keys: " + ", ".join(sorted(unknown)))
        intent["belief_keys"] = list(dict.fromkeys(belief_keys))

    def _stage_volume_operation(
        self,
        wake: dict[str, Any],
        lifetime: dict[str, Any],
        tool_name: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        *,
        idempotency_key: str,
        source: str,
    ) -> dict[str, Any]:
        moment_id = str(wake["frozen_perspective"].get("moment_id", ""))
        key = idempotency_key or stable_hash(
            {"moment_id": moment_id, "seat": lifetime["seat"], "tool": tool_name, "payload": payload}
        )
        existing = next(
            (
                operation
                for operation in self.db.crisis_wake_operations(wake["id"])
                if operation["idempotency_key"] == key
            ),
            None,
        )
        if existing is not None:
            return {
                **existing["result"],
                "moment_id": moment_id,
                "operation": existing,
                "idempotent": True,
            }
        stored_payload = {
            "moment_id": moment_id,
            "lifetime_id": lifetime["id"],
            "seat": lifetime["seat"],
            "source": source,
            **payload,
        }
        operation = self.db.add_crisis_wake_operation(
            {
                "wake_id": wake["id"],
                "tool_name": tool_name,
                "payload": stored_payload,
                "result": result,
                "status": "PROPOSED",
                "idempotency_key": key,
            }
        )
        if wake["status"] != "STAGED":
            self.db.update_crisis_wake(wake["id"], status="STAGED")
        return {
            **result,
            "moment_id": moment_id,
            "operation": operation,
            "idempotent": False,
        }

    def _prepare_volume_communication(
        self,
        worldline_id: str,
        lifetime: dict[str, Any],
        arguments: dict[str, Any],
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        recipient = self._reference_id(arguments.get("recipient", ""))
        content = str(arguments.get("content", "")).strip()
        if not recipient or recipient == lifetime["seat"] or self._lifetime_for_actor(worldline_id, recipient) is None:
            return {"recipient": recipient, "content": content}, {"status": "rejected", "code": "invalid_recipient"}
        if not content or len(content) > 1200:
            return {"recipient": recipient, "content": content}, {"status": "rejected", "code": "invalid_content"}
        start = str(projection.get("positions", {}).get(lifetime["seat"], ""))
        end = str(projection.get("positions", {}).get(recipient, ""))
        travel = self._volume_route_days(start, end)
        if travel is None:
            return {"recipient": recipient, "content": content}, {"status": "rejected", "code": "no_route"}
        return (
            {"recipient": recipient, "content": content},
            {"status": "accepted", "message_id": f"message-{uuid.uuid4().hex[:16]}", "arrival_tick": tick + max(1, travel)},
        )

    def _prepare_volume_revisit(
        self, lifetime: dict[str, Any], arguments: dict[str, Any], tick: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        after_days = int(arguments.get("after_days", 0) or 0)
        reason = str(arguments.get("reason", "")).strip()
        if after_days <= 0 or not reason:
            return {"after_days": after_days, "reason": reason}, {"status": "rejected", "code": "invalid_revisit"}
        due_tick = tick + after_days
        if due_tick >= self._volume_horizon():
            return {"after_days": after_days, "reason": reason}, {"status": "rejected", "code": "crosses_volume_boundary"}
        return (
            {"after_days": after_days, "reason": reason},
            {"status": "accepted", "revisit_id": f"revisit-{uuid.uuid4().hex[:16]}", "due_tick": due_tick},
        )

    def _prepare_volume_investigation(
        self,
        lifetime: dict[str, Any],
        arguments: dict[str, Any],
        active_packs: list[tuple[str, CrisisPack]],
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        question = str(arguments.get("question", "")).strip()
        target = self._reference_id(arguments.get("target", ""))
        method = str(arguments.get("method", "")).strip()
        payload = {"question": question, "target": target, "method": method}
        if not question or len(question) > 1200:
            return payload, {"status": "rejected", "code": "invalid_question"}
        for crisis_id, pack in active_packs:
            request, code = pack.investigation_request(
                lifetime["seat"], target, method, projection, tick
            )
            if request is not None:
                return (
                    {**payload, "crisis_id": crisis_id, "definition_id": request.definition.id},
                    {
                        "status": "accepted",
                        "investigation_id": f"investigation-{uuid.uuid4().hex[:16]}",
                        "definition_id": request.definition.id,
                        "expected_result_tick": request.expected_result_tick,
                    },
                )
            if code == "investigation_method_required" and not method:
                return payload, {"status": "rejected", "code": code}
        return payload, {"status": "rejected", "code": "investigation_unavailable"}

    def _prepare_volume_operation(
        self,
        lifetime: dict[str, Any],
        arguments: dict[str, Any],
        active_packs: list[tuple[str, CrisisPack]],
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        definition_id = self._reference_id(arguments.get("operation_definition_id", ""))
        targets = [self._reference_id(item) for item in arguments.get("targets", [])]
        description = str(arguments.get("description", "")).strip()
        payload = {
            "operation_definition_id": definition_id,
            "targets": targets,
            "description": description,
        }
        if not description:
            return payload, {"status": "rejected", "code": "missing_description"}
        for crisis_id, pack in active_packs:
            request, code = pack.operation_request(
                lifetime["seat"], definition_id, targets, projection, tick
            )
            if request is not None:
                return (
                    {**payload, "crisis_id": crisis_id},
                    {
                        "status": "accepted",
                        "operation_id": f"operation-{uuid.uuid4().hex[:16]}",
                        "definition_id": request.definition.id,
                        "expected_complete_tick": request.expected_complete_tick,
                        "target_map": request.target_map,
                        "input_state": request.input_state,
                    },
                )
            if code != "unknown_operation":
                return payload, {"status": "rejected", "code": code}
        return payload, {"status": "rejected", "code": "unknown_operation"}

    def _prepare_volume_offer(
        self,
        lifetime: dict[str, Any],
        arguments: dict[str, Any],
        active_packs: list[tuple[str, CrisisPack]],
        projection: dict[str, Any],
        tick: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        action = str(arguments.get("action", "")).strip().upper()
        offer_id = self._reference_id(arguments.get("offer_id", ""))
        recipient = self._reference_id(arguments.get("recipient", ""))
        terms = [dict(item) for item in arguments.get("terms", []) if isinstance(item, dict)]
        try:
            expires_after_days = int(arguments.get("expires_after_days", 0) or 0)
        except (TypeError, ValueError):
            expires_after_days = -1
        payload = {
            "action": action,
            "offer_id": offer_id,
            "recipient": recipient,
            "terms": terms,
            "message": str(arguments.get("message", "")).strip(),
            "expires_after_days": expires_after_days,
        }
        try:
            offer_action = OfferAction(action)
        except ValueError:
            return payload, {"status": "rejected", "code": "invalid_offer_action"}
        if payload["expires_after_days"] < 0:
            return payload, {"status": "rejected", "code": "invalid_offer_expiry"}

        requested: list[AgreementTerm] = []
        if offer_action in {OfferAction.PROPOSE, OfferAction.COUNTER}:
            if not payload["message"] or len(payload["message"]) > 1200:
                return payload, {"status": "rejected", "code": "invalid_offer_message"}
            if len(terms) > 4:
                return payload, {"status": "rejected", "code": "invalid_offer_terms"}
            try:
                requested = [AgreementTerm.model_validate(term) for term in terms]
            except (TypeError, ValueError):
                return payload, {"status": "rejected", "code": "invalid_offer_terms"}

        expires_tick = (
            tick + payload["expires_after_days"] if payload["expires_after_days"] else None
        )
        if expires_tick is not None and expires_tick >= self._volume_horizon():
            return payload, {"status": "rejected", "code": "crosses_volume_boundary"}

        if offer_action == OfferAction.PROPOSE:
            if not recipient:
                return payload, {"status": "rejected", "code": "invalid_offer_recipient"}
            for crisis_id, pack in active_packs:
                validated, code = pack.offer_terms_request(
                    lifetime["seat"], recipient, requested
                )
                if validated is not None:
                    return (
                        {
                            **payload,
                            "crisis_id": crisis_id,
                            "terms": [term.model_dump(mode="json") for term in validated],
                        },
                        {
                            "status": "accepted",
                            "offer_id": f"offer-{uuid.uuid4().hex[:16]}",
                            "created_tick": tick,
                            "expires_tick": expires_tick,
                        },
                    )
                if code != "invalid_offer_recipient":
                    return payload, {"status": "rejected", "code": code}
            return payload, {"status": "rejected", "code": "offer_term_unavailable"}

        offer_context: tuple[str, dict[str, Any], CrisisPack] | None = None
        for crisis_id, pack in active_packs:
            state = projection.get("crisis_instances", {}).get(crisis_id, {})
            offer = next(
                (item for item in state.get("offers", []) if str(item.get("id")) == offer_id),
                None,
            )
            if offer is not None:
                offer_context = (crisis_id, offer, pack)
                break
        if offer_context is None:
            return payload, {"status": "rejected", "code": "unknown_offer"}
        crisis_id, offer, pack = offer_context
        if offer.get("status") != OfferStatus.PROPOSED.value:
            return payload, {"status": "rejected", "code": "offer_not_open"}
        actor_id = lifetime["seat"]
        if offer_action in {OfferAction.ACCEPT, OfferAction.REJECT, OfferAction.COUNTER} and offer.get(
            "recipient"
        ) != actor_id:
            return payload, {"status": "rejected", "code": "offer_response_denied"}
        if offer_action == OfferAction.WITHDRAW and offer.get("issuer") != actor_id:
            return payload, {"status": "rejected", "code": "offer_withdrawal_denied"}
        if offer_action == OfferAction.COUNTER:
            validated, code = pack.offer_terms_request(
                actor_id, str(offer["issuer"]), requested
            )
            if validated is None:
                return payload, {"status": "rejected", "code": code}
            counter_payload = {
                **payload,
                "crisis_id": crisis_id,
                "recipient": str(offer["issuer"]),
                "terms": [term.model_dump(mode="json") for term in validated],
                "parent_offer_id": str(offer["id"]),
            }
            if pack.same_agreement_terms(validated, list(offer.get("terms", []))):
                return counter_payload, {
                    "status": "accepted",
                    "agreement_id": f"agreement-{uuid.uuid4().hex[:16]}",
                    "counter_normalized_to_accept": True,
                }
            return counter_payload, {
                "status": "accepted",
                "offer_id": f"offer-{uuid.uuid4().hex[:16]}",
                "parent_offer_id": str(offer["id"]),
                "created_tick": tick,
                "expires_tick": expires_tick,
            }
        return {**payload, "crisis_id": crisis_id}, {
            "status": "accepted",
            "agreement_id": f"agreement-{uuid.uuid4().hex[:16]}"
            if offer_action == OfferAction.ACCEPT
            else "",
        }

    @staticmethod
    def _reference_id(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            reference = value.get("id", "")
            return reference.strip() if isinstance(reference, str) else ""
        return ""

    def _volume_route_days(self, start: str, end: str) -> int | None:
        if start == end:
            return 0
        edges: dict[str, list[tuple[str, int]]] = {}
        for route in self.pack.world.routes:
            edges.setdefault(route.from_location, []).append((route.to_location, int(route.travel_days)))
        queue: list[tuple[int, str]] = [(0, start)]
        best = {start: 0}
        while queue:
            distance, location = queue.pop(0)
            if location == end:
                return distance
            for target, days in edges.get(location, []):
                candidate = distance + days
                if candidate < best.get(target, 10**9):
                    best[target] = candidate
                    queue.append((candidate, target))
        return None

    def commit_pending_moment(self, worldline_id: str) -> dict[str, Any]:
        """Commit all staged Human and Agent intents in deterministic seat order."""

        row = self._active_worldline(worldline_id)
        tick = int(row["current_tick"])
        projection = self._snapshot_projection(worldline_id, tick)
        pending = projection.get("pending_moment")
        if not pending:
            prior = next(
                (
                    event
                    for event in reversed(self.db.worldline_events(worldline_id))
                    if event["event_type"] == "MOMENT_COMMITTED"
                ),
                None,
            )
            if prior is not None:
                return {
                    "worldline": row,
                    "moment_id": prior["payload"]["moment_id"],
                    "events": [],
                    "idempotent": True,
                }
            raise VolumeRuntimeConflict("there is no Pending Logical Moment")

        staged: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for wake_id in pending["wake_ids"]:
            wake = self.db.crisis_wake(wake_id)
            if wake is None or wake["status"] != "STAGED":
                raise VolumeRuntimeConflict("all Human and Agent intents must be staged first")
            operations = [
                operation
                for operation in self.db.crisis_wake_operations(wake_id)
                if operation["payload"].get("moment_id") == pending["id"]
                and operation["status"] == "PROPOSED"
            ]
            if len(operations) != 1:
                raise VolumeRuntimeConflict("each frozen Wake must have exactly one staged intent")
            lifetime = self._lifetime_for_actor(worldline_id, str(wake["actor_id"]))
            if lifetime is None:
                raise VolumeRuntimeError(f"Wake Lifetime is missing: {wake['actor_id']}")
            staged.append((lifetime, wake, operations[0]))
        staged.sort(key=lambda item: str(item[0]["seat"]))

        events: list[dict[str, Any]] = []
        wake_updates: list[dict[str, Any]] = []
        operation_updates: list[dict[str, Any]] = []
        lifetime_updates: list[dict[str, Any]] = []
        wake_creates: list[dict[str, Any]] = []
        committed_intent_ids: list[str] = []
        for lifetime, wake, operation in staged:
            operation_payload = operation["payload"]
            tool_name = str(operation["tool_name"])
            is_deliberation = tool_name == "commit_deliberation"
            if is_deliberation:
                proposal = dict(operation_payload.get("proposal", {}))
                course_intent = dict(operation_payload.get("course_intent", {}))
                intent = {
                    "type": "deliberation",
                    "outcome": str(proposal.get("outcome", "")),
                    "belief_keys": [
                        str(item.get("subject", ""))
                        for item in course_intent.get("belief_updates", [])
                        if str(item.get("subject", ""))
                    ],
                }
            else:
                proposal = {}
                course_intent = {}
                intent = dict(operation_payload.get("intent", operation_payload))
            if tool_name == "logical_intent":
                tool_name = str(intent.get("type", "wait"))
            elif tool_name == "communicate":
                intent = {
                    "type": "message",
                    "recipient": operation_payload.get("recipient", ""),
                    "content": operation_payload.get("content", ""),
                    "delivery_tick": operation["result"].get("arrival_tick", tick + 1),
                }
                tool_name = "message"
            else:
                intent["type"] = tool_name
            belief_parent_ids = self._belief_parent_ids(
                worldline_id,
                lifetime["seat"],
                intent.get("belief_keys", []),
                events,
            )
            causal_parent_ids = list(
                dict.fromkeys(
                    [
                        *([wake["trigger_event_id"]] if wake["trigger_event_id"] else []),
                        *belief_parent_ids,
                        *(
                            [
                                str(event_id)
                                for event_id in course_intent.get("evidence_event_ids", [])
                                if str(event_id)
                            ]
                            if is_deliberation
                            else []
                        ),
                    ]
                )
            )
            intent_event = self._event(
                worldline_id,
                tick,
                "INTENT_COMMITTED",
                {
                    "moment_id": pending["id"],
                    "wake_id": wake["id"],
                    "seat": lifetime["seat"],
                    "source": operation_payload["source"],
                    "tool": operation["tool_name"],
                    "intent": intent,
                    "belief_keys": list(intent.get("belief_keys", [])),
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=causal_parent_ids,
                event_id=f"{pending['id']}:intent:{lifetime['seat']}:{stable_hash(intent)[:12]}",
                runtime_epoch=row["runtime_epoch"],
            )
            events.append(intent_event)
            committed_intent_ids.append(intent_event["id"])
            outcome: dict[str, Any] = {"status": "committed", "event_id": intent_event["id"]}
            if operation["result"].get("status") == "rejected":
                rejected = self._event(
                    worldline_id,
                    tick,
                    "INTENT_REJECTED",
                    {
                        "moment_id": pending["id"],
                        "wake_id": wake["id"],
                        "seat": lifetime["seat"],
                        "tool": operation["tool_name"],
                        "code": operation["result"].get("code", "rejected"),
                    },
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[intent_event["id"]],
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(rejected)
                outcome = {"status": "rejected", "code": operation["result"].get("code", "rejected")}
            elif is_deliberation:
                outcome.update(
                    self._commit_deliberation(
                        worldline_id,
                        tick,
                        projection,
                        pending,
                        wake,
                        lifetime,
                        operation,
                        intent_event,
                        events,
                        lifetime_updates,
                        wake_creates,
                        row["runtime_epoch"],
                    )
                )
            elif intent["type"] == "update_plan":
                previous_course = current_course_from_plan(
                    list(lifetime.get("plan", [])), fallback_tick=tick
                )
                plan_version = (
                    f"{pending['id']}:course:{lifetime['seat']}:{stable_hash(intent)[:12]}"
                )
                horizon_event_id = f"{intent_event['id']}:decision-horizon"
                plan = build_current_course(
                    intent,
                    course_version=plan_version,
                    tick=tick,
                    event_id=horizon_event_id,
                )
                plan_event = self._event(
                    worldline_id,
                    tick,
                    "PLAN_UPDATED",
                    {
                        "moment_id": pending["id"],
                        "wake_id": wake["id"],
                        "seat": lifetime["seat"],
                        "plan": plan,
                    },
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[intent_event["id"]],
                    event_id=f"{intent_event['id']}:plan",
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(plan_event)
                horizon_event_type = (
                    "DECISION_HORIZON_ESTABLISHED"
                    if previous_course is None
                    else "DECISION_HORIZON_REVISED"
                )
                horizon_event = self._event(
                    worldline_id,
                    tick,
                    horizon_event_type,
                    {
                        "moment_id": pending["id"],
                        "wake_id": wake["id"],
                        "seat": lifetime["seat"],
                        "course": plan,
                        "previous_course_event_id": (
                            str(previous_course.get("established_event_id", ""))
                            if previous_course is not None
                            else ""
                        ),
                    },
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[plan_event["id"]],
                    event_id=horizon_event_id,
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(horizon_event)
                beliefs = dict(lifetime["beliefs"])
                belief_keys: list[str] = []
                for update in intent.get("belief_updates", []):
                    subject = update["subject"]
                    belief = {
                        "assessment": update["assessment"],
                        "confidence": update["confidence"],
                        "updated_tick": tick,
                        "evidence_event_ids": list(update["evidence_event_ids"]),
                    }
                    if update.get("condition"):
                        belief["condition"] = update["condition"]
                    beliefs[subject] = belief
                    belief_keys.append(subject)
                    belief_event = self._event(
                        worldline_id,
                        tick,
                        "BELIEF_UPDATED",
                        {
                            "moment_id": pending["id"],
                            "wake_id": wake["id"],
                            "seat": lifetime["seat"],
                            "belief_key": subject,
                            "belief": belief,
                            "evidence_event_ids": list(update["evidence_event_ids"]),
                        },
                        seat_id=lifetime["seat"],
                        provenance=Provenance.BRANCH_DERIVED.value,
                        causal_parent_ids=[plan_event["id"]],
                        event_id=f"{plan_event['id']}:belief:{stable_hash(update)[:12]}",
                        runtime_epoch=row["runtime_epoch"],
                    )
                    events.append(belief_event)
                lifetime_updates.append(
                    {
                        "id": lifetime["id"],
                        "plan_json": json.dumps([plan], ensure_ascii=False, sort_keys=True),
                        "belief_json": json.dumps(beliefs, ensure_ascii=False, sort_keys=True),
                    }
                )
                outcome.update({"plan_version": plan["version"], "belief_keys": belief_keys})
            elif intent["type"] == "message":
                message = self._logical_message(
                    worldline_id, pending["id"], lifetime["seat"], intent, tick
                )
                if operation["tool_name"] == "communicate" and operation["result"].get("message_id"):
                    message["id"] = str(operation["result"]["message_id"])
                projection.setdefault("messages", []).append(message)
                dispatch = self._event(
                    worldline_id,
                    tick,
                    "MESSAGE_DISPATCHED",
                    message,
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[intent_event["id"]],
                    event_id=f"{pending['id']}:message:{lifetime['seat']}:{stable_hash(intent)[:12]}",
                    runtime_epoch=row["runtime_epoch"],
                )
                message["dispatch_event_id"] = dispatch["id"]
                dispatch["payload"] = message
                events.append(dispatch)
                outcome.update(
                    {"message_id": message["id"], "delivery_tick": message["delivery_tick"]}
                )
            elif intent["type"] == "schedule_revisit":
                revisit = {
                    "id": operation["result"]["revisit_id"],
                    "actor_id": lifetime["seat"],
                    "reason": intent["reason"],
                    "created_tick": tick,
                    "due_tick": int(operation["result"]["due_tick"]),
                    "status": "PENDING",
                    "event_id": f"{intent_event['id']}:revisit",
                }
                revisits = list(lifetime["revisits"])
                revisits.append(revisit)
                revisit_event = self._event(
                    worldline_id,
                    tick,
                    "REVISIT_SCHEDULED",
                    {"moment_id": pending["id"], "wake_id": wake["id"], "revisit": revisit},
                    seat_id=lifetime["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[intent_event["id"]],
                    runtime_epoch=row["runtime_epoch"],
                )
                events.append(revisit_event)
                lifetime_updates.append(
                    {
                        "id": lifetime["id"],
                        "revisits_json": json.dumps(revisits, ensure_ascii=False, sort_keys=True),
                    }
                )
                wake_creates.append(
                    {
                        "id": f"{worldline_id}:wake:{revisit['id']}",
                        "actor_id": lifetime["seat"],
                        "wake_type": "REVISIT_DUE",
                        "tick": revisit["due_tick"],
                        "status": "WAITING_HUMAN" if lifetime["controller"] == "HUMAN" else "QUEUED",
                        "source": "volume-revisit",
                        "trigger_event_id": revisit_event["id"],
                        "result": {"revisit_id": revisit["id"]},
                    }
                )
                outcome.update({"revisit_id": revisit["id"], "due_tick": revisit["due_tick"]})
            elif intent["type"] == "investigate":
                try:
                    self._commit_volume_investigation_start(
                        worldline_id,
                        tick,
                        projection,
                        wake,
                        operation,
                        events,
                        intent_event["id"],
                    )
                except VolumeRuntimeConflict:
                    outcome = self._late_rejection(
                        worldline_id,
                        tick,
                        pending,
                        wake,
                        lifetime,
                        operation,
                        intent_event,
                        events,
                        "commit_conflict",
                        row["runtime_epoch"],
                    )
                else:
                    outcome.update(
                        {
                            "investigation_id": operation["result"].get("investigation_id", ""),
                            "expected_result_tick": operation["result"].get("expected_result_tick"),
                        }
                    )
            elif intent["type"] == "operate":
                try:
                    self._commit_volume_operation_start(
                        worldline_id,
                        tick,
                        projection,
                        wake,
                        operation,
                        events,
                        intent_event["id"],
                    )
                except VolumeRuntimeConflict:
                    outcome = self._late_rejection(
                        worldline_id,
                        tick,
                        pending,
                        wake,
                        lifetime,
                        operation,
                        intent_event,
                        events,
                        "commit_conflict",
                        row["runtime_epoch"],
                    )
                else:
                    outcome.update(
                        {
                            "operation_id": operation["result"].get("operation_id", ""),
                            "expected_complete_tick": operation["result"].get("expected_complete_tick"),
                        }
                    )
            elif intent["type"] == "manage_offer":
                try:
                    self._commit_volume_offer(
                        worldline_id,
                        tick,
                        projection,
                        wake,
                        operation,
                        events,
                        wake_creates,
                        intent_event["id"],
                    )
                except VolumeRuntimeConflict:
                    outcome = self._late_rejection(
                        worldline_id,
                        tick,
                        pending,
                        wake,
                        lifetime,
                        operation,
                        intent_event,
                        events,
                        "commit_conflict",
                        row["runtime_epoch"],
                    )
                else:
                    outcome.update(
                        {
                            "offer_id": operation["result"].get("offer_id", ""),
                            "agreement_id": operation["result"].get("agreement_id", ""),
                        }
                    )
            operation_updates.append(
                {"id": operation["id"], "status": "COMMITTED", "result": outcome}
            )
            wake_updates.append(
                {
                    "id": wake["id"],
                    "status": "COMPLETED",
                    "result": {"moment_id": pending["id"], **outcome},
                }
            )

        moment_event = self._event(
            worldline_id,
            tick,
            "MOMENT_COMMITTED",
            {
                "moment_id": pending["id"],
                "tick": tick,
                "intent_event_ids": committed_intent_ids,
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=committed_intent_ids,
            event_id=f"{pending['id']}:committed",
            runtime_epoch=row["runtime_epoch"],
        )
        events.append(moment_event)
        projection.pop("pending_moment", None)
        projection["last_event_id"] = moment_event["id"]
        self.db.commit_volume_moment(
            worldline_id,
            events,
            current_tick=tick,
            lifetime_updates=lifetime_updates,
            wake_updates=wake_updates,
            wake_creates=wake_creates,
            operation_updates=operation_updates,
            snapshot=projection,
            expected_current_tick=tick,
        )
        return {
            "worldline": self.db.worldline(worldline_id),
            "moment_id": pending["id"],
            "events": events,
            "idempotent": False,
        }

    def _commit_deliberation(
        self,
        worldline_id: str,
        tick: int,
        projection: dict[str, Any],
        pending: dict[str, Any],
        wake: dict[str, Any],
        lifetime: dict[str, Any],
        operation: dict[str, Any],
        intent_event: dict[str, Any],
        events: list[dict[str, Any]],
        lifetime_updates: list[dict[str, Any]],
        wake_creates: list[dict[str, Any]],
        runtime_epoch: str,
    ) -> dict[str, Any]:
        """Apply one already-validated V6 proposal inside the atomic moment."""

        proposal = operation["payload"]["proposal"]
        course_intent = operation["payload"]["course_intent"]
        outcome_name = str(proposal["outcome"])
        evidence_event_ids = [
            str(event_id)
            for event_id in course_intent.get("evidence_event_ids", [])
            if str(event_id)
        ]
        deliberation_event = self._event(
            worldline_id,
            tick,
            "DELIBERATION_COMMITTED",
            {
                "moment_id": pending["id"],
                "wake_id": wake["id"],
                "seat": lifetime["seat"],
                "outcome": outcome_name,
                "evidence_event_ids": evidence_event_ids,
                "world_action_count": 1 if operation["payload"].get("world_action") else 0,
            },
            seat_id=lifetime["seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[intent_event["id"], *evidence_event_ids],
            event_id=f"{intent_event['id']}:deliberation",
            runtime_epoch=runtime_epoch,
        )
        events.append(deliberation_event)

        current_course = current_course_from_plan(
            list(lifetime.get("plan", [])), fallback_tick=tick
        )
        if outcome_name == "HOLD":
            if current_course is None:
                raise VolumeRuntimeConflict("HOLD requires an existing Current Course")
            plan = copy.deepcopy(current_course)
            plan["open_dependencies"] = copy.deepcopy(course_intent["open_dependencies"])
            plan["last_deliberated_tick"] = tick
            plan["last_deliberated_event_id"] = deliberation_event["id"]
            plan["updated_tick"] = tick
            horizon_event = self._event(
                worldline_id,
                tick,
                "DECISION_HORIZON_HELD",
                {
                    "moment_id": pending["id"],
                    "wake_id": wake["id"],
                    "seat": lifetime["seat"],
                    "course": plan,
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[deliberation_event["id"]],
                event_id=f"{deliberation_event['id']}:decision-horizon",
                runtime_epoch=runtime_epoch,
            )
            events.append(horizon_event)
        else:
            horizon_event_id = f"{deliberation_event['id']}:decision-horizon"
            plan = build_current_course(
                course_intent,
                course_version=(
                    f"{pending['id']}:course:{lifetime['seat']}:{stable_hash(course_intent)[:12]}"
                ),
                tick=tick,
                event_id=horizon_event_id,
            )
            plan["last_deliberated_event_id"] = deliberation_event["id"]
            plan_event = self._event(
                worldline_id,
                tick,
                "PLAN_UPDATED",
                {
                    "moment_id": pending["id"],
                    "wake_id": wake["id"],
                    "seat": lifetime["seat"],
                    "plan": plan,
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[deliberation_event["id"]],
                event_id=f"{deliberation_event['id']}:plan",
                runtime_epoch=runtime_epoch,
            )
            events.append(plan_event)
            horizon_event = self._event(
                worldline_id,
                tick,
                "DECISION_HORIZON_ESTABLISHED" if current_course is None else "DECISION_HORIZON_REVISED",
                {
                    "moment_id": pending["id"],
                    "wake_id": wake["id"],
                    "seat": lifetime["seat"],
                    "course": plan,
                    "previous_course_event_id": (
                        str(current_course.get("established_event_id", ""))
                        if current_course is not None
                        else ""
                    ),
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[plan_event["id"]],
                event_id=horizon_event_id,
                runtime_epoch=runtime_epoch,
            )
            events.append(horizon_event)

        beliefs = dict(lifetime["beliefs"])
        belief_keys: list[str] = []
        for update in course_intent.get("belief_updates", []):
            subject = update["subject"]
            belief = {
                "assessment": update["assessment"],
                "confidence": update["confidence"],
                "updated_tick": tick,
                "evidence_event_ids": list(update["evidence_event_ids"]),
            }
            if update.get("condition"):
                belief["condition"] = update["condition"]
            beliefs[subject] = belief
            belief_keys.append(subject)
            belief_event = self._event(
                worldline_id,
                tick,
                "BELIEF_UPDATED",
                {
                    "moment_id": pending["id"],
                    "wake_id": wake["id"],
                    "seat": lifetime["seat"],
                    "belief_key": subject,
                    "belief": belief,
                    "evidence_event_ids": list(update["evidence_event_ids"]),
                },
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[
                    horizon_event["id"],
                    *[str(item) for item in update["evidence_event_ids"]],
                ],
                event_id=f"{horizon_event['id']}:belief:{stable_hash(update)[:12]}",
                runtime_epoch=runtime_epoch,
            )
            events.append(belief_event)
        lifetime_updates.append(
            {
                "id": lifetime["id"],
                "plan_json": json.dumps([plan], ensure_ascii=False, sort_keys=True),
                "belief_json": json.dumps(beliefs, ensure_ascii=False, sort_keys=True),
            }
        )

        action = operation["payload"].get("world_action")
        action_result = {}
        if action:
            action_result = self._commit_deliberation_action(
                worldline_id,
                tick,
                projection,
                wake,
                lifetime,
                action,
                events,
                lifetime_updates,
                wake_creates,
                deliberation_event["id"],
                runtime_epoch,
            )
        return {
            "outcome": outcome_name,
            "deliberation_event_id": deliberation_event["id"],
            "course_event_id": horizon_event["id"],
            "belief_keys": belief_keys,
            **action_result,
        }

    def _commit_deliberation_action(
        self,
        worldline_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        lifetime: dict[str, Any],
        action: dict[str, Any],
        events: list[dict[str, Any]],
        lifetime_updates: list[dict[str, Any]],
        wake_creates: list[dict[str, Any]],
        causal_parent_id: str,
        runtime_epoch: str,
    ) -> dict[str, Any]:
        tool_name = str(action["tool"])
        payload = dict(action["payload"])
        result = dict(action["result"])
        operation = {"tool_name": tool_name, "payload": payload, "result": result}
        if tool_name == "communicate":
            payload["delivery_tick"] = int(result["arrival_tick"])
            message = self._logical_message(
                worldline_id,
                str(wake["frozen_perspective"].get("moment_id", "")),
                lifetime["seat"],
                payload,
                tick,
            )
            message["id"] = str(result["message_id"])
            projection.setdefault("messages", []).append(message)
            dispatch = self._event(
                worldline_id,
                tick,
                "MESSAGE_DISPATCHED",
                message,
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[causal_parent_id],
                event_id=f"{causal_parent_id}:message:{stable_hash(message)[:12]}",
                runtime_epoch=runtime_epoch,
            )
            message["dispatch_event_id"] = dispatch["id"]
            dispatch["payload"] = message
            events.append(dispatch)
            return {
                "world_action_tool": tool_name,
                "message_id": message["id"],
                "delivery_tick": message["delivery_tick"],
            }
        if tool_name == "schedule_revisit":
            revisit = {
                "id": result["revisit_id"],
                "actor_id": lifetime["seat"],
                "reason": payload["reason"],
                "created_tick": tick,
                "due_tick": int(result["due_tick"]),
                "status": "PENDING",
                "event_id": f"{causal_parent_id}:revisit",
            }
            revisits = list(lifetime["revisits"])
            revisits.append(revisit)
            revisit_event = self._event(
                worldline_id,
                tick,
                "REVISIT_SCHEDULED",
                {"wake_id": wake["id"], "revisit": revisit},
                seat_id=lifetime["seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[causal_parent_id],
                runtime_epoch=runtime_epoch,
            )
            events.append(revisit_event)
            lifetime["revisits"] = revisits
            lifetime_updates.append(
                {
                    "id": lifetime["id"],
                    "revisits_json": json.dumps(revisits, ensure_ascii=False, sort_keys=True),
                }
            )
            wake_creates.append(
                {
                    "id": f"{worldline_id}:wake:{revisit['id']}",
                    "actor_id": lifetime["seat"],
                    "wake_type": "REVISIT_DUE",
                    "tick": revisit["due_tick"],
                    "status": "WAITING_HUMAN" if lifetime["controller"] == "HUMAN" else "QUEUED",
                    "source": "volume-revisit",
                    "trigger_event_id": revisit_event["id"],
                    "result": {"revisit_id": revisit["id"]},
                }
            )
            return {
                "world_action_tool": tool_name,
                "revisit_id": revisit["id"],
                "due_tick": revisit["due_tick"],
            }
        if tool_name == "investigate":
            self._commit_volume_investigation_start(
                worldline_id,
                tick,
                projection,
                wake,
                operation,
                events,
                causal_parent_id,
            )
            return {
                "world_action_tool": tool_name,
                "investigation_id": result["investigation_id"],
                "expected_result_tick": result["expected_result_tick"],
            }
        if tool_name == "operate":
            self._commit_volume_operation_start(
                worldline_id,
                tick,
                projection,
                wake,
                operation,
                events,
                causal_parent_id,
            )
            return {
                "world_action_tool": tool_name,
                "operation_id": result["operation_id"],
                "expected_complete_tick": result["expected_complete_tick"],
            }
        self._commit_volume_offer(
            worldline_id,
            tick,
            projection,
            wake,
            operation,
            events,
            wake_creates,
            causal_parent_id,
        )
        return {
            "world_action_tool": tool_name,
            "offer_id": result.get("offer_id", ""),
            "agreement_id": result.get("agreement_id", ""),
        }

    def _late_rejection(
        self,
        worldline_id: str,
        tick: int,
        pending: dict[str, Any],
        wake: dict[str, Any],
        lifetime: dict[str, Any],
        operation: dict[str, Any],
        intent_event: dict[str, Any],
        events: list[dict[str, Any]],
        code: str,
        runtime_epoch: str,
    ) -> dict[str, Any]:
        rejected = self._event(
            worldline_id,
            tick,
            "INTENT_REJECTED",
            {
                "moment_id": pending["id"],
                "wake_id": wake["id"],
                "seat": lifetime["seat"],
                "tool": operation["tool_name"],
                "code": code,
            },
            seat_id=lifetime["seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[intent_event["id"]],
            runtime_epoch=runtime_epoch,
        )
        events.append(rejected)
        return {"status": "rejected", "code": code}

    def _commit_volume_investigation_start(
        self,
        worldline_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        causal_parent_id: str,
    ) -> None:
        payload = operation["payload"]
        result = operation["result"]
        crisis_id = str(payload.get("crisis_id", ""))
        pack = self.pack.pack(crisis_id)
        request, code = pack.investigation_request(
            str(wake["actor_id"]),
            str(payload.get("target", "")),
            str(payload.get("method", "")),
            self._action_projection(projection),
            tick,
        )
        if request is None or request.definition.id != result.get("definition_id"):
            raise VolumeRuntimeConflict(f"investigation became unavailable before commit: {code}")
        state = projection["crisis_instances"][crisis_id]
        visible = (
            sorted(pack.participant_ids)
            if request.definition.visibility.value == "PUBLIC"
            else [str(wake["actor_id"])]
        )
        investigation = {
            "id": result["investigation_id"],
            "definition_id": request.definition.id,
            "actor_id": str(wake["actor_id"]),
            "question": payload["question"],
            "target_id": request.target_id,
            "method": request.definition.method,
            "started_tick": tick,
            "expected_result_tick": request.expected_result_tick,
            "status": "IN_PROGRESS",
            "visibility": request.definition.visibility.value,
            "crisis_id": crisis_id,
        }
        state.setdefault("investigations", []).append(investigation)
        started = self._event(
            worldline_id,
            tick,
            "INVESTIGATION_STARTED",
            {"wake_id": wake["id"], "investigation": investigation, "visibility": visible},
            seat_id=wake["actor_id"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
        )
        investigation["start_event_id"] = started["id"]
        events.append(started)

    def _commit_volume_operation_start(
        self,
        worldline_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        causal_parent_id: str,
    ) -> None:
        payload = operation["payload"]
        result = operation["result"]
        crisis_id = str(payload.get("crisis_id", ""))
        pack = self.pack.pack(crisis_id)
        request, code = pack.operation_request(
            str(wake["actor_id"]),
            str(payload.get("operation_definition_id", "")),
            list(payload.get("targets", [])),
            self._action_projection(projection),
            tick,
        )
        if request is None or request.definition.id != result.get("definition_id"):
            raise VolumeRuntimeConflict(f"operation became unavailable before commit: {code}")
        state = projection["crisis_instances"][crisis_id]
        visible = (
            sorted(pack.participant_ids)
            if request.definition.visibility.value == "PUBLIC"
            else [str(wake["actor_id"])]
        )
        started = {
            "id": result["operation_id"],
            "definition_id": request.definition.id,
            "actor_id": str(wake["actor_id"]),
            "target_ids": list(request.target_ids),
            "target_map": dict(request.target_map),
            "started_tick": tick,
            "expected_complete_tick": request.expected_complete_tick,
            "status": "IN_PROGRESS",
            "visibility": request.definition.visibility.value,
            "interruptibility": request.definition.interruptibility,
            "input_state": dict(request.input_state),
            "result_state": {},
            "description": payload["description"],
            "crisis_id": crisis_id,
        }
        state.setdefault("operations", []).append(started)
        started_event = self._event(
            worldline_id,
            tick,
            "OPERATION_STARTED",
            {"wake_id": wake["id"], "operation": started, "visibility": visible},
            seat_id=wake["actor_id"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
        )
        started["start_event_id"] = started_event["id"]
        events.append(started_event)
        for effect in request.definition.start_effects:
            entity_id = request.target_map.get(effect.subject, effect.subject)
            entity = state["entities"].get(entity_id)
            if entity is None or entity["state"] == effect.state:
                continue
            before = entity["state"]
            entity["state"] = effect.state
            events.append(
                self._event(
                    worldline_id,
                    tick,
                    "ENTITY_STATE_CHANGED",
                    {
                        "operation_id": started["id"],
                        "crisis_id": crisis_id,
                        "entity_id": entity_id,
                        "before": before,
                        "after": effect.state,
                        "phase": "start",
                        "visibility": visible,
                    },
                    seat_id=wake["actor_id"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[started_event["id"]],
                    runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
                )
            )

    def _commit_volume_offer(
        self,
        worldline_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        wake_creates: list[dict[str, Any]],
        causal_parent_id: str,
    ) -> None:
        payload = operation["payload"]
        result = operation["result"]
        crisis_id = str(payload.get("crisis_id", ""))
        state = projection["crisis_instances"][crisis_id]
        offers = state.setdefault("offers", [])
        action = str(payload.get("action", "")).upper()

        def queue_wake(actor_id: str, wake_type: str, trigger_event_id: str, result_data: dict[str, Any]) -> None:
            lifetime = self.db.worldline_lifetime(worldline_id, actor_id)
            if lifetime is None:
                return
            wake_creates.append(
                {
                    "id": f"{worldline_id}:wake:{trigger_event_id}:{actor_id}:{wake_type}",
                    "actor_id": actor_id,
                    "wake_type": wake_type,
                    # Offer/Agreement changes are committed after the current
                    # actor slice.  A same-tick Wake would not be picked up by
                    # the global clock once this Moment is cleared.
                    "tick": tick + 1,
                    "status": "WAITING_HUMAN" if lifetime["controller"] == "HUMAN" else "QUEUED",
                    "source": "volume-offer",
                    "trigger_event_id": trigger_event_id,
                    "result": result_data,
                }
            )

        if action == OfferAction.PROPOSE.value:
            offer = {
                "id": result["offer_id"],
                "issuer": str(wake["actor_id"]),
                "recipient": str(payload["recipient"]),
                "terms": list(payload.get("terms", [])),
                "message": payload.get("message", ""),
                "created_tick": tick,
                "expires_tick": result.get("expires_tick"),
                "status": OfferStatus.PROPOSED.value,
                "visibility": "PRIVATE",
                "crisis_id": crisis_id,
            }
            offers.append(offer)
            proposed = self._event(
                worldline_id,
                tick,
                "OFFER_PROPOSED",
                {
                    "wake_id": wake["id"],
                    "offer": offer,
                    "visibility": sorted({offer["issuer"], offer["recipient"]}),
                },
                seat_id=wake["actor_id"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
            )
            offer["proposal_event_id"] = proposed["id"]
            events.append(proposed)
            queue_wake(
                offer["recipient"],
                "OFFER_CHANGE",
                proposed["id"],
                {"offer_id": offer["id"]},
            )
            return
        offer = next((item for item in offers if str(item.get("id")) == str(payload.get("offer_id"))), None)
        if offer is None or offer.get("status") != OfferStatus.PROPOSED.value:
            raise VolumeRuntimeConflict("offer is no longer open at commit")
        visible = sorted({str(offer["issuer"]), str(offer["recipient"])})
        normalized_counter = action == OfferAction.COUNTER.value and bool(
            result.get("counter_normalized_to_accept")
        )
        if normalized_counter:
            action = OfferAction.ACCEPT.value
        if action == OfferAction.COUNTER.value:
            offer["status"] = OfferStatus.COUNTERED.value
            counter_offer = {
                "id": result["offer_id"],
                "issuer": str(wake["actor_id"]),
                "recipient": str(offer["issuer"]),
                "terms": list(payload.get("terms", [])),
                "message": payload.get("message", ""),
                "created_tick": tick,
                "expires_tick": result.get("expires_tick"),
                "status": OfferStatus.PROPOSED.value,
                "parent_offer_id": offer["id"],
                "visibility": "PRIVATE",
                "crisis_id": crisis_id,
            }
            offers.append(counter_offer)
            countered = self._event(
                worldline_id,
                tick,
                "OFFER_COUNTERED",
                {
                    "wake_id": wake["id"],
                    "offer": offer,
                    "counter_offer": counter_offer,
                    "visibility": visible,
                },
                seat_id=wake["actor_id"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
            )
            offer["counter_event_id"] = countered["id"]
            counter_offer["proposal_event_id"] = countered["id"]
            events.append(countered)
            queue_wake(
                counter_offer["recipient"],
                "OFFER_CHANGE",
                countered["id"],
                {"offer_id": counter_offer["id"]},
            )
            return
        if action == OfferAction.ACCEPT.value:
            offer["status"] = OfferStatus.ACCEPTED.value
            accepted = self._event(
                worldline_id,
                tick,
                "OFFER_ACCEPTED",
                {"wake_id": wake["id"], "offer": offer, "visibility": visible},
                seat_id=wake["actor_id"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
            )
            offer["accept_event_id"] = accepted["id"]
            events.append(accepted)
            agreement = {
                "id": result["agreement_id"],
                "parties": visible,
                "terms": list(offer["terms"]),
                "effective_tick": tick,
                "status": AgreementStatus.ACTIVE.value,
                "source_offer_ids": [offer["id"]],
                "visibility": "PRIVATE",
                "crisis_id": crisis_id,
            }
            state.setdefault("agreements", []).append(agreement)
            created = self._event(
                worldline_id,
                tick,
                "AGREEMENT_CREATED",
                {"wake_id": wake["id"], "agreement": agreement, "visibility": visible},
                seat_id=wake["actor_id"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[accepted["id"]],
                runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
            )
            agreement["creation_event_id"] = created["id"]
            events.append(created)
            for party_id in visible:
                queue_wake(
                    party_id,
                    "AGREEMENT_CHANGE",
                    created["id"],
                    {"agreement_id": agreement["id"]},
                )
            return
        event_type = {
            OfferAction.REJECT.value: "OFFER_REJECTED",
            OfferAction.WITHDRAW.value: "OFFER_WITHDRAWN",
        }.get(action)
        if event_type is None:
            raise VolumeRuntimeError(f"unsupported V5 offer action: {action}")
        offer["status"] = {
            "OFFER_REJECTED": OfferStatus.REJECTED.value,
            "OFFER_WITHDRAWN": OfferStatus.WITHDRAWN.value,
        }[event_type]
        changed = self._event(
            worldline_id,
            tick,
            event_type,
            {"wake_id": wake["id"], "offer": offer, "visibility": visible},
            seat_id=wake["actor_id"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            runtime_epoch=self.db.worldline(worldline_id)["runtime_epoch"],
        )
        offer["status_event_id"] = changed["id"]
        events.append(changed)
        counterpart = offer["issuer"] if action == OfferAction.REJECT.value else offer["recipient"]
        queue_wake(counterpart, "OFFER_CHANGE", changed["id"], {"offer_id": offer["id"]})

    def _active_worldline(self, worldline_id: str) -> dict[str, Any]:
        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise VolumeRuntimeError("VOLUME Worldline not found")
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise VolumeRuntimeConflict("Volume Worldline is sealed")
        return row

    def _lifetime_for_actor(self, worldline_id: str, actor_id: str) -> dict[str, Any] | None:
        return self.db.worldline_lifetime_by_id(
            worldline_id, actor_id
        ) or self.db.worldline_lifetime(worldline_id, actor_id)

    def _belief_parent_ids(
        self,
        worldline_id: str,
        seat: str,
        belief_keys: list[str],
        staged_events: list[dict[str, Any]],
    ) -> list[str]:
        if not belief_keys:
            return []
        events = [*self.db.worldline_events(worldline_id), *staged_events]
        parents: list[str] = []
        for key in dict.fromkeys(str(item) for item in belief_keys):
            event = next(
                (
                    item
                    for item in reversed(events)
                    if item["event_type"] == "BELIEF_UPDATED"
                    and item.get("seat_id") == seat
                    and item.get("payload", {}).get("belief_key") == key
                ),
                None,
            )
            if event is not None:
                parents.append(str(event["id"]))
        return parents

    def _instance_for_crisis(self, worldline_id: str, crisis_id: str) -> dict[str, Any]:
        for instance in self.db.crisis_instances(worldline_id):
            if instance["crisis_id"] == crisis_id:
                return instance
        raise VolumeRuntimeError(f"Crisis Instance not found: {crisis_id}")

    def _snapshot_projection(self, worldline_id: str, tick: int) -> dict[str, Any]:
        snapshot = self.db.worldline_snapshot(worldline_id, tick)
        if snapshot is None:
            raise VolumeRuntimeError("Volume Worldline snapshot is missing")
        return copy.deepcopy(snapshot["projection"])

    def _initial_projection(self, worldline_id: str) -> dict[str, Any]:
        positions = {
            lifetime_id: self.pack.world.resolve_location(definition.starting_location)
            for lifetime_id, definition in self.pack.lifetimes.items()
        }
        shared_entities = {
            entity.id: {
                "id": entity.id,
                "type": entity.type.value,
                "display_name": entity.display_name,
                "state": entity.initial_state,
                "assertion_ids": list(entity.assertion_ids),
            }
            for entity in self.pack.world.entities
        }
        field_events = []
        for index, raw in enumerate(self.pack.world.historical_field):
            field_event = dict(raw)
            field_event.setdefault("id", f"field-{index + 1}")
            field_event["tick"] = int(
                field_event.get("tick", field_event.get("world_tick", index + 1))
            )
            field_event.setdefault("status", "PENDING")
            field_event.setdefault("effects", [])
            field_events.append(field_event)
        crisis_instances = {
            reference.id: self._envelope_projection_state(reference, self.pack.pack(reference.id))
            for reference in self.pack.volume.crises
        }
        return {
            "volume_id": self.volume_id,
            "worldline_id": worldline_id,
            "tick": 0,
            "positions": positions,
            "locations": dict(positions),
            "entities": shared_entities,
            "institutional_state": dict(self.pack.world.institutional_state),
            "messages": [],
            "field_events": field_events,
            "crisis_instances": crisis_instances,
            "active_crisis_ids": [],
            "affordances": {},
            "last_event_id": None,
        }

    def _crisis_state(
        self,
        crisis_id: str,
        pack: CrisisPack,
        activation_tick: int,
    ) -> dict[str, Any]:
        reference = self._envelope_reference(crisis_id)
        entities = {
            entity.id: {
                "id": entity.id,
                "type": entity.type.value,
                "display_name": entity.display_name,
                "state": entity.initial_state,
                "assertion_ids": list(entity.assertion_ids),
            }
            for entity in pack.crisis.entities
        }
        pressures = []
        for pressure in pack.crisis.pressures:
            item = {
                "id": pressure.id,
                "kind": pressure.kind.value,
                "title": pressure.title,
                "description": pressure.description,
                "trigger_tick": pressure.trigger_tick,
                "global_trigger_tick": activation_tick + pressure.trigger_tick,
                "preconditions": [
                    condition.model_dump(mode="json") for condition in pressure.preconditions
                ],
                "effects": [effect.model_dump(mode="json") for effect in pressure.effects],
                "status": "PENDING",
                "visibility": pressure.visibility.value,
                "visible_actor_ids": list(pressure.visible_actor_ids),
                "provenance": pressure.provenance.value,
                "assertion_ids": list(pressure.assertion_ids),
            }
            pressures.append(item)
        available_affordances = {
            "operations": [definition.id for definition in pack.crisis.operations],
            "investigations": [definition.id for definition in pack.crisis.investigations],
            "offers": [
                {
                    "type": term.type.value,
                    "subject": term.subject,
                    "value": term.value,
                    "party_ids": list(term.party_ids),
                }
                for term in pack.crisis.offer_terms
            ],
            "offer_terms": [
                {
                    "type": term.type.value,
                    "subject": term.subject,
                    "value": term.value,
                    "party_ids": list(term.party_ids),
                }
                for term in pack.crisis.offer_terms
            ],
            "pressures": [pressure.id for pressure in pack.crisis.pressures],
        }
        return {
            "crisis_id": crisis_id,
            "status": CrisisInstanceStatus.ACTIVE.value,
            "phase": "OPEN",
            "activation_tick": activation_tick,
            "local_origin_tick": 0,
            "local_tick": 0,
            "participants": list(pack.participant_ids),
            "envelope": {
                "earliest_activation_tick": reference.earliest_activation_tick,
                "activation_preconditions": [
                    item.model_dump(mode="json")
                    for item in reference.activation_preconditions
                ],
                "participants": list(reference.participants or pack.participant_ids),
                "local_horizon": reference.local_horizon,
            },
            "entities": entities,
            "message_ids": [],
            "operations": [],
            "investigations": [],
            "offers": [],
            "agreements": [],
            "available_affordances": available_affordances,
            "pressures": pressures,
            "resolution": {"status": "OPEN"},
            "resolution_reports": [],
            "settlement": {"status": "OPEN"},
        }

    @staticmethod
    def _lifetime_db_id(worldline_id: str, lifetime_id: str) -> str:
        return f"{worldline_id}:lifetime:{lifetime_id}"

    @staticmethod
    def _instance_db_id(worldline_id: str, crisis_id: str) -> str:
        return f"{worldline_id}:crisis:{crisis_id}"

    def _volume_content_hash(self) -> str:
        payload = {
            "volume": self.pack.volume.model_dump(mode="json"),
            "lifetimes": {
                lifetime_id: definition.model_dump(mode="json")
                for lifetime_id, definition in sorted(self.pack.lifetimes.items())
            },
            "world": {
                "locations": [
                    location.model_dump(mode="json") for location in self.pack.world.locations
                ],
                "routes": [route.model_dump(mode="json") for route in self.pack.world.routes],
                "location_aliases": dict(self.pack.world.location_aliases),
                "entities": [entity.model_dump(mode="json") for entity in self.pack.world.entities],
                "institutional_state": dict(self.pack.world.institutional_state),
                "historical_field": list(self.pack.world.historical_field),
            },
            "crises": {
                crisis_id: pack.content_hash for crisis_id, pack in sorted(self.pack.packs.items())
            },
        }
        return stable_hash(payload)

    def _volume_horizon(self) -> int:
        return max(
            [pack.crisis.simulation_boundary.maximum_tick for pack in self.pack.packs.values()]
            or [0]
        )

    @staticmethod
    def _event(
        worldline_id: str,
        tick: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        seat_id: str | None = None,
        provenance: str = "branch_derived",
        causal_parent_ids: list[str] | None = None,
        event_id: str | None = None,
        runtime_epoch: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": event_id or f"wle-{uuid.uuid4().hex[:16]}",
            "worldline_id": worldline_id,
            "tick": int(tick),
            "event_type": event_type,
            "seat_id": seat_id,
            "payload": payload,
            "provenance": provenance,
            "causal_parent_ids": causal_parent_ids or [],
            "runtime_epoch": runtime_epoch,
        }

    @staticmethod
    def _checkpoint_message(crisis_id: str, message: Any, activation_tick: int) -> dict[str, Any]:
        arrival = activation_tick + max(1, int(message.delivery_tick))
        return {
            "id": f"{crisis_id}:{message.id}",
            "source_crisis_id": crisis_id,
            "sender": message.sender,
            "recipient": message.recipient,
            "content": message.content,
            "local_dispatch_tick": int(message.dispatch_tick),
            "dispatch_tick": activation_tick,
            "local_delivery_tick": int(message.delivery_tick),
            "delivery_tick": arrival,
            "arrival_tick": arrival,
            "status": "in_transit",
            "source": "checkpoint",
            "disputed": bool(message.disputed),
            "assertion_ids": list(message.assertion_ids),
        }

    def _normalize_plan_intent(
        self,
        worldline_id: str,
        lifetime: dict[str, Any],
        wake: dict[str, Any],
        intent: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        objective = str(intent.get("objective", "")).strip()
        steps = [str(step).strip() for step in intent.get("steps", []) if str(step).strip()]
        if not objective or not steps:
            raise VolumeRuntimeError("update_plan requires an objective and at least one step")
        rationale = str(intent.get("rationale", "")).strip()
        rationale_source = str(intent.get("rationale_source", "")).strip()
        if source == "human":
            if rationale and rationale_source != "explicit":
                raise VolumeRuntimeConflict("Human rationale must be marked as explicitly stated")
            if not rationale:
                rationale_source = "unstated"
            elif rationale_source != "explicit":
                raise VolumeRuntimeConflict("Human rationale provenance is invalid")
        belief_updates = intent.get("belief_updates", [])
        if not isinstance(belief_updates, list):
            raise VolumeRuntimeError("belief_updates must be a list")
        if source == "human" and belief_updates and intent.get("belief_source") != "explicit":
            raise VolumeRuntimeConflict("Human belief updates must be explicitly stated")
        builder = LifetimeContextBuilder(self.db, self.pack)
        normalized_beliefs: list[dict[str, Any]] = []
        for raw in belief_updates:
            if not isinstance(raw, dict):
                raise VolumeRuntimeError("each belief update must be an object")
            subject = str(raw.get("subject", raw.get("belief_key", ""))).strip()
            assessment = str(raw.get("assessment", "")).strip()
            confidence = raw.get("confidence")
            if not subject or not assessment:
                raise VolumeRuntimeError("belief updates require subject and assessment")
            if not (
                confidence in {"low", "medium", "high"}
                or isinstance(confidence, (int, float))
                and 0 <= float(confidence) <= 1
            ):
                raise VolumeRuntimeError("belief confidence must be low, medium, high, or 0..1")
            evidence_event_ids = builder.validate_evidence(
                worldline_id,
                lifetime["id"],
                raw.get("evidence_event_ids"),
                fallback_event_id=str(wake.get("trigger_event_id", "")),
            )
            item = {
                "subject": subject,
                "assessment": assessment,
                "confidence": confidence,
                "evidence_event_ids": evidence_event_ids,
            }
            if raw.get("condition"):
                item["condition"] = str(raw["condition"]).strip()
            normalized_beliefs.append(item)
        return {
            **intent,
            "objective": objective,
            "steps": steps,
            "rationale": rationale,
            "rationale_source": rationale_source,
            "belief_source": str(intent.get("belief_source", "")).strip(),
            "belief_updates": normalized_beliefs,
            "evidence_event_ids": builder.validate_evidence(
                worldline_id,
                lifetime["id"],
                intent.get("evidence_event_ids"),
                fallback_event_id="",
            ),
            "open_dependencies": self._normalize_open_dependencies(intent, current_tick=int(wake["tick"])),
            "reconsider_when": [
                str(item).strip() for item in intent.get("reconsider_when", []) if str(item).strip()
            ],
        }

    @staticmethod
    def _normalize_open_dependencies(intent: dict[str, Any], *, current_tick: int) -> list[dict[str, Any]]:
        try:
            return normalize_open_dependencies(
                intent.get("open_dependencies", []), current_tick=current_tick
            )
        except DecisionHorizonError as exc:
            raise VolumeRuntimeError(str(exc)) from exc

    def _logical_message(
        self,
        worldline_id: str,
        moment_id: str,
        sender: str,
        intent: dict[str, Any],
        tick: int,
    ) -> dict[str, Any]:
        recipient = str(intent.get("recipient", "")).strip()
        content = str(intent.get("content", "")).strip()
        if not recipient or self.db.worldline_lifetime(worldline_id, recipient) is None:
            raise VolumeRuntimeError(f"unknown message recipient Lifetime: {recipient}")
        if not content:
            raise VolumeRuntimeError("message content is required")
        delivery_tick = int(intent.get("delivery_tick", tick + 1))
        if delivery_tick <= tick:
            raise VolumeRuntimeError("message delivery must be after the current global tick")
        intent_hash = stable_hash(intent)[:12]
        return {
            "id": f"{moment_id}:message:{sender}:{intent_hash}",
            "source_crisis_id": str(intent.get("crisis_id", "")),
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "dispatch_tick": tick,
            "delivery_tick": delivery_tick,
            "arrival_tick": delivery_tick,
            "status": "in_transit",
            "source": "logical_moment",
            "disputed": False,
            "assertion_ids": [],
        }

    @staticmethod
    def _current_state(
        projection: dict[str, Any], crisis: dict[str, Any] | None, subject: str
    ) -> str:
        if crisis is not None and subject in crisis.get("entities", {}):
            return str(crisis["entities"][subject].get("state", ""))
        if subject in projection.get("entities", {}):
            return str(projection["entities"][subject].get("state", ""))
        return str(projection.get("institutional_state", {}).get(subject, ""))

    def _pressure_preconditions_met(
        self, projection: dict[str, Any], crisis: dict[str, Any], pressure: dict[str, Any]
    ) -> bool:
        return all(
            self._current_state(projection, crisis, condition["subject"])
            in condition.get("states", [])
            for condition in pressure.get("preconditions", [])
        )

    @staticmethod
    def _apply_effects(
        projection: dict[str, Any], crisis: dict[str, Any] | None, effects: list[dict[str, Any]]
    ) -> None:
        for effect in effects:
            subject = str(effect.get("subject", effect.get("target", "")))
            state = effect.get("state", effect.get("value", ""))
            if crisis is not None and subject in crisis.get("entities", {}):
                crisis["entities"][subject]["state"] = state
            elif subject in projection.get("entities", {}):
                projection["entities"][subject]["state"] = state
            elif subject:
                projection.setdefault("institutional_state", {})[subject] = state

    def _activation_response(
        self, worldline_id: str, instance: dict[str, Any], *, idempotent: bool
    ) -> dict[str, Any]:
        return {
            "worldline": self.db.worldline(worldline_id),
            "instance": instance,
            "idempotent": idempotent,
            "crisis_instances": self.db.crisis_instances(worldline_id),
        }

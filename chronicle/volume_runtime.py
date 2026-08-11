from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any

from . import hermes
from .crisis import CrisisPack, VolumePack
from .db import content_hash, stable_hash
from .models import CrisisInstanceStatus, Provenance, WorldlineKind, WorldlineStatus
from .subject_continuity import LifetimeContextBuilder

if TYPE_CHECKING:
    from .host import ChronicleHost


class VolumeRuntimeError(ValueError):
    """A user-visible error at the V5 Volume runtime boundary."""


class VolumeRuntimeConflict(VolumeRuntimeError):
    """A V5 Volume operation conflicts with the current global state."""


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
                values, events, lifetime_values, initial_projection
            )
            bindings = []
            for lifetime in lifetime_values:
                metadata = lifetime["profile_metadata"]
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
                            "token_hash": "",
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
        try:
            self.db.commit_volume_moment(
                worldline_id,
                events,
                current_tick=tick,
                instance_creates=[instance],
                snapshot=projection,
                expected_current_tick=tick,
            )
        except sqlite3.IntegrityError as exc:
            raise VolumeRuntimeConflict(
                "Crisis activation raced with another Volume moment"
            ) from exc
        created = self.db.crisis_instance(instance_id) or instance
        return self._activation_response(worldline_id, created, idempotent=False)

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
        candidates.extend(
            int(wake["tick"])
            for wake in self.db.subject_wakes(worldline_id)
            if wake["status"] in {"QUEUED", "WAITING_HUMAN"} and int(wake["tick"]) > current
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
            knowledge = list(lifetime.get("knowledge", []))
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
            if not any(
                isinstance(item, dict) and item.get("message_id") == message["id"]
                for item in knowledge
            ):
                knowledge.append(knowledge_item)
            lifetime_updates[message["recipient"]] = {
                "seat": message["recipient"],
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
            }
            wake_creates.append(
                {
                    "id": f"{worldline_id}:wake:{message['id']}",
                    "actor_id": message["recipient"],
                    "wake_type": "OBSERVATION",
                    "tick": target,
                    "status": "WAITING_HUMAN" if lifetime["controller"] == "HUMAN" else "QUEUED",
                    "source": "volume-message",
                    "trigger_event_id": delivered["id"],
                    "result": {"message_id": message["id"]},
                }
            )

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
        return {
            "worldline": self.db.worldline(worldline_id),
            "instance": self.db.crisis_instance(instance["id"]),
            "event": event,
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
        if wake["status"] not in {"QUEUED", "WAITING_HUMAN", "STAGED"}:
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
        committed_intent_ids: list[str] = []
        for lifetime, wake, operation in staged:
            intent = dict(operation["payload"]["intent"])
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
                    "source": operation["payload"]["source"],
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
            if intent["type"] == "update_plan":
                plan = {
                    "version": f"{pending['id']}:plan:{lifetime['seat']}:{stable_hash(intent)[:12]}",
                    "objective": intent["objective"],
                    "steps": list(intent["steps"]),
                    "rationale": intent["rationale"],
                    "rationale_source": intent.get("rationale_source", ""),
                    "reconsider_when": list(intent.get("reconsider_when", [])),
                    "updated_tick": tick,
                }
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
            "crisis_instances": {},
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
            "reconsider_when": [
                str(item).strip() for item in intent.get("reconsider_when", []) if str(item).strip()
            ],
        }

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

from __future__ import annotations

import difflib
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .config import AppConfig
from .db import ChronicleDB, stable_hash
from .hermes import (
    PROFILE_NAMES,
    HermesClient,
    HermesRuntimeError,
    parse_actor_response,
    probe,
    wake_messages,
)
from .models import ActionType, ActorWakeResponse, BeliefUpdate, BranchAction, Intention, WakeType
from .scenario import ScenarioPack


class ProtocolViolation(RuntimeError):
    pass


class ChronicleHost:
    """Deterministic owner of Chronicle time, truth, delivery, and records."""

    def __init__(self, config: AppConfig, db: ChronicleDB | None = None, pack: ScenarioPack | None = None):
        self.config = config
        self.db = db or ChronicleDB(config.database_path)
        self.pack = pack or ScenarioPack.load(config.scenario_path)
        from .runtime import WorldlineRuntime

        self.worldline_runtime = WorldlineRuntime(self)
        self.worldline_runtime.ensure_canon_worldline()

    @property
    def current_tick(self) -> int:
        return int(self.db.get_meta("canon_tick", str(self.pack.manifest.start_tick)))

    def set_tick(self, tick: int) -> int:
        if not self.pack.manifest.start_tick <= tick <= self.pack.manifest.end_tick:
            raise ValueError("tick outside the Canon window")
        if tick < self.current_tick:
            raise ValueError("Chronicle time cannot move backwards")
        if tick != self.current_tick and self.db.active_human_worldline() is not None:
            raise ValueError("Canon advancement is locked while a human Worldline is active")
        self.db.set_meta("canon_tick", str(tick))
        self.worldline_runtime.ensure_canon_worldline()
        return tick

    def reset_for_test(self) -> None:
        self.db.set_meta("canon_tick", str(self.pack.manifest.start_tick))
        self.worldline_runtime.ensure_canon_worldline()

    def world_state(self, tick: int | None = None) -> dict[str, Any]:
        tick = self.current_tick if tick is None else tick
        state: dict[str, Any] = {
            "tick": tick,
            "location_control": {},
            "route_pressure": {},
            "capital_status": "standing",
            "command_state": "active",
            "force_posture": {},
            "information_state": {},
            "season": {},
            "court_decision": {},
            "relief_order": {},
            "supply_state": {},
            "command_conflict": {},
            "belief_pressure": {},
            "simulation_boundary": False,
            "effects": {},
            "last_event_id": None,
        }
        for event in self.pack.event_at_or_before(tick):
            state["last_event_id"] = event.id
            for effect in event.world_effects:
                state["effects"].setdefault(effect.type, {})[effect.target] = effect.value
                if effect.type == "control_change":
                    state["location_control"][effect.target] = effect.value
                elif effect.type == "route_pressure":
                    state["route_pressure"][effect.target] = effect.value
                elif effect.type == "capital_status":
                    state["capital_status"] = effect.value
                elif effect.type == "command_state":
                    state["command_state"] = effect.value
                elif effect.type in {"force_posture", "force_readiness"}:
                    state["force_posture"][effect.target] = effect.value
                elif effect.type in {"information_state", "capital_security"}:
                    state["information_state"][effect.target] = effect.value
                elif effect.type in {
                    "season_open",
                    "court_decision",
                    "relief_order",
                    "supply_state",
                    "command_conflict",
                    "belief_pressure",
                }:
                    projection = {
                        "season_open": "season",
                        "court_decision": "court_decision",
                        "relief_order": "relief_order",
                        "supply_state": "supply_state",
                        "command_conflict": "command_conflict",
                        "belief_pressure": "belief_pressure",
                    }[effect.type]
                    state[projection][effect.target] = effect.value
                elif effect.type == "simulation_boundary":
                    state["simulation_boundary"] = bool(effect.value)
        return state

    def timeline(self, tick: int | None = None) -> list[dict[str, Any]]:
        tick = self.current_tick if tick is None else tick
        items: list[dict[str, Any]] = []
        for event in self.pack.events:
            assertion = self.pack.assertion_by_id.get(event.assertion_ids[0])
            items.append(
                {
                    "id": event.id,
                    "tick": event.tick,
                    "native_date": event.native_date,
                    "title": event.title,
                    "marker": event.marker.value,
                    "tags": event.tags,
                    "is_current": event.tick == tick,
                    "is_past": event.tick <= tick,
                    "has_fork": event.id == self.pack.fork.event_id,
                    "assertion_id": assertion.id if assertion else None,
                }
            )
        return items

    def event_detail(self, event_id: str, tick: int | None = None) -> dict[str, Any]:
        event = self.pack.event_by_id[event_id]
        tick = self.current_tick if tick is None else tick
        assertions = [self.pack.assertion_by_id[item].model_dump(mode="json") for item in event.assertion_ids]
        observations: dict[str, list[dict[str, Any]]] = {}
        for seat in self.pack.actor_by_seat:
            observations[seat] = [
                {
                    **observation.model_dump(mode="json"),
                    "delivered": observation.delivery_tick <= tick,
                    "display_event": event.title,
                }
                for observation in event.observations.get(seat, [])
            ]
        return {
            "event": event.model_dump(mode="json"),
            "assertions": assertions,
            "observations": observations,
            "who_knows": {
                assertion_id: self.pack.who_knows(assertion_id, tick) for assertion_id in event.assertion_ids
            },
            "is_fork": event.id == self.pack.fork.event_id,
        }

    def who_knows(self, tick: int | None = None) -> list[dict[str, Any]]:
        tick = self.current_tick if tick is None else tick
        result: list[dict[str, Any]] = []
        for actor in self.pack.actors:
            observations = self.pack.observations_for(actor.seat, tick)
            result.append(
                {
                    "seat": actor.seat,
                    "display_name": actor.display_name,
                    "runtime_alias": actor.runtime_alias,
                    "observation_count": len(observations),
                    "last_observation_tick": observations[-1][1].delivery_tick if observations else None,
                    "known_assertions": sorted({ob.origin_assertion_id for _, ob in observations}),
                }
            )
        return result

    def source_detail(self, assertion_id: str) -> dict[str, Any]:
        assertion = self.pack.assertion_by_id[assertion_id]
        sources = [source.model_dump(mode="json") for source in self.pack.sources if source.id in assertion.source_ids]
        return {"assertion": assertion.model_dump(mode="json"), "sources": sources}

    def lifetime(self, seat: str) -> dict[str, Any]:
        actor = self.pack.actor_by_seat[seat]
        native_text, native_hash = self._native_memory(seat)
        if self._native_memory_path(seat).exists():
            memory_text, memory_hash = native_text, native_hash
        else:
            memory_text, memory_hash = self.db.current_memory(seat)
        records = self.db.life_records(seat)
        beliefs = self.db.current_beliefs(seat)
        return {
            "actor": actor.model_dump(mode="json"),
            "records": records,
            "beliefs": beliefs,
            "memory": {
                "text": memory_text,
                "hash": memory_hash,
                "versions": self.db.memory_versions(seat),
            },
            "wake_sessions": self.db.wake_sessions(seat),
            "stats": {
                "observations": len({item for record in records for item in record["observation_ids"]}),
                "intentions": sum(len(record["intentions"]) for record in records),
                "memories": len(self.db.memory_versions(seat)),
            },
        }

    def _runtime_env(self) -> dict[str, str]:
        path = self.config.runtime_env_path
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
        return values

    def _profile_key(self, profile: str) -> str:
        return self._runtime_env().get(f"CHRONICLE_{profile.upper().replace('-', '_')}_API_SERVER_KEY", "")

    def _native_memory_path(self, seat: str) -> Path:
        profile = PROFILE_NAMES[seat]
        return self.config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"

    def _native_memory(self, seat: str) -> tuple[str, str]:
        path = self._native_memory_path(seat)
        if not path.exists():
            return "", hashlib.sha256(b"").hexdigest()
        text = path.read_text(encoding="utf-8")
        return text, hashlib.sha256(path.read_bytes()).hexdigest()

    def _restore_native_memory(self, seat: str, existed: bool, text: str) -> None:
        path = self._native_memory_path(seat)
        if existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif path.exists():
            path.unlink()

    def _record_native_memory_violation(
        self,
        *,
        seat: str,
        tick: int,
        wake_type: WakeType,
        epoch: str,
        before_text: str,
        before_hash: str,
        before_exists: bool,
        after_text: str,
        after_hash: str,
        reason: str,
    ) -> str:
        diff = "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile="memory.before",
                tofile="memory.after",
            )
        )
        try:
            self._restore_native_memory(seat, before_exists, before_text)
            _restored_text, restored_hash = self._native_memory(seat)
            if restored_hash != before_hash:
                raise OSError("restored Memory hash does not match the snapshot")
        except OSError as exc:
            self.db.add_protocol_violation(
                {
                    "seat": seat,
                    "tick": tick,
                    "wake_type": wake_type.value,
                    "reason": f"{reason}; rollback failed",
                    "memory_hash_before": before_hash,
                    "memory_hash_after": after_hash,
                    "memory_diff": diff,
                    "action": "rollback_failed",
                    "runtime_epoch": epoch,
                }
            )
            raise HermesRuntimeError("Hermes Memory rollback failed") from exc
        self.db.add_protocol_violation(
            {
                "seat": seat,
                "tick": tick,
                "wake_type": wake_type.value,
                "reason": reason,
                "memory_hash_before": before_hash,
                "memory_hash_after": restored_hash,
                "memory_diff": diff,
                "action": "rollback",
                "runtime_epoch": epoch,
            }
        )
        return restored_hash

    def _compensate_native_memory_failure(
        self,
        *,
        seat: str,
        tick: int,
        wake_type: WakeType,
        epoch: str,
        before_text: str,
        before_hash: str,
        before_exists: bool,
        reason: str,
    ) -> None:
        try:
            after_text, after_hash = self._native_memory(seat)
        except OSError as exc:
            raise HermesRuntimeError("Hermes Memory could not be inspected after wake failure") from exc
        if after_hash == before_hash:
            return
        self._record_native_memory_violation(
            seat=seat,
            tick=tick,
            wake_type=wake_type,
            epoch=epoch,
            before_text=before_text,
            before_hash=before_hash,
            before_exists=before_exists,
            after_text=after_text,
            after_hash=after_hash,
            reason=reason,
        )

    def _epoch(self) -> str:
        soul = self.config.root / "hermes" / "chronicle-actor" / "SOUL.md"
        skill = self.config.root / "hermes" / "chronicle-actor" / "skills" / "chronicle-actor-protocol" / "SKILL.md"
        toolset = "memory"
        values = {
            "hermes_version": self._hermes_version(),
            "provider_base_url_hash": self.config.provider_hash(),
            "model": self.config.llm_model or "fixture",
            "api_mode": self.config.llm_api_mode,
            "reasoning_effort": self.config.llm_reasoning_effort,
            "soul_hash": _file_hash(soul),
            "skill_hash": _file_hash(skill),
            "toolset_hash": stable_hash(toolset),
        }
        return self.db.ensure_epoch(values)

    def _hermes_version(self) -> str:
        try:
            from .hermes import cli_version

            return cli_version(self.config)
        except Exception:
            return "unavailable"

    def _runtime_input(
        self, seat: str, tick: int, wake_type: WakeType, outcome: str = "", *, live: bool = False
    ) -> dict[str, Any]:
        actor = self.pack.actor_by_seat[seat]
        observations = [
            {
                "id": observation.id,
                "received_at": observation.delivery_tick,
                "channel": observation.channel,
                "source_alias": observation.source_alias,
                "reliability_hint": observation.reliability_hint,
                "payload": observation.runtime_payload,
            }
            for _, observation in self.pack.observations_for(seat, tick)
        ]
        memory_text, _ = self.db.current_memory(seat)
        if live and self._profile_key(PROFILE_NAMES[seat]):
            native_text, _ = self._native_memory(seat)
            if native_text:
                memory_text = native_text
        return {
            "seat": actor.runtime_alias,
            "tick": tick,
            "wake_type": wake_type.value,
            "allowed_intents": [item.value for item in actor.authority],
            "observations": observations,
            "current_beliefs": self.db.current_beliefs(seat),
            "subjective_memory": memory_text,
            "reflection_outcome": outcome if wake_type == WakeType.REFLECTION else "",
        }

    def wake(
        self,
        seat: str,
        tick: int | None = None,
        wake_type: WakeType = WakeType.OBSERVATION,
        *,
        live: bool = False,
        outcome: str = "",
    ) -> dict[str, Any]:
        if seat not in self.pack.actor_by_seat:
            raise ValueError(f"unknown Seat {seat}")
        tick = self.current_tick if tick is None else tick
        profile = PROFILE_NAMES[seat]
        use_native_memory = live and self.config.llm_configured and bool(self._profile_key(profile))
        runtime_input = self._runtime_input(seat, tick, wake_type, outcome, live=live)
        epoch = self._epoch()
        before_beliefs = self.db.current_beliefs(seat)
        if use_native_memory:
            memory_before, memory_hash_before = self._native_memory(seat)
            memory_existed_before = self._native_memory_path(seat).exists()
        else:
            memory_before, memory_hash_before = self.db.current_memory(seat)
            memory_existed_before = False
        source = "fixture"
        session_id: str | None = None
        response: ActorWakeResponse
        protocol_error = ""
        if live:
            if not self.config.llm_configured:
                raise HermesRuntimeError("live Hermes is not configured")
            key = self._profile_key(profile)
            if not key:
                raise HermesRuntimeError("live Hermes Profile key is not configured")
            readiness = probe(self.config, [profile])
            if not readiness.ready_for(profile):
                raise HermesRuntimeError("live Hermes readiness check failed")
            client = HermesClient(self.config)
            wake_id = f"{seat.lower()}-{tick}-{wake_type.value}"
            session_id = client.create_fresh_session(profile, key, wake_id)
            if not session_id:
                raise HermesRuntimeError("live Hermes Fresh Session is unavailable")
            try:
                raw, session_id = client.chat(
                    profile,
                    key,
                    wake_messages(runtime_input, wake_type.value),
                    session_id,
                    f"chronicle:{seat}",
                )
                response = parse_actor_response(raw)
                source = "hermes"
            except Exception as exc:
                if use_native_memory:
                    self._compensate_native_memory_failure(
                        seat=seat,
                        tick=tick,
                        wake_type=wake_type,
                        epoch=epoch,
                        before_text=memory_before,
                        before_hash=memory_hash_before,
                        before_exists=memory_existed_before,
                        reason="live Hermes wake failed after a native Memory mutation",
                    )
                raise HermesRuntimeError("live Hermes wake failed") from exc
        else:
            response = self._fixture_response(seat, tick, wake_type, runtime_input, outcome)

        life_id = f"life-{uuid.uuid4().hex[:12]}"
        memory_hash_after = memory_hash_before
        memory_record: dict[str, Any] | None = None
        if wake_type != WakeType.REFLECTION and response.memory_action not in {"NO_CHANGE", ""}:
            protocol_error = protocol_error or "normal wake proposed a memory mutation"
            response = response.model_copy(update={"memory_action": "NO_CHANGE", "memory_text": ""})
            self.db.add_protocol_violation(
                {
                    "seat": seat,
                    "tick": tick,
                    "wake_type": wake_type.value,
                    "reason": protocol_error,
                    "memory_hash_before": memory_hash_before,
                    "memory_hash_after": memory_hash_before,
                    "action": "blocked",
                    "runtime_epoch": epoch,
                }
            )
        if use_native_memory:
            native_after_text, native_after_hash = self._native_memory(seat)
            native_changed = native_after_hash != memory_hash_before
            memory_hash_after = native_after_hash
            if wake_type != WakeType.REFLECTION and native_changed:
                protocol_error = protocol_error or "ordinary wake mutated Hermes Memory"
                memory_hash_after = self._record_native_memory_violation(
                    seat=seat,
                    tick=tick,
                    wake_type=wake_type,
                    epoch=epoch,
                    before_text=memory_before,
                    before_hash=memory_hash_before,
                    before_exists=memory_existed_before,
                    after_text=native_after_text,
                    after_hash=native_after_hash,
                    reason=protocol_error,
                )
            elif wake_type == WakeType.REFLECTION and response.memory_action == "UPDATE_MEMORY":
                if not native_changed:
                    protocol_error = protocol_error or "reflection requested memory update but Hermes Memory did not change"
                    self.db.add_protocol_violation(
                        {
                            "seat": seat,
                            "tick": tick,
                            "wake_type": wake_type.value,
                            "reason": protocol_error,
                            "memory_hash_before": memory_hash_before,
                            "memory_hash_after": memory_hash_after,
                            "action": "blocked",
                            "runtime_epoch": epoch,
                        }
                    )
                else:
                    try:
                        memory_record = self.db.add_memory_version(
                            seat,
                            native_after_text,
                            memory_hash_before,
                            [life_id],
                            "reflection",
                            memory_hash=native_after_hash,
                        )
                    except ValueError as exc:
                        protocol_error = str(exc)
                        memory_hash_after = self._record_native_memory_violation(
                            seat=seat,
                            tick=tick,
                            wake_type=wake_type,
                            epoch=epoch,
                            before_text=memory_before,
                            before_hash=memory_hash_before,
                            before_exists=memory_existed_before,
                            after_text=native_after_text,
                            after_hash=native_after_hash,
                            reason=protocol_error,
                        )
            elif wake_type == WakeType.REFLECTION and native_changed:
                protocol_error = protocol_error or "Hermes Memory changed without UPDATE_MEMORY"
                memory_hash_after = self._record_native_memory_violation(
                    seat=seat,
                    tick=tick,
                    wake_type=wake_type,
                    epoch=epoch,
                    before_text=memory_before,
                    before_hash=memory_hash_before,
                    before_exists=memory_existed_before,
                    after_text=native_after_text,
                    after_hash=native_after_hash,
                    reason=protocol_error,
                )
        elif wake_type == WakeType.REFLECTION and response.memory_action == "UPDATE_MEMORY" and response.memory_text.strip():
            memory_record = self.db.add_memory_version(
                seat,
                response.memory_text.strip(),
                memory_hash_before,
                [life_id],
                "reflection",
            )
            memory_hash_after = memory_record["memory_hash"]
        elif wake_type == WakeType.REFLECTION and response.memory_action not in {"NO_CHANGE", "UPDATE_MEMORY", ""}:
            protocol_error = protocol_error or "reflection returned an unsupported memory action"

        updates = [item.model_dump(mode="json") for item in response.belief_updates]
        self.db.update_beliefs(seat, tick, updates)
        after_beliefs = self.db.current_beliefs(seat)

        observation_ids = [item[1].id for item in self.pack.observations_for(seat, tick)]
        self.db.append_life_record(
            {
                "id": life_id,
                "seat": seat,
                "tick": tick,
                "wake_type": wake_type.value,
                "observation_ids": observation_ids,
                "belief_before": before_beliefs,
                "belief_after": after_beliefs,
                "intentions": [item.model_dump(mode="json") for item in response.intentions],
                "memory_hash_before": memory_hash_before,
                "memory_hash_after": memory_hash_after,
                "runtime_epoch": epoch,
            }
        )
        self.db.add_wake_session(
            {
                "id": f"wake-{uuid.uuid4().hex[:12]}",
                "seat": seat,
                "wake_type": wake_type.value,
                "hermes_session_id": session_id,
                "source": source,
                "runtime_epoch": epoch,
                "status": "protocol_violation" if protocol_error else "completed",
            }
        )
        return {
            "life_record_id": life_id,
            "seat": seat,
            "tick": tick,
            "wake_type": wake_type.value,
            "source": source,
            "hermes_session_id": session_id,
            "runtime_epoch": epoch,
            "response": response.model_dump(mode="json"),
            "protocol_error": protocol_error,
            "memory": {"before_hash": memory_hash_before, "after_hash": memory_hash_after, "changed": memory_hash_before != memory_hash_after},
            "runtime_input_summary": {
                "observation_count": len(runtime_input["observations"]),
                "allowed_intents": runtime_input["allowed_intents"],
                "memory_source": "hermes" if use_native_memory else "fixture",
            },
        }

    def _fixture_response(
        self, seat: str, tick: int, wake_type: WakeType, runtime_input: dict[str, Any], outcome: str
    ) -> ActorWakeResponse:
        observations = runtime_input["observations"]
        payload = " ".join(item["payload"] for item in observations[-4:])
        lower = payload.casefold()
        pressure = any(word in lower for word in ("fallen", "failing", "broken", "exposed", "immediate"))
        direction = "down" if pressure else "up"
        confidence = min(0.92, 0.36 + (len(observations) * 0.025))
        if wake_type == WakeType.REFLECTION:
            lesson = "A delayed report can still be correct; its delivery time is part of the decision."
            if outcome:
                lesson = f"{outcome[:120]} Keep the timing and source limits visible in future judgments."
            return ActorWakeResponse(
                assessment="A later result changes how the earlier report should be weighted.",
                belief_updates=[BeliefUpdate(belief_key="report_timing", direction="up", confidence=0.72, statement="Timing affects trust and action." )],
                intentions=[Intention(action=ActionType.WAIT, reason="Reassess after reflection")],
                uncertainties=["The next report may still arrive too late."],
                memory_action="UPDATE_MEMORY",
                memory_text=lesson,
            )
        action = ActionType.WAIT
        if seat == "A" and pressure:
            action = ActionType.ISSUE_ORDER
        elif seat == "B" and pressure:
            action = ActionType.PREPARE_MOVEMENT
        elif seat == "C" and pressure:
            action = ActionType.REQUEST_INFORMATION
        return ActorWakeResponse(
            assessment=(
                "The received reports suggest a worsening northern position, but their sequence remains incomplete."
                if pressure
                else "The received reports are insufficient to establish a stable picture of the wider road."
            ),
            belief_updates=[
                BeliefUpdate(
                    belief_key="northern_route_stability",
                    direction=direction,
                    confidence=confidence,
                    statement="The northern route is not yet a stable basis for certainty." if pressure else "The route may still hold, but evidence is partial.",
                )
            ],
            intentions=[Intention(action=action, target="Capital" if action == ActionType.ISSUE_ORDER else "", reason="Act only within the received picture")],
            uncertainties=["The unseen side of the route", "Whether the next report will arrive in time"],
        )


def _file_hash(path: Path) -> str:
    if not path.exists():
        return stable_hash("")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BranchEngine:
    def __init__(self, host: ChronicleHost):
        self.host = host

    def create(self) -> dict[str, Any]:
        fork = self.host.pack.fork
        event = self.host.pack.event_by_id[fork.event_id]
        if self.host.current_tick < event.tick:
            raise ValueError("branch is unavailable before the fork tick")
        if self.host.db.branch_for_fork(fork.id) is not None:
            raise ValueError("branch already exists for this fork")
        state = {
            "premise": fork.runtime_premise,
            "fork_tick": event.tick,
            "tick": event.tick,
            "day_offset": 0,
            "world": self.host.world_state(event.tick),
            "orders": [],
            "messages": [],
            "locations": {actor.seat: actor.initial_location for actor in self.host.pack.actors},
            "differences": [{"label": "Premise", "value": fork.display_name, "provenance": "branch_derived"}],
        }
        branch_id = self.host.db.create_branch(fork.id, event.tick, state)
        return self.host.db.branch(branch_id) or {}

    def step(self, branch_id: str, seat: str, action: BranchAction) -> dict[str, Any]:
        branch = self.host.db.branch(branch_id)
        if branch is None:
            raise ValueError("branch not found")
        if branch["status"] != "active":
            raise ValueError("branch is no longer active")
        actor = self.host.pack.actor_by_seat.get(seat)
        if actor is None:
            raise ValueError("unknown Seat")
        state = branch["state_json"]
        result = self._validate(actor, state, action)
        if result["status"] == "rejected":
            self.host.db.add_branch_record(branch_id, branch["tick"], seat, action.model_dump(mode="json"), result)
            return {"branch": branch, "result": result}

        next_tick = branch["tick"] + 1
        state = json.loads(json.dumps(state, ensure_ascii=False))
        state["tick"] = next_tick
        state["day_offset"] = next_tick - state["fork_tick"]
        if action.type == ActionType.SEND_MESSAGE:
            route = self._route_between(state["locations"][seat], state["locations"][action.recipient])
            state["messages"].append(
                {
                    "from": seat,
                    "recipient": action.recipient,
                    "payload": action.payload,
                    "delivery_tick": next_tick + route.travel_days,
                    "status": "in_transit",
                }
            )
        elif action.type == ActionType.ISSUE_ORDER:
            state["orders"].append({"from": seat, "target": action.target, "payload": action.payload, "status": "accepted"})
        elif action.type in {ActionType.MOVE_PRINCIPAL, ActionType.PREPARE_MOVEMENT, ActionType.REDEPLOY_FORCE}:
            state["locations"][seat] = action.target
        state["world"]["tick"] = next_tick
        state["world"]["branch_locations"] = state["locations"]
        state["world"]["branch_orders"] = state["orders"]
        state["world"]["branch_messages"] = state["messages"]
        boundary_reason = ""
        status = "active"
        if state["day_offset"] >= self.host.pack.fork.max_days:
            status = "boundary"
            boundary_reason = "14 simulated days reached"
        result["tick"] = next_tick
        self.host.db.update_branch(branch_id, tick=next_tick, state=state, status=status, boundary_reason=boundary_reason)
        self.host.db.add_branch_record(branch_id, next_tick, seat, action.model_dump(mode="json"), result)
        return {"branch": self.host.db.branch(branch_id), "result": result}

    def _validate(self, actor: Any, state: dict[str, Any], action: BranchAction) -> dict[str, Any]:
        if action.type not in actor.authority:
            return {"status": "rejected", "reason": "Seat authority does not include this action"}
        if action.type == ActionType.SEND_MESSAGE and (not action.recipient or not action.payload):
            return {"status": "rejected", "reason": "recipient and payload are required"}
        if action.type == ActionType.SEND_MESSAGE:
            if action.recipient not in self.host.pack.actor_by_seat or action.recipient == actor.seat:
                return {"status": "rejected", "reason": "recipient must be another known Seat"}
            try:
                self._route_between(state["locations"][actor.seat], state["locations"][action.recipient])
            except ValueError as exc:
                return {"status": "rejected", "reason": str(exc)}
        if action.type in {ActionType.MOVE_PRINCIPAL, ActionType.PREPARE_MOVEMENT, ActionType.REDEPLOY_FORCE}:
            if action.target not in self.host.pack.location_by_id:
                return {"status": "rejected", "reason": "target is not a known location"}
            if action.target == state["locations"][actor.seat]:
                return {"status": "rejected", "reason": "target is already the current location"}
            try:
                self._route_between(state["locations"][actor.seat], action.target)
            except ValueError as exc:
                return {"status": "rejected", "reason": str(exc)}
        if action.type == ActionType.ISSUE_ORDER and not action.payload:
            return {"status": "rejected", "reason": "an order needs a payload"}
        return {"status": "accepted", "provenance": "branch_derived", "message": "Host accepted the intention and advanced one simulated day"}

    def _route_between(self, origin: str, destination: str) -> Any:
        for route in self.host.pack.routes:
            if {route.from_location, route.to_location} == {origin, destination}:
                return route
        raise ValueError("no defined route connects the current locations")

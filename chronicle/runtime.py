from __future__ import annotations

import difflib
import json
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any

from . import hermes
from .db import stable_hash
from .interaction import CompiledInput, IntentCompiler
from .models import (
    ACTION_CAUSAL_ENVELOPE,
    ActionType,
    ActionValidation,
    ActorWakeResponse,
    BranchAction,
    Controller,
    InteractionResult,
    Provenance,
    SeatContextView,
    WorldlineKind,
    WorldlineStatus,
)
from .worldline import descendant_events, project_canon, project_worldline

if TYPE_CHECKING:
    from .host import ChronicleHost


class WorldlineError(ValueError):
    """A user-visible error at the Chronicle V2 worldline boundary."""


class WorldlineConflict(WorldlineError):
    """The requested operation conflicts with a sealed or active worldline."""


class WorldlineRuntime:
    """Owns V2 worldline lifecycle without changing the V1 BranchEngine contract."""

    def __init__(self, host: ChronicleHost):
        self.host = host
        self.db = host.db
        self.pack = host.pack
        self.compiler = IntentCompiler()

    @property
    def canon_id(self) -> str:
        return f"canon-{self.pack.manifest.id}"

    def ensure_canon_worldline(self) -> dict[str, Any]:
        row = self.db.worldline(self.canon_id)
        if row is None:
            row = self.db.create_worldline(
                {
                    "id": self.canon_id,
                    "scenario_id": self.pack.manifest.id,
                    "kind": WorldlineKind.CANON.value,
                    "status": WorldlineStatus.ACTIVE.value,
                    "current_tick": self.host.current_tick,
                    "runtime_epoch": "source-pack",
                }
            )
        existing_ids = {event["id"] for event in self.db.worldline_events(self.canon_id)}
        for event in self.pack.events:
            event_id = f"{self.canon_id}:canon:{event.id}"
            if event_id in existing_ids:
                continue
            self.db.append_worldline_event(
                self.canon_id,
                event.tick,
                "CANON_EVENT",
                {
                    "event_id": event.id,
                    "native_date": event.native_date,
                    "title": event.title,
                    "assertion_ids": event.assertion_ids,
                    "branch_policy": event.branch_policy.value,
                    "world_effects": [item.model_dump(mode="json") for item in event.world_effects],
                },
                provenance=Provenance.HISTORICAL.value,
                event_id=event_id,
            )
        current_tick = self.host.current_tick
        if int(row["current_tick"]) != current_tick:
            self.db.update_worldline(self.canon_id, current_tick=current_tick)
        snapshot = self.db.worldline_snapshot(self.canon_id, current_tick)
        if snapshot is None or int(snapshot["ledger_cursor"]) < self._ledger_cursor(self.canon_id):
            projection = project_canon(self.pack.events, current_tick)
            self.db.append_worldline_snapshot(
                self.canon_id,
                current_tick,
                self._ledger_cursor(self.canon_id),
                projection,
            )
        return self.db.worldline(self.canon_id) or row

    def next_canon_tick(self) -> int | None:
        current = self.host.current_tick
        future = [event.tick for event in self.pack.events if event.tick > current]
        return min(future) if future else None

    def advance_canon_next(self) -> dict[str, Any]:
        self._assert_archivist_open()
        next_tick = self.next_canon_tick()
        if next_tick is None:
            return {
                "current_tick": self.host.current_tick,
                "event": None,
                "world": self.host.world_state(),
            }
        tick = self.host.set_tick(next_tick)
        event = self.pack.event_by_tick(tick)
        return {
            "current_tick": tick,
            "event": event.model_dump(mode="json") if event else None,
            "world": self.host.world_state(tick),
            "who_knows": self.host.who_knows(tick),
        }

    def create(self, entry_id: str, seat: str = "A", *, live: bool = False) -> dict[str, Any]:
        self.ensure_canon_worldline()
        if self.db.active_human_worldline() is not None:
            raise WorldlineConflict("an active human Worldline already exists")
        entry = self._entry(entry_id)
        if seat not in entry.playable_seats:
            raise WorldlineError("this Entry does not expose the requested Seat")
        if seat not in self.pack.actor_by_seat:
            raise WorldlineError(f"unknown Seat {seat}")
        event = self.pack.event_by_id[entry.event_id]
        if self.host.current_tick < event.tick:
            raise WorldlineError("the Entry is not available before its Canon tick")
        if live:
            self._assert_live_ready()

        worldline_id = f"wl-{uuid.uuid4().hex[:16]}"
        runtime_epoch = self.host._epoch()
        base_projection = project_canon(self.pack.events, event.tick)
        base_projection["locations"] = {
            actor.seat: actor.initial_location for actor in self.pack.actors
        }
        base_projection["entry_id"] = entry.id
        base_projection["branch_premise"] = entry.display_name
        worldline_values = {
            "id": worldline_id,
            "scenario_id": self.pack.manifest.id,
            "kind": WorldlineKind.BRANCH.value,
            "status": WorldlineStatus.ACTIVE.value,
            "entry_id": entry.id,
            "controller_seat": seat,
            "current_tick": event.tick,
            "runtime_epoch": runtime_epoch,
            "runtime_mode": "live" if live else "fixture",
        }
        created = self._planned_event(
            worldline_id,
            event.tick,
            "WORLDLINE_CREATED",
            {
                "entry_id": entry.id,
                "controller_seat": seat,
                "controller": Controller.HUMAN.value,
                "runtime_mode": "live" if live else "fixture",
                "horizon": entry.horizon,
                "base_projection": base_projection,
            },
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=runtime_epoch,
        )
        entered = self._planned_event(
            worldline_id,
            event.tick,
            "ENTRY_ENTERED",
            {
                "entry_id": entry.id,
                "premise": entry.premise,
                "world_effects": [
                    {
                        "type": "court_decision",
                        "target": "southern_command_proposal",
                        "value": "accepted",
                        "provenance": Provenance.BRANCH_DERIVED.value,
                    }
                ],
            },
            seat_id=seat,
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[created["id"]],
            runtime_epoch=runtime_epoch,
        )
        lifetime_values: list[dict[str, Any]] = []
        human_lifetime: dict[str, Any] | None = None
        for actor in self.pack.actors:
            memory_text, memory_hash = self._memory_snapshot(actor.seat)
            knowledge = self._knowledge_for_seat(actor.seat, event.tick)
            beliefs = self.db.current_beliefs(actor.seat)
            lifetime = {
                "id": f"{worldline_id}-lifetime-{actor.seat.lower()}",
                "worldline_id": worldline_id,
                "seat": actor.seat,
                "controller": Controller.HUMAN.value
                if actor.seat == seat
                else Controller.AGENT.value,
                "parent_canon_lifetime": f"{self.canon_id}:{actor.seat}",
                "genesis_hash": stable_hash(
                    {
                        "worldline_id": worldline_id,
                        "seat": actor.seat,
                        "entry_id": entry.id,
                        "memory_hash": memory_hash,
                        "knowledge": knowledge,
                    }
                ),
                "memory_text": memory_text,
                "memory_hash": memory_hash,
                "knowledge": knowledge,
                "beliefs": beliefs,
                "authority": [item.value for item in actor.authority],
            }
            lifetime_values.append(lifetime)
            if actor.seat == seat:
                human_lifetime = lifetime

        initial_deliveries = self._plan_due_observations(
            worldline_id,
            event.tick,
            entry_tick=event.tick,
            exact_tick=None,
            causal_parent_ids=[entered["id"]],
            runtime_epoch=runtime_epoch,
        )
        context = self._seat_context_from_row(
            worldline_id,
            worldline_values,
            extra_events=[created, entered, *initial_deliveries],
            lifetime_override=human_lifetime,
        )
        context_event = self._planned_event(
            worldline_id,
            event.tick,
            "CONTEXT_FROZEN",
            context.model_dump(mode="json"),
            seat_id=seat,
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[item["id"] for item in initial_deliveries] or [entered["id"]],
            runtime_epoch=runtime_epoch,
        )
        initial_events = [created, entered, *initial_deliveries, context_event]
        try:
            self.db.create_worldline_bundle(
                worldline_values,
                initial_events,
                lifetime_values,
                project_worldline(initial_events),
            )
        except sqlite3.IntegrityError as exc:
            raise WorldlineConflict("an active human Worldline already exists") from exc
        return self._active_response(worldline_id, context=context)

    def active(self) -> dict[str, Any] | None:
        row = self.db.active_human_worldline()
        if row is None:
            return None
        return self._active_response(row["id"])

    def inhabit(self, worldline_id: str, lifetime_id: str) -> dict[str, Any]:
        """Take the next step of one V5 Lifetime without running cognition."""

        if not lifetime_id.strip():
            raise WorldlineError("Lifetime id is required")
        result = self._transition_volume_controller(
            worldline_id,
            lifetime_id,
            "HUMAN",
            event_type="LIFETIME_INHABITED",
            reason="inhabit",
        )
        return self._volume_controller_response(result)

    def leave(self, worldline_id: str) -> dict[str, Any]:
        """Leave the current V5 Lifetime and hand an existing trigger to Hermes."""

        row = self._volume(worldline_id)
        lifetime_id = str(row.get("human_lifetime_id") or "")
        if not lifetime_id:
            return {
                "worldline": self._public_volume_worldline(row),
                "lifetime": None,
                "event": None,
                "handoff_wake_ids": [],
                "idempotent": True,
            }
        result = self._transition_volume_controller(
            worldline_id,
            lifetime_id,
            "AGENT",
            event_type="LIFETIME_LEFT",
            reason="leave",
        )
        return self._volume_controller_response(result)

    def sealed(self) -> list[dict[str, Any]]:
        return [
            self._public_worldline(row)
            for row in self.db.worldlines(status=WorldlineStatus.SEALED.value)
            if row["kind"] == WorldlineKind.BRANCH.value
        ]

    def lifetimes(self, worldline_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        return {
            "worldline": self._public_worldline(row),
            "lifetimes": [
                self._public_lifetime(
                    lifetime,
                    private=(
                        row["status"] == WorldlineStatus.SEALED.value
                        or lifetime["seat"] == row["controller_seat"]
                    ),
                )
                for lifetime in self.db.worldline_lifetimes(worldline_id)
            ],
        }

    def lifetime(self, worldline_id: str, seat: str) -> dict[str, Any]:
        self._branch(worldline_id)
        if seat not in self.pack.actor_by_seat:
            raise WorldlineError("Seat not found")
        lifetime = self.db.worldline_lifetime(worldline_id, seat)
        if lifetime is None:
            raise WorldlineError("Seat lifetime is missing from the Worldline")
        current = self._branch(worldline_id)
        if (
            current["status"] == WorldlineStatus.ACTIVE.value
            and seat != current["controller_seat"]
        ):
            raise WorldlineConflict("an active Seat cannot inspect another Seat lifetime")
        public = self._public_lifetime(lifetime, private=True)
        records = self._branch_lifetime_records(worldline_id, seat)
        public["records"] = records
        public["stats"] = {
            "observations": sum(item.get("wake_type") == "OBSERVATION" for item in records),
            "intentions": sum(len(item.get("intentions", [])) for item in records),
            "memories": len((public.get("memory") or {}).get("versions", [])),
        }
        return {"worldline": self._public_worldline(current), "lifetime": public}

    def ledger(self, worldline_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        events = [
            event
            for event in self.db.worldline_events(worldline_id)
            if self._ledger_event_visible(row, event)
        ]
        public_events = [
            {
                "sequence": event["sequence"],
                "id": event["id"],
                "tick": event["tick"],
                "event_type": event["event_type"],
                "seat_id": event["seat_id"],
                "payload": event["payload"],
                "provenance": event["provenance"],
                "causal_parent_ids": event["causal_parent_ids"],
                "created_at": event["created_at"],
            }
            for event in events
        ]
        return {
            "worldline": self._public_worldline(row),
            "cursor": events[-1]["sequence"] if events else 0,
            "events": public_events,
        }

    @staticmethod
    def _ledger_event_visible(row: dict[str, Any], event: dict[str, Any]) -> bool:
        if row["status"] == WorldlineStatus.SEALED.value:
            return True
        controller = row["controller_seat"]
        if event.get("seat_id") == controller:
            return True
        if event["event_type"] in {"WORLDLINE_CREATED", "ENTRY_ENTERED", "TIME_ADVANCED"}:
            return True
        if event["event_type"] in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            return event.get("payload", {}).get("from") == controller
        return False

    def context(self, worldline_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise WorldlineConflict("a sealed Worldline cannot resume a Seat context")
        context = self.seat_context(worldline_id)
        return self._active_response(worldline_id, context=context)

    def input(self, worldline_id: str, text: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        self._require_active_human(row)
        if row["pending_confirmation_json"]:
            raise WorldlineConflict("confirm or cancel the pending high-impact action first")
        if not text.strip():
            raise WorldlineError("input cannot be empty")
        context = self.seat_context(worldline_id)
        epoch = row["runtime_epoch"] or self.host._epoch()
        frozen = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "CONTEXT_FROZEN",
            context.model_dump(mode="json"),
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=epoch,
        )
        user_input = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "USER_INPUT",
            {"text": text.strip(), "context_hash": stable_hash(context.model_dump(mode="json"))},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[frozen["id"]],
            runtime_epoch=epoch,
        )
        compiled = self.compiler.compile(text, context, self.pack)
        input_events = [frozen, user_input]
        if compiled.unrecognized_segments or len(compiled.actions) > 1:
            return self._record_compound_input(row, user_input, compiled, epoch, input_events=input_events)
        if not compiled.actions:
            return self._record_non_action_input(row, user_input, compiled, epoch, input_events=input_events)

        action = compiled.actions[0]
        status, reason = self._validate_action(row, action)
        if status != ActionValidation.ACCEPTED:
            rejected = self._planned_event(
                worldline_id,
                int(row["current_tick"]),
                "INTENT_REJECTED",
                {
                    "action": action.model_dump(mode="json"),
                    "status": status.value,
                    "reason": reason,
                },
                seat_id=row["controller_seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[user_input["id"]],
                runtime_epoch=epoch,
            )
            self._commit_input_moment(row, [*input_events, rejected])
            result = InteractionResult(
                kind=compiled.kind,
                answer=compiled.answer,
                interpreted_actions=[action],
                status=status,
                result={"event_id": rejected["id"], "reason": reason},
            )
            return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(worldline_id).model_dump(mode="json")}

        entry = self._entry(row["entry_id"])
        if action.type in entry.confirmation_required:
            confirmation_id = f"confirmation-{uuid.uuid4().hex[:12]}"
            pending = {
                "confirmation_id": confirmation_id,
                "action": action.model_dump(mode="json"),
                "input_event_id": user_input["id"],
                "context_event_id": frozen["id"],
                "tick": int(row["current_tick"]),
            }
            awaiting = self._planned_event(
                worldline_id,
                int(row["current_tick"]),
                "INTENT_AWAITING_CONFIRMATION",
                pending,
                seat_id=row["controller_seat"],
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[user_input["id"]],
                runtime_epoch=epoch,
            )
            self._commit_input_moment(
                row,
                [*input_events, awaiting],
                pending_confirmation_json=json.dumps(pending, ensure_ascii=False, sort_keys=True),
            )
            result = InteractionResult(
                kind=compiled.kind,
                answer=compiled.answer,
                interpreted_actions=[action],
                status=ActionValidation.ACCEPTED,
                requires_confirmation=True,
                confirmation_id=confirmation_id,
                result={"event_id": awaiting["id"], "reason": "请确认这项高影响动作。"},
            )
            return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(worldline_id).model_dump(mode="json")}

        return self._commit_action(row, user_input, action, compiled, epoch, input_events=input_events)

    def confirm(self, worldline_id: str, confirmation_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        self._require_active_human(row)
        pending_raw = row.get("pending_confirmation_json") or ""
        if not pending_raw:
            prior = self._confirmation_event(worldline_id, confirmation_id)
            if prior and prior["event_type"] == "INTENT_CONFIRMED":
                return self._idempotent_confirmation_response(row, prior, accepted=True)
            if prior and prior["event_type"] == "INTENT_CANCELLED":
                raise WorldlineConflict("this confirmation was already cancelled")
            raise WorldlineError("there is no pending confirmation")
        pending = json.loads(pending_raw)
        if pending.get("confirmation_id") != confirmation_id:
            raise WorldlineError("confirmation id does not match the pending action")
        epoch = row["runtime_epoch"] or self.host._epoch()
        action = BranchAction.model_validate(pending["action"])
        compiled = CompiledInput("intent", actions=(action,), status=ActionValidation.ACCEPTED)
        confirmed = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "INTENT_CONFIRMED",
            {"confirmation_id": confirmation_id, "action": pending["action"]},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[pending["input_event_id"], pending["context_event_id"]],
            runtime_epoch=epoch,
        )
        accepted = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "INTENT_ACCEPTED",
            {"action": action.model_dump(mode="json"), "status": ActionValidation.ACCEPTED.value},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[confirmed["id"]],
            runtime_epoch=epoch,
        )
        action_event = self._planned_action_event(
            worldline_id,
            int(row["current_tick"]),
            row["controller_seat"],
            action,
            [accepted["id"], confirmed["id"]],
            epoch,
            [confirmed, accepted],
        )
        try:
            self.db.commit_worldline_moment(
                worldline_id,
                [confirmed, accepted, action_event],
                current_tick=int(row["current_tick"]),
                pending_confirmation_json="",
                expected_pending_confirmation_json=pending_raw,
                expected_current_tick=int(row["current_tick"]),
            )
        except sqlite3.IntegrityError as exc:
            prior = self._confirmation_event(worldline_id, confirmation_id)
            if prior and prior["event_type"] == "INTENT_CONFIRMED":
                return self._idempotent_confirmation_response(self._branch(worldline_id), prior, accepted=True)
            raise WorldlineConflict("confirmation state changed; refresh and retry") from exc
        result = InteractionResult(
            kind=compiled.kind,
            answer=compiled.answer,
            interpreted_actions=[action],
            status=ActionValidation.ACCEPTED,
            result={
                "event_id": action_event["id"],
                "event_type": action_event["event_type"],
                "message": "意图已记录；时间不会因提交意图自动推进。",
            },
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(worldline_id).model_dump(mode="json")}

    def cancel(self, worldline_id: str, confirmation_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        self._require_active_human(row)
        pending_raw = row.get("pending_confirmation_json") or ""
        if not pending_raw:
            prior = self._confirmation_event(worldline_id, confirmation_id)
            if prior and prior["event_type"] == "INTENT_CANCELLED":
                return self._idempotent_confirmation_response(row, prior, accepted=False)
            if prior and prior["event_type"] == "INTENT_CONFIRMED":
                raise WorldlineConflict("this confirmation was already confirmed")
            raise WorldlineError("there is no pending confirmation")
        pending = json.loads(pending_raw)
        if pending.get("confirmation_id") != confirmation_id:
            raise WorldlineError("confirmation id does not match the pending action")
        epoch = row["runtime_epoch"] or self.host._epoch()
        cancelled = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "INTENT_CANCELLED",
            {"confirmation_id": confirmation_id, "action": pending["action"]},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[pending["input_event_id"], pending["context_event_id"]],
            runtime_epoch=epoch,
        )
        try:
            self.db.commit_worldline_moment(
                worldline_id,
                [cancelled],
                current_tick=int(row["current_tick"]),
                pending_confirmation_json="",
                expected_pending_confirmation_json=pending_raw,
                expected_current_tick=int(row["current_tick"]),
            )
        except sqlite3.IntegrityError as exc:
            prior = self._confirmation_event(worldline_id, confirmation_id)
            if prior and prior["event_type"] == "INTENT_CANCELLED":
                return self._idempotent_confirmation_response(self._branch(worldline_id), prior, accepted=False)
            raise WorldlineConflict("confirmation state changed; refresh and retry") from exc
        result = InteractionResult(
            kind="intent",
            status=ActionValidation.AMBIGUOUS,
            result={"event_id": cancelled["id"], "message": "已取消这项待确认动作。"},
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(worldline_id).model_dump(mode="json")}

    def _confirmation_event(self, worldline_id: str, confirmation_id: str) -> dict[str, Any] | None:
        for event in reversed(self.db.worldline_events(worldline_id)):
            if (
                event["event_type"] in {"INTENT_CONFIRMED", "INTENT_CANCELLED"}
                and event["payload"].get("confirmation_id") == confirmation_id
            ):
                return event
        return None

    def _idempotent_confirmation_response(
        self, row: dict[str, Any], event: dict[str, Any], *, accepted: bool
    ) -> dict[str, Any]:
        action_event = next(
            (
                candidate
                for candidate in self.db.worldline_events(row["id"])
                if event["id"] in candidate.get("causal_parent_ids", [])
                and candidate["event_type"]
                in {
                    "MESSAGE_DISPATCHED",
                    "ORDER_ISSUED",
                    "INQUIRY_REQUESTED",
                    "AUTHORITY_APPOINTED",
                    "MOVEMENT_PREPARED",
                    "PRINCIPAL_MOVED",
                    "FORCE_REDEPLOYED",
                    "DISCLOSURE_SET",
                    "WAIT_COMMITTED",
                }
            ),
            None,
        )
        result = InteractionResult(
            kind="intent",
            status=ActionValidation.ACCEPTED if accepted else ActionValidation.AMBIGUOUS,
            result={
                "event_id": action_event["id"] if action_event else event["id"],
                "idempotent": True,
                "message": "这项确认已经处理过。",
            },
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(row["id"]).model_dump(mode="json")}

    def advance(self, worldline_id: str, *, live: bool = False) -> dict[str, Any]:
        row = self._branch(worldline_id)
        self._require_active_human(row)
        requested_mode = "live" if live else "fixture"
        if requested_mode != (row.get("runtime_mode") or "fixture"):
            raise WorldlineConflict("Worldline runtime mode is fixed for the active experience")
        if row["pending_confirmation_json"]:
            raise WorldlineConflict("confirm or cancel the pending high-impact action first")
        if live:
            self._assert_live_ready()
        current = int(row["current_tick"])
        entry = self._entry(row["entry_id"])
        horizon = self.pack.event_by_id[entry.event_id].tick + entry.horizon
        events = self.db.worldline_events(worldline_id)
        projection = project_worldline(events)
        future_ticks = [
            event.tick
            for event in self.pack.events
            if current < event.tick <= horizon and event.branch_policy.value != "canon_only"
        ]
        future_ticks.extend(
            int(message["delivery_tick"])
            for message in projection.get("messages", [])
            if message.get("status") == "in_transit"
            and current < int(message.get("delivery_tick", 0)) <= horizon
        )
        delivered_observations = {
            event["payload"].get("observation_id")
            for event in events
            if event["event_type"] == "OBSERVATION_DELIVERED"
        }
        future_ticks.extend(
            observation.delivery_tick
            for canon_event in self.pack.events
            if canon_event.tick <= self.pack.event_by_id[entry.event_id].tick
            or canon_event.branch_policy.value != "canon_only"
            for observations in canon_event.observations.values()
            for observation in observations
            if observation.id not in delivered_observations
            and current < observation.delivery_tick <= horizon
        )
        if not future_ticks:
            return self._seal_at_boundary(row, "horizon_reached")
        target = min(future_ticks)
        epoch = row["runtime_epoch"] or self.host._epoch()
        frozen = self._planned_event(
            worldline_id,
            current,
            "CONTEXT_FROZEN",
            self.seat_context(worldline_id).model_dump(mode="json"),
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            runtime_epoch=epoch,
        )
        advanced = self._planned_event(
            worldline_id,
            target,
            "TIME_ADVANCED",
            {"from_tick": current, "to_tick": target, "reason": "next_significant_event"},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[frozen["id"]],
            runtime_epoch=epoch,
        )
        canon_events = [
            event
            for event in self.pack.events
            if event.tick == target and event.branch_policy.value != "canon_only"
        ]
        canon_records: list[dict[str, Any]] = []
        for event in canon_events:
            canon_records.append(
                self._planned_event(
                    worldline_id,
                    target,
                    "CANON_EVENT",
                    {
                        "event_id": event.id,
                        "native_date": event.native_date,
                        "title": event.title,
                        "assertion_ids": event.assertion_ids,
                        "branch_policy": event.branch_policy.value,
                        "world_effects": [item.model_dump(mode="json") for item in event.world_effects],
                    },
                    provenance=Provenance.HISTORICAL.value,
                    causal_parent_ids=[advanced["id"]],
                    runtime_epoch=epoch,
                    event_id=f"{worldline_id}:canon:{event.id}",
                )
            )
        message_deliveries = self._plan_due_messages(
            worldline_id,
            target,
            causal_parent_ids=[advanced["id"]],
            runtime_epoch=epoch,
        )
        observation_deliveries = self._plan_due_observations(
            worldline_id,
            target,
            entry_tick=self.pack.event_by_id[entry.event_id].tick,
            exact_tick=target,
            causal_parent_ids=[item["id"] for item in canon_records] or [advanced["id"]],
            runtime_epoch=epoch,
        )
        deliveries = message_deliveries + observation_deliveries
        target_row = dict(row)
        target_row["current_tick"] = target
        agent_deliveries: dict[str, list[dict[str, Any]]] = {}
        for delivery in deliveries:
            seat = delivery.get("seat_id")
            if seat and seat != row["controller_seat"]:
                agent_deliveries.setdefault(seat, []).append(delivery)
        lifetime_updates: list[dict[str, Any]] = [
            self._delivery_lifetime_update(worldline_id, seat, seat_deliveries)
            for seat, seat_deliveries in agent_deliveries.items()
        ]
        agent_wakes = self._wake_agents_for_deliveries(
            target_row, deliveries, live=live, epoch=epoch
        )
        try:
            moment_events = [frozen, advanced, *canon_records, *deliveries]
            for wake in agent_wakes:
                wake["all_deliveries"] = agent_deliveries.get(wake["seat"], wake["deliveries"])
                context_event = self._planned_event(
                    worldline_id,
                    target,
                    "CONTEXT_FROZEN",
                    wake["context"],
                    seat_id=wake["seat"],
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[item["id"] for item in wake["deliveries"]],
                    runtime_epoch=epoch,
                )
                wake_event = self._planned_event(
                    worldline_id,
                    target,
                    "AGENT_WAKE",
                    wake["payload"],
                    seat_id=wake["seat"],
                    provenance=Provenance.MODELED.value
                    if wake["source"] == "fixture"
                    else Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[context_event["id"]],
                    runtime_epoch=epoch,
                )
                wake["event_id"] = wake_event["id"]
                wake["response"] = wake["payload"]["response"]
                moment_events.extend([context_event, wake_event])
                agent_events, lifetime_update = self._apply_agent_response(
                    target_row,
                    wake,
                    parent_id=wake_event["id"],
                    base_events=moment_events,
                    epoch=epoch,
                )
                moment_events.extend(agent_events)
                if lifetime_update:
                    lifetime_updates.append(lifetime_update)
            self.db.commit_worldline_moment(
                worldline_id,
                moment_events,
                current_tick=target,
                lifetime_updates=lifetime_updates,
                snapshot=project_worldline(self.db.worldline_events(worldline_id) + moment_events),
                expected_current_tick=current,
            )
        except sqlite3.IntegrityError as exc:
            self._cleanup_uncommitted_profiles(agent_wakes)
            raise WorldlineConflict("Worldline changed while this moment was being prepared; refresh and retry") from exc
        except Exception:
            self._cleanup_uncommitted_profiles(agent_wakes)
            raise
        updated = self.db.worldline(worldline_id) or row
        public_deliveries = [
            record["payload"]
            for record in deliveries
            if record.get("seat_id") == row["controller_seat"]
            or (
                record["event_type"] == "MESSAGE_DELIVERED"
                and record.get("payload", {}).get("from") == row["controller_seat"]
            )
        ]
        public_wakes = [
            {
                "seat": wake["seat"],
                "source": wake["source"],
                "trigger": wake["payload"].get("trigger", ""),
                "event_id": wake.get("event_id", ""),
                "accepted_count": len(wake["payload"].get("branch_results", {}).get("accepted", [])),
                "rejected_count": len(wake["payload"].get("branch_results", {}).get("rejected", [])),
            }
            for wake in agent_wakes
        ]
        return {
            "worldline": self._public_worldline(updated),
            "advanced_to": target,
            "canon_events": [record["payload"] for record in canon_records],
            "deliveries": public_deliveries,
            "agent_wakes": public_wakes,
            "hidden_delivery_count": len(deliveries) - len(public_deliveries),
            "context": self.seat_context(worldline_id).model_dump(mode="json"),
        }

    def seal(
        self,
        worldline_id: str,
        reason: str = "user_exit",
        *,
        extra_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = self._branch(worldline_id)
        self._require_active_human(row)
        if row["pending_confirmation_json"]:
            raise WorldlineConflict("confirm or cancel the pending high-impact action first")
        if not reason.strip():
            reason = "user_exit"
        epoch = row["runtime_epoch"] or self.host._epoch()
        pre_events = list(extra_events or [])
        existing_events = self.db.worldline_events(worldline_id)
        context_parent_ids = [pre_events[-1]["id"]] if pre_events else (
            [existing_events[-1]["id"]] if existing_events else []
        )
        final_context = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "CONTEXT_FROZEN",
            self.seat_context(worldline_id).model_dump(mode="json"),
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=context_parent_ids,
            runtime_epoch=epoch,
        )
        pre_events.append(final_context)
        event = self._planned_event(
            worldline_id,
            int(row["current_tick"]),
            "WORLDLINE_SEALED",
            {"reason": reason.strip()},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[final_context["id"]],
            runtime_epoch=epoch,
        )
        outcome = self._seal_outcome(row, reason.strip())
        try:
            self.db.commit_worldline_seal(
                worldline_id,
                event,
                reason=reason.strip(),
                outcome=outcome,
                pre_events=pre_events,
                snapshot=project_worldline(existing_events + pre_events + [event]),
            )
        except sqlite3.IntegrityError as exc:
            raise WorldlineConflict("Worldline changed while it was being sealed; refresh and retry") from exc
        sealed = self.db.worldline(worldline_id) or row
        return {"worldline": self._public_worldline(sealed), "event_id": event["id"]}

    def debrief(self, worldline_id: str) -> dict[str, Any]:
        row = self._branch(worldline_id)
        if row["status"] != WorldlineStatus.SEALED.value:
            raise WorldlineConflict("Debrief is available only after the Worldline is sealed")
        events = self.db.worldline_events(worldline_id)
        contexts = [
            event["payload"]
            for event in events
            if event["event_type"] == "CONTEXT_FROZEN"
            and event.get("seat_id") == row["controller_seat"]
        ]
        human_inputs = [event for event in events if event["event_type"] == "USER_INPUT"]
        human_roots = {
            event["id"]
            for event in events
            if event["event_type"] in {"INTENT_ACCEPTED", "INTENT_CONFIRMED"}
            and event.get("seat_id") == row["controller_seat"]
        }
        changed = descendant_events(events, human_roots)
        projection = project_worldline(events)
        entry = self._entry(row["entry_id"])
        canon_at_stop = project_canon(self.pack.events, int(row["current_tick"]))
        return {
            "worldline": self._public_worldline(row),
            "entry": entry.model_dump(mode="json"),
            "what_you_saw": {
                "contexts": contexts,
                "inputs": [event["payload"] for event in human_inputs],
            },
            "what_was_true": {
                "tick": int(row["current_tick"]),
                "branch_projection": projection,
                "canon_projection_at_stop": canon_at_stop,
                "branch_effects": [
                    event["payload"]
                    for event in events
                    if event["event_type"] in {"ENTRY_ENTERED", "ORDER_ISSUED", "MESSAGE_DISPATCHED", "MESSAGE_DELIVERED", "MOVEMENT_PREPARED", "PRINCIPAL_MOVED", "FORCE_REDEPLOYED", "DISCLOSURE_SET", "AUTHORITY_APPOINTED"}
                ],
            },
            "what_you_changed": [
                {
                    "event_type": event["event_type"],
                    "tick": event["tick"],
                    "payload": event["payload"],
                    "causal_parent_ids": event["causal_parent_ids"],
                }
                for event in changed
                if event["event_type"] not in {"CONTEXT_FROZEN", "USER_INPUT"}
            ],
            "where_stopped": {
                "tick": int(row["current_tick"]),
                "reason": row["seal_reason"],
                "outcome": row["outcome"],
                "horizon": self.pack.event_by_id[entry.event_id].tick + entry.horizon,
            },
        }

    def seat_context(self, worldline_id: str) -> SeatContextView:
        row = self._branch(worldline_id)
        return self._seat_context_from_row(worldline_id, row)

    def _record_non_action_input(
        self,
        row: dict[str, Any],
        user_input: dict[str, Any],
        compiled: CompiledInput,
        epoch: str,
        *,
        input_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        event_type = "INQUIRY_ANSWERED" if compiled.kind == "inquiry" else "INPUT_REJECTED"
        payload = {"kind": compiled.kind, "answer": compiled.answer, "status": (compiled.status.value if compiled.status else "")}
        record = self._planned_event(
            row["id"],
            int(row["current_tick"]),
            event_type,
            payload,
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[user_input["id"]],
            runtime_epoch=epoch,
        )
        self._commit_input_moment(row, [*input_events, record])
        result = InteractionResult(
            kind=compiled.kind,
            answer=compiled.answer,
            status=compiled.status,
            result={"event_id": record["id"], "reason": payload.get("reason", "")},
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(row["id"]).model_dump(mode="json")}

    def _record_compound_input(
        self,
        row: dict[str, Any],
        user_input: dict[str, Any],
        compiled: CompiledInput,
        epoch: str,
        *,
        input_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        action_results: list[dict[str, Any]] = []
        for action in compiled.actions:
            status, reason = self._validate_action(row, action)
            action_results.append(
                {
                    "action": action.model_dump(mode="json"),
                    "status": status.value,
                    "reason": reason,
                }
            )
        reason = (
            "输入中包含无法识别的片段；请确认后再提交。"
            if compiled.unrecognized_segments
            else "一次输入包含多个动作；请拆开或编辑后再提交。"
        )
        record = self._planned_event(
            row["id"],
            int(row["current_tick"]),
            "INPUT_REQUIRES_CLARIFICATION",
            {
                "kind": compiled.kind,
                "actions": [action.model_dump(mode="json") for action in compiled.actions],
                "action_results": action_results,
                "unrecognized_segments": list(compiled.unrecognized_segments),
                "reason": reason,
            },
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[user_input["id"]],
            runtime_epoch=epoch,
        )
        self._commit_input_moment(row, [*input_events, record])
        result = InteractionResult(
            kind=compiled.kind,
            answer=reason,
            interpreted_actions=list(compiled.actions),
            status=ActionValidation.AMBIGUOUS,
            result={"event_id": record["id"], "action_results": action_results, "reason": reason},
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(row["id"]).model_dump(mode="json")}

    def _commit_action(
        self,
        row: dict[str, Any],
        parent: dict[str, Any],
        action: BranchAction,
        compiled: CompiledInput,
        epoch: str,
        *,
        confirmed_event: dict[str, Any] | None = None,
        input_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        worldline_id = row["id"]
        tick = int(row["current_tick"])
        seat = row["controller_seat"]
        prefix = list(input_events or [])
        accepted = self._planned_event(
            worldline_id,
            tick,
            "INTENT_ACCEPTED",
            {"action": action.model_dump(mode="json"), "status": ActionValidation.ACCEPTED.value},
            seat_id=seat,
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[parent["id"]],
            runtime_epoch=epoch,
        )
        action_parent_ids = [accepted["id"]]
        if confirmed_event:
            action_parent_ids.append(confirmed_event["id"])
        action_event = self._planned_action_event(
            worldline_id,
            tick,
            seat,
            action,
            action_parent_ids,
            epoch,
            [*prefix, accepted],
        )
        self._commit_input_moment(row, [*prefix, accepted, action_event])
        result = InteractionResult(
            kind=compiled.kind,
            answer=compiled.answer,
            interpreted_actions=[action],
            status=ActionValidation.ACCEPTED,
            result={
                "event_id": action_event["id"],
                "event_type": action_event["event_type"],
                "message": "意图已记录；时间不会因提交意图自动推进。",
            },
        )
        return {"interaction": result.model_dump(mode="json"), "context": self.seat_context(worldline_id).model_dump(mode="json")}

    def _commit_input_moment(
        self,
        row: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        pending_confirmation_json: str | None = None,
    ) -> None:
        try:
            self.db.commit_worldline_moment(
                row["id"],
                events,
                current_tick=int(row["current_tick"]),
                snapshot=project_worldline(self.db.worldline_events(row["id"]) + events),
                pending_confirmation_json=pending_confirmation_json,
                expected_pending_confirmation_json="",
                expected_current_tick=int(row["current_tick"]),
            )
        except sqlite3.IntegrityError as exc:
            raise WorldlineConflict(
                "Worldline changed while the input was being committed; refresh and retry"
            ) from exc

    def _planned_action_event(
        self,
        worldline_id: str,
        tick: int,
        seat: str,
        action: BranchAction,
        parent_ids: list[str],
        epoch: str,
        base_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": seat,
            "seat": seat,
            "target": action.target,
            "recipient": action.recipient,
            "payload": action.payload,
            "priority": action.priority,
            "causal_envelope": ACTION_CAUSAL_ENVELOPE[action.type],
        }
        event_type = {
            ActionType.SEND_MESSAGE: "MESSAGE_DISPATCHED",
            ActionType.ISSUE_ORDER: "ORDER_ISSUED",
            ActionType.REQUEST_INFORMATION: "INQUIRY_REQUESTED",
            ActionType.APPOINT_AUTHORITY: "AUTHORITY_APPOINTED",
            ActionType.PREPARE_MOVEMENT: "MOVEMENT_PREPARED",
            ActionType.MOVE_PRINCIPAL: "PRINCIPAL_MOVED",
            ActionType.REDEPLOY_FORCE: "FORCE_REDEPLOYED",
            ActionType.SET_DISCLOSURE: "DISCLOSURE_SET",
            ActionType.WAIT: "WAIT_COMMITTED",
        }[action.type]
        if action.type == ActionType.SEND_MESSAGE:
            projection = project_worldline(self.db.worldline_events(worldline_id) + base_events)
            origin = projection.get("locations", {}).get(seat, "")
            destination = projection.get("locations", {}).get(action.recipient, "")
            route = self._route_between(origin, destination)
            payload.update(
                {
                    "id": f"message-{uuid.uuid4().hex[:12]}",
                    "origin": origin,
                    "destination": destination,
                    "delivery_tick": tick + route.travel_days,
                    "status": "in_transit",
                }
            )
        if action.type == ActionType.SET_DISCLOSURE:
            payload["value"] = action.payload
        return self._planned_event(
            worldline_id,
            tick,
            event_type,
            payload,
            seat_id=seat,
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=parent_ids,
            runtime_epoch=epoch,
        )

    def _agent_intention_to_action(self, seat: str, intention: Any) -> BranchAction:
        payload = intention.payload or {}
        recipient = str(payload.get("recipient") or payload.get("seat") or "")
        if not recipient and intention.target in self.pack.actor_by_seat and intention.target != seat:
            recipient = intention.target
        raw_payload = payload.get("payload") or payload.get("text") or intention.reason
        if isinstance(raw_payload, dict):
            raw_payload = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)
        return BranchAction(
            type=intention.action,
            target=str(payload.get("target") or intention.target or ""),
            recipient=recipient,
            payload=str(raw_payload or ""),
            priority=str(payload.get("priority") or "normal"),
        )

    def _apply_agent_response(
        self,
        row: dict[str, Any],
        wake: dict[str, Any],
        *,
        parent_id: str,
        base_events: list[dict[str, Any]],
        epoch: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        seat = wake["seat"]
        lifetime = self.db.worldline_lifetime(row["id"], seat)
        if lifetime is None:
            return [], None
        response = ActorWakeResponse.model_validate(wake["payload"]["response"])
        events: list[dict[str, Any]] = []
        working_events = list(base_events)
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        agent_row = dict(row)
        agent_row["controller_seat"] = seat
        for intention in response.intentions:
            action = self._agent_intention_to_action(seat, intention)
            status, reason = self._validate_action(agent_row, action, base_events=working_events)
            if status != ActionValidation.ACCEPTED:
                rejection = self._planned_event(
                    row["id"],
                    int(row["current_tick"]),
                    "AGENT_INTENT_REJECTED",
                    {
                        "seat": seat,
                        "action": action.model_dump(mode="json"),
                        "status": status.value,
                        "reason": reason,
                    },
                    seat_id=seat,
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[parent_id],
                    runtime_epoch=epoch,
                )
                events.append(rejection)
                working_events.append(rejection)
                rejected.append({"action": action.model_dump(mode="json"), "status": status.value, "reason": reason})
                continue
            accepted_event = self._planned_event(
                row["id"],
                int(row["current_tick"]),
                "AGENT_INTENT_ACCEPTED",
                {"seat": seat, "action": action.model_dump(mode="json"), "status": status.value},
                seat_id=seat,
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[parent_id],
                runtime_epoch=epoch,
            )
            action_event = self._planned_action_event(
                row["id"],
                int(row["current_tick"]),
                seat,
                action,
                [accepted_event["id"]],
                epoch,
                working_events,
            )
            events.extend([accepted_event, action_event])
            working_events.extend([accepted_event, action_event])
            accepted.append(
                {
                    "action": action.model_dump(mode="json"),
                    "event_id": action_event["id"],
                    "event_type": action_event["event_type"],
                }
            )

        beliefs = dict(lifetime["beliefs"])
        for update in response.belief_updates:
            belief = update.model_dump(mode="json")
            belief["updated_tick"] = int(row["current_tick"])
            beliefs[update.belief_key] = belief
        knowledge = list(lifetime["knowledge"])
        known_keys = {
            item.get("observation_id") or item.get("message_id")
            for item in knowledge
            if isinstance(item, dict)
        }
        for delivery in wake.get("all_deliveries", wake["deliveries"]):
            payload = delivery["payload"]
            item = {
                "observation_id": payload.get("observation_id", ""),
                "message_id": payload.get("message_id", ""),
                "delivery_tick": delivery["tick"],
                "origin_assertion_id": payload.get("origin_assertion_id", ""),
            }
            key = item["observation_id"] or item["message_id"]
            if key and key not in known_keys:
                knowledge.append(item)
                known_keys.add(key)
        if response.memory_action not in {"", "NO_CHANGE"}:
            blocked = self._planned_event(
                row["id"],
                int(row["current_tick"]),
                "AGENT_RESPONSE_REJECTED",
                {
                    "seat": seat,
                    "reason": "ordinary Agent Wake cannot mutate durable memory",
                    "memory_action": response.memory_action,
                },
                seat_id=seat,
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[parent_id],
                runtime_epoch=epoch,
            )
            events.append(blocked)
        if wake.get("memory_violation"):
            rolled_back = self._planned_event(
                row["id"],
                int(row["current_tick"]),
                "AGENT_RESPONSE_REJECTED",
                {
                    "seat": seat,
                    "reason": wake["memory_violation"]["reason"],
                    "memory": wake["memory_violation"],
                },
                seat_id=seat,
                provenance=Provenance.BRANCH_DERIVED.value,
                causal_parent_ids=[parent_id],
                runtime_epoch=epoch,
            )
            events.append(rolled_back)

        wake["payload"]["branch_results"] = {"accepted": accepted, "rejected": rejected}
        lifetime_update = dict(wake.get("profile_update") or {})
        lifetime_update.update(
            {
                "seat": seat,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "belief_json": json.dumps(beliefs, ensure_ascii=False, sort_keys=True),
            }
        )
        return events, lifetime_update

    def _validate_action(
        self,
        row: dict[str, Any],
        action: BranchAction,
        *,
        base_events: list[dict[str, Any]] | None = None,
    ) -> tuple[ActionValidation, str]:
        entry = self._entry(row["entry_id"])
        seat = row["controller_seat"]
        actor = self.pack.actor_by_seat[seat]
        if action.type not in entry.actions:
            return ActionValidation.UNSUPPORTED, "该 Entry 没有开放这类动作。"
        if ACTION_CAUSAL_ENVELOPE[action.type] not in set(entry.causal_envelope):
            return ActionValidation.UNSUPPORTED, "这个动作超出了当前 Entry 的因果边界。"
        if action.type not in actor.authority:
            return ActionValidation.IMPOSSIBLE, "这个 Seat 当前没有执行该动作的权限。"
        if action.type == ActionType.SEND_MESSAGE:
            if not action.recipient or not action.payload:
                return ActionValidation.AMBIGUOUS, "传信需要明确收信 Seat 和内容。"
            if action.recipient not in self.pack.actor_by_seat or action.recipient == seat:
                return ActionValidation.IMPOSSIBLE, "收信 Seat 不可用。"
            projection = project_worldline(self.db.worldline_events(row["id"]) + list(base_events or []))
            origin = projection.get("locations", {}).get(seat, "")
            destination = projection.get("locations", {}).get(action.recipient, "")
            try:
                self._route_between(origin, destination)
            except WorldlineError as exc:
                return ActionValidation.IMPOSSIBLE, str(exc)
        if action.type in {ActionType.ISSUE_ORDER, ActionType.APPOINT_AUTHORITY, ActionType.SET_DISCLOSURE} and not action.payload and action.type != ActionType.APPOINT_AUTHORITY:
            return ActionValidation.AMBIGUOUS, "该动作需要补充内容。"
        if action.type in {
            ActionType.PREPARE_MOVEMENT,
            ActionType.MOVE_PRINCIPAL,
            ActionType.REDEPLOY_FORCE,
        }:
            if not action.target:
                return ActionValidation.AMBIGUOUS, "移动或调动需要明确目标位置。"
            if action.target not in self.pack.location_by_id:
                return ActionValidation.IMPOSSIBLE, "目标位置不在当前 Entry 的路线模型中。"
            projection = project_worldline(self.db.worldline_events(row["id"]) + list(base_events or []))
            current = projection.get("locations", {}).get(seat, "")
            if action.target == current:
                return ActionValidation.IMPOSSIBLE, "目标位置与当前所在位置相同。"
            try:
                self._route_between(current, action.target)
            except WorldlineError as exc:
                return ActionValidation.IMPOSSIBLE, str(exc)
        return ActionValidation.ACCEPTED, ""

    @staticmethod
    def _planned_event(
        worldline_id: str,
        tick: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        seat_id: str | None = None,
        provenance: str = Provenance.BRANCH_DERIVED.value,
        causal_parent_ids: list[str] | None = None,
        runtime_epoch: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": event_id or f"wle-{uuid.uuid4().hex[:16]}",
            "worldline_id": worldline_id,
            "tick": tick,
            "event_type": event_type,
            "seat_id": seat_id,
            "payload": payload,
            "provenance": provenance,
            "causal_parent_ids": causal_parent_ids or [],
            "runtime_epoch": runtime_epoch,
        }

    def _plan_due_messages(
        self,
        worldline_id: str,
        tick: int,
        *,
        causal_parent_ids: list[str],
        runtime_epoch: str,
    ) -> list[dict[str, Any]]:
        events = self.db.worldline_events(worldline_id)
        delivered = {
            event["payload"].get("message_id")
            for event in events
            if event["event_type"] == "MESSAGE_DELIVERED"
        }
        records: list[dict[str, Any]] = []
        for dispatch in events:
            if dispatch["event_type"] != "MESSAGE_DISPATCHED":
                continue
            payload = dispatch["payload"]
            message_id = payload.get("id", "")
            if not message_id or message_id in delivered or int(payload.get("delivery_tick", 0)) != tick:
                continue
            records.append(
                self._planned_event(
                    worldline_id,
                    tick,
                    "MESSAGE_DELIVERED",
                    {
                        "message_id": message_id,
                        "from": payload.get("from", ""),
                        "recipient": payload.get("recipient", ""),
                        "payload": payload.get("payload", ""),
                        "origin": payload.get("origin", ""),
                        "destination": payload.get("destination", ""),
                        "status": "delivered",
                    },
                    seat_id=payload.get("recipient"),
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[dispatch["id"]] or causal_parent_ids,
                    runtime_epoch=runtime_epoch,
                    event_id=f"{worldline_id}:message-delivered:{message_id}",
                )
            )
            delivered.add(message_id)
        return records

    def _plan_due_observations(
        self,
        worldline_id: str,
        tick: int,
        *,
        entry_tick: int,
        exact_tick: int | None,
        causal_parent_ids: list[str],
        runtime_epoch: str,
    ) -> list[dict[str, Any]]:
        existing = {
            event["payload"].get("observation_id")
            for event in self.db.worldline_events(worldline_id)
            if event["event_type"] == "OBSERVATION_DELIVERED"
        }
        records: list[dict[str, Any]] = []
        for canon_event in self.pack.events:
            eligible = canon_event.tick <= entry_tick or canon_event.branch_policy.value != "canon_only"
            if not eligible:
                continue
            for seat, observations in canon_event.observations.items():
                for observation in observations:
                    if observation.id in existing:
                        continue
                    if observation.delivery_tick > tick:
                        continue
                    if exact_tick is not None and observation.delivery_tick != exact_tick:
                        continue
                    records.append(
                        self._planned_event(
                            worldline_id,
                            observation.delivery_tick,
                            "OBSERVATION_DELIVERED",
                            {
                                "observation_id": observation.id,
                                "origin_event_id": canon_event.id,
                                "origin_assertion_id": observation.origin_assertion_id,
                                "channel": observation.channel,
                                "source_alias": observation.source_alias,
                                "reliability_hint": observation.reliability_hint,
                                "runtime_payload": observation.runtime_payload,
                            },
                            seat_id=seat,
                            provenance=Provenance.HISTORICAL.value,
                            causal_parent_ids=causal_parent_ids,
                            runtime_epoch=runtime_epoch,
                            event_id=f"{worldline_id}:observation:{observation.id}",
                        )
                    )
                    existing.add(observation.id)
        return records

    def _append_due_messages(
        self,
        worldline_id: str,
        tick: int,
        *,
        causal_parent_ids: list[str],
        runtime_epoch: str,
    ) -> list[dict[str, Any]]:
        events = self.db.worldline_events(worldline_id)
        delivered = {
            event["payload"].get("message_id")
            for event in events
            if event["event_type"] == "MESSAGE_DELIVERED"
        }
        records: list[dict[str, Any]] = []
        for dispatch in events:
            if dispatch["event_type"] != "MESSAGE_DISPATCHED":
                continue
            payload = dispatch["payload"]
            message_id = payload.get("id", "")
            if not message_id or message_id in delivered or int(payload.get("delivery_tick", 0)) != tick:
                continue
            records.append(
                self.db.append_worldline_event(
                    worldline_id,
                    tick,
                    "MESSAGE_DELIVERED",
                    {
                        "message_id": message_id,
                        "from": payload.get("from", ""),
                        "recipient": payload.get("recipient", ""),
                        "payload": payload.get("payload", ""),
                        "origin": payload.get("origin", ""),
                        "destination": payload.get("destination", ""),
                        "status": "delivered",
                    },
                    seat_id=payload.get("recipient"),
                    provenance=Provenance.BRANCH_DERIVED.value,
                    causal_parent_ids=[dispatch["id"]] or causal_parent_ids,
                    runtime_epoch=runtime_epoch,
                    event_id=f"{worldline_id}:message-delivered:{message_id}",
                )
            )
            delivered.add(message_id)
        return records

    def _append_due_observations(
        self,
        worldline_id: str,
        tick: int,
        *,
        entry_tick: int,
        exact_tick: int | None,
        causal_parent_ids: list[str],
        runtime_epoch: str,
    ) -> list[dict[str, Any]]:
        existing = {
            event["payload"].get("observation_id")
            for event in self.db.worldline_events(worldline_id)
            if event["event_type"] == "OBSERVATION_DELIVERED"
        }
        records: list[dict[str, Any]] = []
        for canon_event in self.pack.events:
            eligible = canon_event.tick <= entry_tick or canon_event.branch_policy.value != "canon_only"
            if not eligible:
                continue
            for seat, observations in canon_event.observations.items():
                for observation in observations:
                    if observation.id in existing:
                        continue
                    if observation.delivery_tick > tick:
                        continue
                    if exact_tick is not None and observation.delivery_tick != exact_tick:
                        continue
                    records.append(
                        self.db.append_worldline_event(
                            worldline_id,
                            observation.delivery_tick,
                            "OBSERVATION_DELIVERED",
                            {
                                "observation_id": observation.id,
                                "origin_event_id": canon_event.id,
                                "origin_assertion_id": observation.origin_assertion_id,
                                "channel": observation.channel,
                                "source_alias": observation.source_alias,
                                "reliability_hint": observation.reliability_hint,
                                "runtime_payload": observation.runtime_payload,
                            },
                            seat_id=seat,
                            provenance=Provenance.HISTORICAL.value,
                            causal_parent_ids=causal_parent_ids,
                            runtime_epoch=runtime_epoch,
                            event_id=f"{worldline_id}:observation:{observation.id}",
                        )
                    )
                    existing.add(observation.id)
        return records

    def _cleanup_uncommitted_profiles(self, wakes: list[dict[str, Any]]) -> None:
        cleanup_errors: list[Exception] = []
        seen: set[tuple[str, str]] = set()
        for wake in reversed(wakes):
            cleanup = wake.get("profile_cleanup")
            if not cleanup:
                continue
            key = (str(cleanup["seat"]), str(cleanup["worldline_id"]))
            if key in seen:
                continue
            seen.add(key)
            try:
                hermes.remove_lazy_profile(
                    self.host.config,
                    key[0],
                    key[1],
                )
            except Exception as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise hermes.HermesRuntimeError(
                "live Hermes lazy Profile cleanup failed after the moment failed"
            ) from cleanup_errors[0]

    def _wake_agents_for_deliveries(
        self,
        row: dict[str, Any],
        deliveries: list[dict[str, Any]],
        *,
        live: bool,
        epoch: str,
    ) -> list[dict[str, Any]]:
        created_profiles: list[tuple[str, str]] = []
        try:
            return self._wake_agents_for_deliveries_uncompensated(
                row,
                deliveries,
                live=live,
                epoch=epoch,
                created_profiles=created_profiles,
            )
        except Exception:
            cleanup_errors: list[Exception] = []
            for seat, _profile in reversed(created_profiles):
                try:
                    hermes.remove_lazy_profile(self.host.config, seat, row["id"])
                except Exception as cleanup_exc:
                    cleanup_errors.append(cleanup_exc)
            if cleanup_errors:
                raise hermes.HermesRuntimeError(
                    "live Hermes lazy Profile cleanup failed after the moment failed"
                ) from cleanup_errors[0]
            raise

    def _wake_agents_for_deliveries_uncompensated(
        self,
        row: dict[str, Any],
        deliveries: list[dict[str, Any]],
        *,
        live: bool,
        epoch: str,
        created_profiles: list[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for delivery in deliveries:
            seat = delivery.get("seat_id")
            if seat and seat != row["controller_seat"] and self._delivery_wakes_agent(row, delivery):
                grouped.setdefault(seat, []).append(delivery)
        wakes: list[dict[str, Any]] = []
        for seat, seat_deliveries in grouped.items():
            lifetime = self.db.worldline_lifetime(row["id"], seat)
            if lifetime is None:
                continue
            profile_update: dict[str, Any] | None = None
            if not lifetime["profile_name"]:
                profile_name, metadata = self._prepare_lazy_lifetime_profile(row, lifetime, live=live)
                lifetime = dict(lifetime)
                lifetime["profile_name"] = profile_name
                profile_update = {
                    "seat": seat,
                    "profile_name": profile_name,
                    "profile_metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                }
                if live:
                    created_profiles.append((seat, profile_name))
            context = self._agent_context(row, seat, extra_events=seat_deliveries)
            response: dict[str, Any]
            source = "fixture"
            session_id = ""
            if live:
                profile = lifetime["profile_name"]
                key = hermes.profile_api_key(self.host.config, profile)
                if not key:
                    raise hermes.HermesRuntimeError("live Hermes lazy Profile key is unavailable")
                readiness = hermes.probe(self.host.config, [profile])
                if not readiness.ready_for(profile):
                    raise hermes.HermesRuntimeError("live Hermes lazy Profile readiness check failed")
                client = hermes.HermesClient(self.host.config)
                memory_path = hermes.profile_memory_path(self.host.config, profile)
                memory_before, memory_hash_before = hermes.read_profile_memory(self.host.config, profile)
                memory_existed_before = memory_path.exists()
                try:
                    session_id = client.create_fresh_session(profile, key, f"{row['id']}-{seat}-{row['current_tick']}") or ""
                    if not session_id:
                        raise hermes.HermesRuntimeError("live Hermes Fresh Session is unavailable for a lazy Seat")
                    raw, session_id = client.chat(
                        profile,
                        key,
                        hermes.wake_messages(self._context_for_prompt(context), "observation"),
                        session_id,
                        f"chronicle:{row['id']}:{seat}",
                    )
                    response = hermes.parse_actor_response(raw).model_dump(mode="json")
                    source = "hermes"
                except Exception as exc:
                    self._guard_lazy_profile_memory(
                        row,
                        seat,
                        profile,
                        memory_before,
                        memory_hash_before,
                        memory_existed_before,
                        epoch,
                        "lazy Agent Wake failed after Hermes Memory mutation",
                    )
                    raise hermes.HermesRuntimeError("live Hermes lazy Seat wake failed") from exc
                memory_violation = self._guard_lazy_profile_memory(
                    row,
                    seat,
                    profile,
                    memory_before,
                    memory_hash_before,
                    memory_existed_before,
                    epoch,
                    "ordinary lazy Agent Wake mutated Hermes Memory",
                )
            else:
                response = self._fixture_agent_response(seat, seat_deliveries)
                memory_violation = None
            wakes.append(
                {
                    "seat": seat,
                    "source": source,
                    "deliveries": seat_deliveries,
                    "context": context.model_dump(mode="json"),
                    "profile_update": profile_update,
                    "profile_cleanup": (
                        {"seat": seat, "worldline_id": row["id"]}
                        if live and profile_update
                        else None
                    ),
                    "memory_violation": memory_violation,
                    "payload": {
                        "seat": seat,
                        "source": source,
                        "session_id": session_id,
                        "observation_ids": [
                            item["payload"].get("observation_id")
                            for item in seat_deliveries
                            if item["event_type"] == "OBSERVATION_DELIVERED"
                        ],
                        "message_ids": [
                            item["payload"].get("message_id")
                            for item in seat_deliveries
                            if item["event_type"] == "MESSAGE_DELIVERED"
                        ],
                        "trigger": (
                            "message"
                            if any(item["event_type"] == "MESSAGE_DELIVERED" for item in seat_deliveries)
                            else "significant_observation"
                        ),
                        "response": response,
                    },
                }
            )
        return wakes

    def _guard_lazy_profile_memory(
        self,
        row: dict[str, Any],
        seat: str,
        profile: str,
        before_text: str,
        before_hash: str,
        before_exists: bool,
        epoch: str,
        reason: str,
    ) -> dict[str, Any] | None:
        try:
            after_text, after_hash = hermes.read_profile_memory(self.host.config, profile)
        except OSError as exc:
            raise hermes.HermesRuntimeError("Hermes lazy Profile Memory could not be inspected") from exc
        if after_hash == before_hash:
            return None
        diff = "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile="memory.before",
                tofile="memory.after",
            )
        )
        try:
            hermes.restore_profile_memory(self.host.config, profile, before_exists, before_text)
            _restored_text, restored_hash = hermes.read_profile_memory(self.host.config, profile)
            if restored_hash != before_hash:
                raise OSError("restored Memory hash does not match the snapshot")
        except OSError as exc:
            self.db.add_protocol_violation(
                {
                    "seat": seat,
                    "tick": int(row["current_tick"]),
                    "wake_type": "observation",
                    "reason": f"{reason}; Worldline {row['id']}; rollback failed",
                    "memory_hash_before": before_hash,
                    "memory_hash_after": after_hash,
                    "memory_diff": diff,
                    "action": "rollback_failed",
                    "runtime_epoch": epoch,
                }
            )
            raise hermes.HermesRuntimeError("Hermes lazy Profile Memory rollback failed") from exc
        self.db.add_protocol_violation(
            {
                "seat": seat,
                "tick": int(row["current_tick"]),
                "wake_type": "observation",
                "reason": f"{reason}; Worldline {row['id']}",
                "memory_hash_before": before_hash,
                "memory_hash_after": restored_hash,
                "memory_diff": diff,
                "action": "rollback",
                "runtime_epoch": epoch,
            }
        )
        return {
            "reason": reason,
            "memory_hash_before": before_hash,
            "memory_hash_after": after_hash,
            "memory_hash_restored": restored_hash,
        }

    @staticmethod
    def _fixture_agent_response(seat: str, deliveries: list[dict[str, Any]]) -> dict[str, Any]:
        """Keep fixture reactions deterministic while still exercising a causal reply."""

        received_message = any(item["event_type"] == "MESSAGE_DELIVERED" for item in deliveries)
        if seat == "C" and received_message:
            return {
                "assessment": "东部位置已收到传信；回报当前关口状态，但不推断其他位置的完整局势。",
                "belief_updates": [],
                "intentions": [
                    {
                        "action": ActionType.SEND_MESSAGE.value,
                        "target": "A",
                        "reason": "回报东部关口当前状态",
                        "payload": {
                            "recipient": "A",
                            "text": "东部已收到传信，关口暂时维持；是否出动仍需等待更完整的边地报告。",
                        },
                    },
                    {"action": ActionType.WAIT.value, "target": "", "reason": "等待更多信息", "payload": {}},
                ],
                "uncertainties": ["未观察到其他 Seat 的完整状态。"],
                "memory_action": "NO_CHANGE",
                "memory_text": "",
            }
        return {
            "assessment": "新抵达的信息已被记录；该 Seat 仍只能依据自身视角判断。",
            "belief_updates": [],
            "intentions": [{"action": ActionType.WAIT.value, "target": "", "reason": "等待更多信息", "payload": {}}],
            "uncertainties": ["未观察到其他 Seat 的完整状态。"],
            "memory_action": "NO_CHANGE",
            "memory_text": "",
        }

    def _delivery_lifetime_update(
        self, worldline_id: str, seat: str, deliveries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        lifetime = self.db.worldline_lifetime(worldline_id, seat)
        if lifetime is None:
            return {"seat": seat}
        knowledge = list(lifetime["knowledge"])
        known_keys = {
            item.get("observation_id") or item.get("message_id")
            for item in knowledge
            if isinstance(item, dict)
        }
        for delivery in deliveries:
            payload = delivery["payload"]
            item = {
                "observation_id": payload.get("observation_id", ""),
                "message_id": payload.get("message_id", ""),
                "delivery_tick": delivery["tick"],
                "origin_assertion_id": payload.get("origin_assertion_id", ""),
            }
            key = item["observation_id"] or item["message_id"]
            if key and key not in known_keys:
                knowledge.append(item)
                known_keys.add(key)
        return {
            "seat": seat,
            "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
        }

    def _delivery_wakes_agent(self, row: dict[str, Any], delivery: dict[str, Any]) -> bool:
        entry = self._entry(row["entry_id"])
        if delivery["event_type"] == "MESSAGE_DELIVERED":
            return entry.wake_policy.messages
        if delivery["event_type"] != "OBSERVATION_DELIVERED":
            return False
        return delivery["payload"].get("channel") in set(entry.wake_policy.observation_channels)

    def _prepare_lazy_lifetime_profile(
        self, row: dict[str, Any], lifetime: dict[str, Any], *, live: bool
    ) -> tuple[str, dict[str, Any]]:
        seat = lifetime["seat"]
        profile_name = f"chronicle-{row['id'][-8:]}-seat-{seat.lower()}"
        if live:
            try:
                profile_name, metadata = hermes.create_lazy_profile(
                    self.host.config,
                    seat,
                    row["id"],
                    memory_text=lifetime["memory_text"],
                )
            except Exception as exc:
                raise hermes.HermesRuntimeError("live Hermes lazy Profile creation failed") from exc
        else:
            metadata = {
                "mode": "fixture",
                "created_on_observation": True,
                "worldline_id": row["id"],
                "seat": seat,
            }
        return profile_name, metadata

    def _agent_context(
        self,
        row: dict[str, Any],
        seat: str,
        *,
        extra_events: list[dict[str, Any]] | None = None,
    ) -> SeatContextView:
        original = row["controller_seat"]
        row = dict(row)
        row["controller_seat"] = seat
        context = self.seat_context_for(row["id"], row, extra_events=extra_events)
        row["controller_seat"] = original
        return context

    def seat_context_for(
        self,
        worldline_id: str,
        row: dict[str, Any],
        *,
        extra_events: list[dict[str, Any]] | None = None,
    ) -> SeatContextView:
        return self._seat_context_from_row(worldline_id, row, extra_events=extra_events)

    def _seat_context_from_row(
        self,
        worldline_id: str,
        row: dict[str, Any],
        *,
        extra_events: list[dict[str, Any]] | None = None,
        lifetime_override: dict[str, Any] | None = None,
    ) -> SeatContextView:
        seat = row["controller_seat"]
        lifetime = lifetime_override or self.db.worldline_lifetime(worldline_id, seat)
        if lifetime is None:
            raise WorldlineError("Seat lifetime is missing from the Worldline")
        events = self.db.worldline_events(worldline_id) + list(extra_events or [])
        observation_deliveries = [
            event
            for event in events
            if event["event_type"] == "OBSERVATION_DELIVERED"
            and event.get("seat_id") == seat
            and int(event["tick"]) <= int(row["current_tick"])
        ]
        message_deliveries = [
            event
            for event in events
            if event["event_type"] == "MESSAGE_DELIVERED"
            and event.get("seat_id") == seat
            and int(event["tick"]) <= int(row["current_tick"])
        ]
        reached = [
            {
                "observation_id": event["payload"].get("observation_id", ""),
                "received_at": event["tick"],
                "channel": event["payload"].get("channel", ""),
                "source_alias": event["payload"].get("source_alias", ""),
                "reliability_hint": event["payload"].get("reliability_hint", ""),
                "payload": event["payload"].get("runtime_payload", ""),
                "origin_assertion_id": event["payload"].get("origin_assertion_id", ""),
            }
            for event in observation_deliveries
        ] + [
            {
                "message_id": event["payload"].get("message_id", ""),
                "received_at": event["tick"],
                "channel": "branch-message",
                "source_alias": event["payload"].get("from", ""),
                "reliability_hint": "your Seat's committed message",
                "payload": event["payload"].get("payload", ""),
                "origin_assertion_id": "",
                "from": event["payload"].get("from", ""),
            }
            for event in message_deliveries
        ]
        reached.sort(key=lambda item: (int(item["received_at"]), item.get("observation_id", item.get("message_id", ""))))
        projection = project_worldline(events)
        known_assertions = sorted(
            {item["origin_assertion_id"] for item in reached if item.get("origin_assertion_id")}
        )
        open_orders = [
            item for item in projection.get("orders", []) if item.get("from") == seat or item.get("recipient") == seat
        ]
        carried_messages = [
            item for item in projection.get("messages", []) if item.get("from") == seat or item.get("recipient") == seat
        ]
        uncertainty = ["你尚未拥有其他 Seat 的完整视角。"]
        uncertainty.append("目前没有新的已送达消息。" if not reached else "晚到消息可能改变当前判断。")
        return SeatContextView(
            worldline_id=worldline_id,
            entry_id=row["entry_id"],
            seat=seat,
            tick=int(row["current_tick"]),
            known_world={
                "tick": int(row["current_tick"]),
                "known_assertion_ids": known_assertions,
                "known_observation_count": len(observation_deliveries),
                "last_received_at": reached[-1]["received_at"] if reached else None,
            },
            what_reached_you=reached,
            what_you_carry={
                "memory": {"text": lifetime["memory_text"], "hash": lifetime["memory_hash"]},
                "beliefs": lifetime["beliefs"],
                "open_orders": open_orders,
                "messages": carried_messages,
                "entry_commitment": "你已进入这条 Entry 的当前历史位置。",
            },
            authority=[ActionType(item) for item in lifetime["authority"]],
            known_uncertainty=uncertainty,
            visible_entities=sorted(
                {seat}
                | {item.get("from", "") for item in carried_messages}
                | {item.get("recipient", "") for item in carried_messages}
                - {""}
            ),
            visible_assertion_ids=known_assertions,
        )

    def _context_for_prompt(self, context: SeatContextView) -> dict[str, Any]:
        return {
            "seat": context.seat,
            "tick": context.tick,
            "known_world": context.known_world,
            "what_reached_you": context.what_reached_you,
            "what_you_carry": context.what_you_carry,
            "authority": [item.value for item in context.authority],
            "known_uncertainty": context.known_uncertainty,
        }

    def _active_response(
        self, worldline_id: str, *, context: SeatContextView | None = None
    ) -> dict[str, Any]:
        row = self._branch(worldline_id)
        entry = self._entry(row["entry_id"])
        seat = self.pack.actor_by_seat[row["controller_seat"]]
        return {
            "worldline": self._public_worldline(row),
            "entry": entry.model_dump(mode="json"),
            "seat": {
                "seat": seat.seat,
                "display_name": seat.display_name,
                "authority": [item.value for item in seat.authority],
            },
            "context": (context or self.seat_context(worldline_id)).model_dump(mode="json"),
        }

    def _public_worldline(self, row: dict[str, Any]) -> dict[str, Any]:
        pending = None
        if row.get("pending_confirmation_json"):
            pending = json.loads(row["pending_confirmation_json"])
        return {
            "id": row["id"],
            "scenario_id": row["scenario_id"],
            "kind": row["kind"],
            "status": row["status"],
            "entry_id": row["entry_id"],
            "seat": row["controller_seat"],
            "current_tick": int(row["current_tick"]),
            "runtime_epoch": row["runtime_epoch"],
            "runtime_mode": row.get("runtime_mode", "fixture"),
            "seal_reason": row["seal_reason"],
            "outcome": row["outcome"],
            "pending_confirmation": pending,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _branch_lifetime_records(self, worldline_id: str, seat: str) -> list[dict[str, Any]]:
        lifetime = self.db.worldline_lifetime(worldline_id, seat)
        if lifetime is None:
            return []
        records: list[dict[str, Any]] = []
        for event in self.db.worldline_events(worldline_id):
            if event.get("seat_id") != seat:
                continue
            payload = event.get("payload", {})
            if event["event_type"] == "CONTEXT_FROZEN" and lifetime["controller"] == Controller.HUMAN.value:
                reached = payload.get("what_reached_you", [])
                records.append(
                    {
                        "id": event["id"],
                        "tick": event["tick"],
                        "wake_type": "OBSERVATION",
                        "observation_ids": [
                            item.get("observation_id") or item.get("message_id")
                            for item in reached
                            if item.get("observation_id") or item.get("message_id")
                        ],
                        "intentions": [],
                    }
                )
            elif event["event_type"] == "AGENT_WAKE":
                response = payload.get("response", {})
                records.append(
                    {
                        "id": event["id"],
                        "tick": event["tick"],
                        "wake_type": "OBSERVATION",
                        "observation_ids": list(payload.get("observation_ids", []))
                        + list(payload.get("message_ids", [])),
                        "intentions": response.get("intentions", []),
                    }
                )
            elif event["event_type"] in {"INTENT_ACCEPTED", "AGENT_INTENT_ACCEPTED"}:
                action = payload.get("action")
                records.append(
                    {
                        "id": event["id"],
                        "tick": event["tick"],
                        "wake_type": "INTENT",
                        "observation_ids": [],
                        "intentions": [action] if action else [],
                    }
                )
        return records

    def _public_lifetime(self, lifetime: dict[str, Any], *, private: bool) -> dict[str, Any]:
        actor = self.pack.actor_by_seat.get(lifetime["seat"])
        metadata = lifetime.get("profile_metadata") or {}
        actor_public = (
            {
                "seat": actor.seat,
                "display_name": actor.display_name,
                "description": actor.description,
                "initial_location": actor.initial_location,
            }
            if actor
            else None
        )
        public = {
            "id": lifetime["id"],
            "worldline_id": lifetime["worldline_id"],
            "seat": lifetime["seat"],
            "actor": actor_public,
            "controller": lifetime["controller"],
            "status": lifetime["status"],
            "profile": {
                "mode": metadata.get("mode", "unknown"),
            },
            "updated_at": lifetime["updated_at"],
        }
        if private:
            public.update(
                {
                    "parent_canon_lifetime": lifetime["parent_canon_lifetime"],
                    "profile": {
                        "name": lifetime["profile_name"],
                        "mode": metadata.get("mode", "unknown"),
                    },
                    "genesis_hash": lifetime["genesis_hash"],
                    "memory": {"text": lifetime["memory_text"], "hash": lifetime["memory_hash"]},
                    "knowledge": lifetime["knowledge"],
                    "beliefs": lifetime["beliefs"],
                    "authority": lifetime["authority"],
                }
            )
        return public

    def _append_snapshot(self, worldline_id: str, tick: int) -> None:
        ledger_cursor = self._ledger_cursor(worldline_id)
        existing = self.db.worldline_snapshot(worldline_id, tick)
        if existing is not None and int(existing["ledger_cursor"]) >= ledger_cursor:
            return
        events = self.db.worldline_events(worldline_id)
        self.db.append_worldline_snapshot(
            worldline_id,
            tick,
            ledger_cursor,
            project_worldline(events),
        )

    def _ledger_cursor(self, worldline_id: str) -> int:
        events = self.db.worldline_events(worldline_id)
        return int(events[-1]["sequence"]) if events else 0

    def _knowledge_for_seat(self, seat: str, tick: int) -> list[dict[str, Any]]:
        return [
            {
                "observation_id": observation.id,
                "origin_event_id": event.id,
                "origin_assertion_id": observation.origin_assertion_id,
                "delivery_tick": observation.delivery_tick,
            }
            for event, observation in self.pack.observations_for(seat, tick)
        ]

    def _memory_snapshot(self, seat: str) -> tuple[str, str]:
        native_path = self.host._native_memory_path(seat)
        if native_path.exists():
            return self.host._native_memory(seat)
        return self.db.current_memory(seat)

    def _seal_outcome(self, row: dict[str, Any], reason: str) -> str:
        if reason in {"horizon_reached", "simulation_boundary"}:
            return "BOUNDARY"
        events = self.db.worldline_events(row["id"])
        changed = any(
            event["event_type"]
            in {
                "MESSAGE_DISPATCHED",
                "ORDER_ISSUED",
                "AUTHORITY_APPOINTED",
                "MOVEMENT_PREPARED",
                "PRINCIPAL_MOVED",
                "FORCE_REDEPLOYED",
                "DISCLOSURE_SET",
            }
            for event in events
        )
        return "DIVERGED" if changed else "CANON_LIKE"

    def _entry(self, entry_id: str):
        if entry_id != self.pack.fork.id:
            raise WorldlineError(f"unknown Entry {entry_id}")
        return self.pack.fork

    def _branch(self, worldline_id: str) -> dict[str, Any]:
        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.BRANCH.value:
            raise WorldlineError("Worldline not found")
        return row

    def _volume(self, worldline_id: str) -> dict[str, Any]:
        row = self.db.worldline(worldline_id)
        if row is None or row["kind"] != WorldlineKind.VOLUME.value:
            raise WorldlineError("VOLUME Worldline not found")
        return row

    def _transition_volume_controller(
        self,
        worldline_id: str,
        lifetime_id: str,
        controller: str,
        *,
        event_type: str,
        reason: str,
    ) -> dict[str, Any]:
        try:
            return self.db.transition_volume_controller(
                worldline_id,
                lifetime_id,
                controller,
                event_type=event_type,
                reason=reason,
            )
        except KeyError as exc:
            raise WorldlineError(str(exc)) from exc
        except (sqlite3.IntegrityError, ValueError) as exc:
            raise WorldlineConflict(str(exc)) from exc

    def _volume_controller_response(self, result: dict[str, Any]) -> dict[str, Any]:
        lifetime = result["lifetime"]
        return {
            "worldline": self._public_volume_worldline(result["worldline"]),
            "lifetime": {
                "id": lifetime["id"],
                "worldline_id": lifetime["worldline_id"],
                "seat": lifetime["seat"],
                "controller": lifetime["controller"],
                "status": lifetime["status"],
                "profile_name": lifetime["profile_name"],
                "profile_state": lifetime["profile_state"],
                "updated_at": lifetime["updated_at"],
            },
            "event": result["event"],
            "handoff_wake_ids": result["handoff_wake_ids"],
            "idempotent": result["idempotent"],
        }

    @staticmethod
    def _public_volume_worldline(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "scenario_id": row["scenario_id"],
            "kind": row["kind"],
            "status": row["status"],
            "current_tick": int(row["current_tick"]),
            "runtime_epoch": row["runtime_epoch"],
            "runtime_mode": row.get("runtime_mode", "fixture"),
            "volume_id": row.get("volume_id", ""),
            "volume_content_version": int(row.get("volume_content_version", 0)),
            "volume_content_hash": row.get("volume_content_hash", ""),
            "worldline_phase": row.get("worldline_phase", "LEGACY"),
            "human_lifetime_id": row.get("human_lifetime_id", ""),
            "updated_at": row["updated_at"],
        }

    def _require_active_human(self, row: dict[str, Any]) -> None:
        if row["status"] != WorldlineStatus.ACTIVE.value:
            raise WorldlineConflict("Worldline is sealed")
        if not row["controller_seat"]:
            raise WorldlineConflict("Worldline has no human Seat")

    def _assert_archivist_open(self) -> None:
        if self.db.active_human_worldline() is not None:
            raise WorldlineConflict("Archivist view is locked while a human Seat is active")

    def _assert_live_ready(self) -> None:
        if not self.host.config.llm_configured:
            raise hermes.HermesRuntimeError("live Hermes is not configured")
        profiles = list(hermes.PROFILE_NAMES.values())
        readiness = hermes.probe(self.host.config, profiles)
        if not all(readiness.ready_for(profile) for profile in profiles):
            raise hermes.HermesRuntimeError("live Hermes readiness check failed")

    def _route_between(self, origin: str, destination: str):
        for route in self.pack.routes:
            if {route.from_location, route.to_location} == {origin, destination}:
                return route
        raise WorldlineError("no defined route connects the current locations")

    def _seal_at_boundary(self, row: dict[str, Any], reason: str) -> dict[str, Any]:
        events = self.db.worldline_events(row["id"])
        horizon = self._planned_event(
            row["id"],
            int(row["current_tick"]),
            "HORIZON_REACHED",
            {"reason": reason},
            seat_id=row["controller_seat"],
            provenance=Provenance.BRANCH_DERIVED.value,
            causal_parent_ids=[events[-1]["id"]] if events else [],
            runtime_epoch=row["runtime_epoch"],
        )
        return self.seal(row["id"], reason, extra_events=[horizon])

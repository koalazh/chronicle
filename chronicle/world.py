from __future__ import annotations

import hashlib
import heapq
import inspect
import json
import uuid
from dataclasses import dataclass
from typing import Any

from .crisis import CrisisPack
from .db import ChronicleDB


class WorldAccessError(PermissionError):
    """The caller is not bound to this active Run, Actor, and Wake."""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoundWorldIdentity:
    run_id: str
    actor_id: str
    profile_name: str
    wake_id: str


class WorldService:
    """Deterministic Chronicle boundary shared by Hermes MCP and Human decisions."""

    def __init__(self, db: ChronicleDB, pack: CrisisPack):
        self.db = db
        self.pack = pack

    def session_for_token(self, wake_id: str, token: str) -> "WorldAffordanceSession":
        binding = self.db.agent_binding_for_token_hash(token_hash(token))
        if binding is None:
            raise WorldAccessError("invalid Chronicle world binding")
        return self._session(
            wake_id,
            run_id=str(binding["worldline_id"]),
            actor_id=str(binding["role"]),
            profile_name=str(binding["profile_identity"]),
        )

    def session_for_current_token(self, token: str) -> "WorldAffordanceSession":
        binding = self.db.agent_binding_for_token_hash(token_hash(token))
        if binding is None:
            raise WorldAccessError("invalid Chronicle world binding")
        wake = self.db.running_crisis_wake(
            str(binding["worldline_id"]), str(binding["role"])
        )
        if wake is None:
            raise WorldAccessError("this Actor has no active Wake")
        return self._session(
            str(wake["id"]),
            run_id=str(binding["worldline_id"]),
            actor_id=str(binding["role"]),
            profile_name=str(binding["profile_identity"]),
        )

    def fixture_session(self, wake_id: str, actor_id: str) -> "WorldAffordanceSession":
        wake = self.db.crisis_wake(wake_id)
        if wake is None:
            raise WorldAccessError("unknown wake")
        return self._session(
            wake_id,
            run_id=str(wake["worldline_id"]),
            actor_id=actor_id,
            profile_name=f"fixture://{actor_id}",
        )

    def human_session(self, wake_id: str, actor_id: str) -> "WorldAffordanceSession":
        wake = self.db.crisis_wake(wake_id)
        if wake is None:
            raise WorldAccessError("unknown Human decision")
        run = self.db.worldline(str(wake["worldline_id"]))
        if run is None:
            raise WorldAccessError("Run is unavailable")
        controllers = json.loads(run["controller_map_json"])
        if controllers.get(actor_id) != "HUMAN":
            raise WorldAccessError("this Actor is not Human-controlled")
        return self._session(
            wake_id,
            run_id=str(wake["worldline_id"]),
            actor_id=actor_id,
            profile_name="human://local",
        )

    def _session(
        self,
        wake_id: str,
        *,
        run_id: str,
        actor_id: str,
        profile_name: str,
    ) -> "WorldAffordanceSession":
        wake = self.db.crisis_wake(wake_id)
        if wake is None or wake["status"] != "RUNNING":
            raise WorldAccessError("wake is not active")
        if wake["worldline_id"] != run_id or wake["actor_id"] != actor_id:
            raise WorldAccessError("binding does not own this wake")
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise WorldAccessError("Run is not active")
        return WorldAffordanceSession(
            service=self,
            identity=BoundWorldIdentity(run_id, actor_id, profile_name, wake_id),
        )

    def route_days(self, start: str, end: str) -> int | None:
        queue: list[tuple[int, str]] = [(0, start)]
        best: dict[str, int] = {start: 0}
        edges: dict[str, list[tuple[str, int]]] = {}
        for route in self.pack.crisis.routes:
            edges.setdefault(route.from_location, []).append(
                (route.to_location, route.travel_days)
            )
        while queue:
            distance, location = heapq.heappop(queue)
            if location == end:
                return distance
            if distance != best.get(location):
                continue
            for target, days in edges.get(location, []):
                candidate = distance + days
                if candidate < best.get(target, 10**9):
                    best[target] = candidate
                    heapq.heappush(queue, (candidate, target))
        return None


class WorldAffordanceSession:
    """Actor-bound tools. Tool arguments intentionally contain no caller identity."""

    MAX_OPERATIONS_PER_WAKE = 8

    def __init__(self, service: WorldService, identity: BoundWorldIdentity):
        self.service = service
        self.identity = identity

    def _stage(
        self,
        tool_name: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        existing = self.service.db.crisis_wake_operations(self.identity.wake_id)
        repeated = next(
            (item for item in existing if item["idempotency_key"] == idempotency_key),
            None,
        )
        if repeated is not None:
            return repeated["result"]
        if len(existing) >= self.MAX_OPERATIONS_PER_WAKE:
            return {"status": "rejected", "code": "wake_tool_budget_exhausted"}
        status = "PROPOSED" if result.get("status") == "accepted" else "REJECTED"
        operation = self.service.db.add_crisis_wake_operation(
            {
                "wake_id": self.identity.wake_id,
                "tool_name": tool_name,
                "payload": payload,
                "result": result,
                "status": status,
                "idempotency_key": idempotency_key,
            }
        )
        return operation["result"]

    def _actor(self):
        return self.service.pack.actor_by_id[self.identity.actor_id]

    def _tick_and_projection(self) -> tuple[int, dict[str, Any]]:
        wake = self.service.db.crisis_wake(self.identity.wake_id)
        snapshot = self.service.db.worldline_snapshot(self.identity.run_id)
        if wake is None or snapshot is None:
            raise WorldAccessError("wake state is unavailable")
        return int(wake["tick"]), dict(snapshot["projection"])

    def communicate(
        self,
        recipient: str,
        content: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {"recipient": recipient, "content": content.strip()}
        if "communicate" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        if recipient not in self.service.pack.actor_by_id or recipient == self.identity.actor_id:
            result = {"status": "rejected", "code": "invalid_recipient"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        if not payload["content"] or len(payload["content"]) > 1200:
            result = {"status": "rejected", "code": "invalid_content"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        start = projection["positions"][self.identity.actor_id]
        end = projection["positions"][recipient]
        travel_days = self.service.route_days(start, end)
        if travel_days is None:
            result = {"status": "rejected", "code": "no_route"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        message_id = f"message-{uuid.uuid4().hex[:16]}"
        result = {
            "status": "accepted",
            "message_id": message_id,
            "dispatch_tick": tick,
            "arrival_tick": tick + max(1, travel_days),
        }
        return self._stage("communicate", payload, result, idempotency_key=idempotency_key)

    def act(
        self,
        action: str,
        description: str,
        *,
        target: str = "",
        idempotency_key: str,
    ) -> dict[str, Any]:
        action = action.strip().lower()
        payload = {"action": action, "description": description.strip(), "target": target}
        if action not in {"hold", "prepare", "move"}:
            result = {"status": "rejected", "code": "unsupported_action"}
            return self._stage("act", payload, result, idempotency_key=idempotency_key)
        if action not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("act", payload, result, idempotency_key=idempotency_key)
        if not payload["description"]:
            result = {"status": "rejected", "code": "missing_description"}
            return self._stage("act", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        result: dict[str, Any] = {"status": "accepted", "action_id": f"action-{uuid.uuid4().hex[:16]}"}
        if action == "move":
            if target not in self.service.pack.location_by_id:
                result = {"status": "rejected", "code": "unknown_location"}
            else:
                start = projection["positions"][self.identity.actor_id]
                travel_days = self.service.route_days(start, target)
                if travel_days is None or travel_days <= 0:
                    result = {"status": "rejected", "code": "no_route"}
                else:
                    arrival_tick = tick + travel_days
                    boundary = self.service.pack.crisis.simulation_boundary.maximum_tick
                    if arrival_tick >= boundary:
                        result = {"status": "rejected", "code": "crosses_simulation_boundary"}
                    else:
                        result.update(
                            {
                                "movement_id": f"movement-{uuid.uuid4().hex[:16]}",
                                "arrival_tick": arrival_tick,
                            }
                        )
        else:
            actor = self._actor()
            current_location = projection["positions"][self.identity.actor_id]
            valid_targets = set(actor.resources) | {current_location}
            if not target:
                result = {"status": "rejected", "code": "missing_grounded_target"}
            elif target not in valid_targets:
                result = {"status": "rejected", "code": "unknown_resource_or_position"}
        return self._stage("act", payload, result, idempotency_key=idempotency_key)

    def update_plan(
        self,
        objective: str,
        steps: list[str],
        *,
        rationale: str = "",
        belief_updates: list[dict[str, str]] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        beliefs = belief_updates or []
        payload = {
            "objective": objective.strip(),
            "steps": [step.strip() for step in steps if step.strip()],
            "rationale": rationale.strip(),
            "belief_updates": beliefs,
        }
        if "update_plan" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
        elif not payload["objective"] or not payload["steps"]:
            result = {"status": "rejected", "code": "invalid_plan"}
        elif any(
            not isinstance(item, dict)
            or not str(item.get("subject", "")).strip()
            or not str(item.get("assessment", "")).strip()
            or item.get("confidence") not in {"low", "medium", "high"}
            for item in beliefs
        ):
            result = {"status": "rejected", "code": "invalid_belief_update"}
        else:
            result = {"status": "accepted", "plan_version": f"plan-{uuid.uuid4().hex[:12]}"}
        return self._stage("update_plan", payload, result, idempotency_key=idempotency_key)

    def schedule_followup(
        self,
        after_days: int,
        purpose: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {"after_days": after_days, "purpose": purpose.strip()}
        tick, _ = self._tick_and_projection()
        due_tick = tick + after_days
        boundary = self.service.pack.crisis.simulation_boundary.maximum_tick
        if "schedule_followup" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
        elif after_days <= 0 or not payload["purpose"]:
            result = {"status": "rejected", "code": "invalid_followup"}
        elif due_tick >= boundary:
            result = {"status": "rejected", "code": "crosses_simulation_boundary"}
        else:
            result = {
                "status": "accepted",
                "commitment_id": f"commitment-{uuid.uuid4().hex[:16]}",
                "due_tick": due_tick,
            }
        return self._stage("schedule_followup", payload, result, idempotency_key=idempotency_key)


def world_tool_signatures() -> dict[str, inspect.Signature]:
    """Inspectable contract used by tests and the MCP adapter."""

    return {
        name: inspect.signature(getattr(WorldAffordanceSession, name))
        for name in ("communicate", "act", "update_plan", "schedule_followup")
    }

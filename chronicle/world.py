from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from dataclasses import dataclass
from typing import Any

from .crisis import AgreementTerm, CrisisPack, OfferAction, OfferStatus
from .db import ChronicleDB, stable_hash


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
        return self.pack.route_days(start, end)


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
        host_key = stable_hash(
            {
                "wake_id": self.identity.wake_id,
                "tool": tool_name,
                "caller_slot": idempotency_key,
            }
        )
        existing = self.service.db.crisis_wake_operations(self.identity.wake_id)
        repeated = next(
            (item for item in existing if item["idempotency_key"] == host_key),
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
                "idempotency_key": host_key,
            }
        )
        return operation["result"]

    def _actor(self):
        return self.service.pack.actor_by_id[self.identity.actor_id]

    def _has_resolution_knowledge(self) -> bool:
        lifetime = self.service.db.worldline_lifetime(
            self.identity.run_id, self.identity.actor_id
        )
        return bool(
            lifetime
            and any(
                isinstance(item, dict) and item.get("kind") == "resolution"
                for item in lifetime["knowledge"]
            )
        )

    @staticmethod
    def _reference_id(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            reference = value.get("id", "")
            return reference.strip() if isinstance(reference, str) else ""
        return ""

    def _normalized_terms(self, terms: list[Any] | None) -> list[Any]:
        normalized: list[Any] = []
        for term in terms or []:
            if not isinstance(term, dict):
                normalized.append(term)
                continue
            value = dict(term)
            value["subject"] = self._reference_id(value.get("subject", ""))
            value.pop("recipient", None)
            normalized.append(value)
        return normalized

    def _tick_and_projection(self) -> tuple[int, dict[str, Any]]:
        wake = self.service.db.crisis_wake(self.identity.wake_id)
        snapshot = self.service.db.worldline_snapshot(self.identity.run_id)
        if wake is None or snapshot is None:
            raise WorldAccessError("wake state is unavailable")
        return int(wake["tick"]), dict(snapshot["projection"])

    def _aftermath_communication_is_grounded(
        self,
        recipient: str,
        projection: dict[str, Any],
    ) -> bool:
        actor_id = self.identity.actor_id
        for offer in projection.get("offers", []):
            if (
                offer.get("status") == OfferStatus.PROPOSED.value
                and {offer.get("issuer"), offer.get("recipient")} == {actor_id, recipient}
            ):
                return True
        return any(
            agreement.get("status") == "ACTIVE"
            and actor_id in agreement.get("parties", [])
            and recipient in agreement.get("parties", [])
            for agreement in projection.get("agreements", [])
        )

    def communicate(
        self,
        recipient: str | dict[str, Any],
        content: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "recipient": self._reference_id(recipient),
            "content": content.strip() if isinstance(content, str) else "",
        }
        if "communicate" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        if (
            payload["recipient"] not in self.service.pack.actor_by_id
            or payload["recipient"] == self.identity.actor_id
        ):
            result = {"status": "rejected", "code": "invalid_recipient"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        if not payload["content"] or len(payload["content"]) > 1200:
            result = {"status": "rejected", "code": "invalid_content"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        if self._has_resolution_knowledge() and not self._aftermath_communication_is_grounded(
            payload["recipient"], projection
        ):
            result = {"status": "rejected", "code": "aftermath_communication_closed"}
            return self._stage("communicate", payload, result, idempotency_key=idempotency_key)
        start = projection["positions"][self.identity.actor_id]
        end = projection["positions"][payload["recipient"]]
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

    def operate(
        self,
        operation_definition_id: str | dict[str, Any],
        targets: list[str | dict[str, Any]],
        description: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "operation_definition_id": self._reference_id(operation_definition_id),
            "targets": [self._reference_id(target) for target in targets],
            "description": description.strip() if isinstance(description, str) else "",
        }
        if "operate" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("operate", payload, result, idempotency_key=idempotency_key)
        if not payload["description"]:
            result = {"status": "rejected", "code": "missing_description"}
            return self._stage("operate", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        request, code = self.service.pack.operation_request(
            self.identity.actor_id,
            payload["operation_definition_id"],
            payload["targets"],
            projection,
            tick,
        )
        if request is None:
            result = {"status": "rejected", "code": code}
        else:
            conflicts_with_staged = any(
                existing["tool_name"] == "operate"
                and existing["status"] == "PROPOSED"
                and self._operations_conflict(
                    request.definition.id,
                    payload["targets"],
                    str(existing["payload"].get("operation_definition_id", "")),
                    list(existing["payload"].get("targets", [])),
                )
                for existing in self.service.db.crisis_wake_operations(self.identity.wake_id)
            )
            result = (
                {"status": "rejected", "code": "operation_conflict"}
                if conflicts_with_staged
                else {
                    "status": "accepted",
                    "operation_id": f"operation-{uuid.uuid4().hex[:16]}",
                    "expected_complete_tick": request.expected_complete_tick,
                    "input_state": request.input_state,
                }
            )
        return self._stage("operate", payload, result, idempotency_key=idempotency_key)

    def _operations_conflict(
        self,
        definition_id: str,
        target_ids: list[str],
        existing_definition_id: str,
        existing_target_ids: list[str],
    ) -> bool:
        definition = self.service.pack.operation_by_id.get(definition_id)
        existing = self.service.pack.operation_by_id.get(existing_definition_id)
        if definition is None or existing is None:
            return False
        return bool(set(target_ids).intersection(existing_target_ids)) and (
            existing.id in definition.conflicts or definition.id in existing.conflicts
        )

    def investigate(
        self,
        question: str,
        target: str | dict[str, Any],
        *,
        method: str = "",
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "question": question.strip() if isinstance(question, str) else "",
            "target": self._reference_id(target),
            "method": method.strip() if isinstance(method, str) else "",
        }
        if "investigate" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("investigate", payload, result, idempotency_key=idempotency_key)
        if self._has_resolution_knowledge():
            result = {"status": "rejected", "code": "aftermath_investigation_closed"}
            return self._stage("investigate", payload, result, idempotency_key=idempotency_key)
        if not payload["question"] or len(payload["question"]) > 1200:
            result = {"status": "rejected", "code": "invalid_question"}
            return self._stage("investigate", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        request, code = self.service.pack.investigation_request(
            self.identity.actor_id,
            payload["target"],
            payload["method"],
            projection,
            tick,
        )
        if request is None:
            result = {"status": "rejected", "code": code}
        else:
            already_staged = any(
                existing["tool_name"] == "investigate"
                and existing["status"] == "PROPOSED"
                and existing["payload"].get("target") == payload["target"]
                and existing["result"].get("definition_id") == request.definition.id
                for existing in self.service.db.crisis_wake_operations(self.identity.wake_id)
            )
            result = (
                {"status": "rejected", "code": "investigation_already_active"}
                if already_staged
                else {
                    "status": "accepted",
                    "investigation_id": f"investigation-{uuid.uuid4().hex[:16]}",
                    "definition_id": request.definition.id,
                    "expected_result_tick": request.expected_result_tick,
                    "method": request.definition.method,
                }
            )
        return self._stage("investigate", payload, result, idempotency_key=idempotency_key)

    def manage_offer(
        self,
        action: str,
        *,
        offer_id: str | dict[str, Any] = "",
        recipient: str | dict[str, Any] = "",
        terms: list[dict[str, Any]] | None = None,
        message: str = "",
        expires_after_days: int = 0,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "action": action.strip().upper() if isinstance(action, str) else "",
            "offer_id": self._reference_id(offer_id),
            "recipient": self._reference_id(recipient),
            "terms": self._normalized_terms(terms),
            "message": message.strip() if isinstance(message, str) else "",
            "expires_after_days": expires_after_days,
        }
        if "manage_offer" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
            return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
        try:
            offer_action = OfferAction(payload["action"])
        except ValueError:
            result = {"status": "rejected", "code": "invalid_offer_action"}
            return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
        tick, projection = self._tick_and_projection()
        actor_id = self.identity.actor_id
        if offer_action in {OfferAction.PROPOSE, OfferAction.COUNTER}:
            if not payload["message"] or len(payload["message"]) > 1200:
                result = {"status": "rejected", "code": "invalid_offer_message"}
                return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
            if len(payload["terms"]) > 4:
                result = {"status": "rejected", "code": "invalid_offer_terms"}
                return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
            try:
                requested_terms = [AgreementTerm.model_validate(term) for term in payload["terms"]]
            except (TypeError, ValueError):
                result = {"status": "rejected", "code": "invalid_offer_terms"}
                return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
        else:
            requested_terms = []
        if not isinstance(payload["expires_after_days"], int) or payload["expires_after_days"] < 0:
            result = {"status": "rejected", "code": "invalid_offer_expiry"}
            return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)
        if offer_action == OfferAction.PROPOSE:
            validated_terms, code = self.service.pack.offer_terms_request(
                actor_id,
                payload["recipient"],
                requested_terms,
            )
            if validated_terms is None:
                result = {"status": "rejected", "code": code}
            else:
                expires_tick = (
                    tick + payload["expires_after_days"]
                    if payload["expires_after_days"]
                    else None
                )
                if expires_tick is not None and expires_tick >= self.service.pack.crisis.simulation_boundary.maximum_tick:
                    result = {"status": "rejected", "code": "crosses_simulation_boundary"}
                else:
                    result = {
                        "status": "accepted",
                        "offer_id": f"offer-{uuid.uuid4().hex[:16]}",
                        "created_tick": tick,
                        "expires_tick": expires_tick,
                    }
        else:
            offer = next(
                (
                    item
                    for item in projection.get("offers", [])
                    if item.get("id") == payload["offer_id"]
                ),
                None,
            )
            if offer is None:
                result = {"status": "rejected", "code": "unknown_offer"}
            elif offer.get("status") != OfferStatus.PROPOSED.value:
                result = {"status": "rejected", "code": "offer_not_open"}
            elif offer_action in {OfferAction.ACCEPT, OfferAction.REJECT} and offer.get("recipient") != actor_id:
                result = {"status": "rejected", "code": "offer_response_denied"}
            elif offer_action == OfferAction.WITHDRAW and offer.get("issuer") != actor_id:
                result = {"status": "rejected", "code": "offer_withdrawal_denied"}
            elif offer_action == OfferAction.COUNTER and offer.get("recipient") != actor_id:
                result = {"status": "rejected", "code": "offer_response_denied"}
            elif offer_action == OfferAction.COUNTER:
                validated_terms, code = self.service.pack.offer_terms_request(
                    actor_id,
                    str(offer["issuer"]),
                    requested_terms,
                )
                if validated_terms is None:
                    result = {"status": "rejected", "code": code}
                else:
                    expires_tick = (
                        tick + payload["expires_after_days"]
                        if payload["expires_after_days"]
                        else None
                    )
                    if (
                        expires_tick is not None
                        and expires_tick >= self.service.pack.crisis.simulation_boundary.maximum_tick
                    ):
                        result = {"status": "rejected", "code": "crosses_simulation_boundary"}
                    elif self.service.pack.same_agreement_terms(
                        validated_terms, list(offer.get("terms", []))
                    ):
                        result = {
                            "status": "accepted",
                            "agreement_id": f"agreement-{uuid.uuid4().hex[:16]}",
                            "counter_normalized_to_accept": True,
                        }
                    else:
                        result = {
                            "status": "accepted",
                            "offer_id": f"offer-{uuid.uuid4().hex[:16]}",
                            "parent_offer_id": str(offer["id"]),
                            "created_tick": tick,
                            "expires_tick": expires_tick,
                        }
            elif offer_action == OfferAction.ACCEPT:
                result = {
                    "status": "accepted",
                    "agreement_id": f"agreement-{uuid.uuid4().hex[:16]}",
                }
            else:
                result = {"status": "accepted"}
        return self._stage("manage_offer", payload, result, idempotency_key=idempotency_key)

    def update_plan(
        self,
        objective: str,
        steps: list[str],
        *,
        rationale: str = "",
        belief_updates: list[dict[str, str] | str] | None = None,
        reconsider_when: list[str] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        beliefs = [item for item in belief_updates or [] if isinstance(item, dict)]
        ignored_belief_updates = len(belief_updates or []) - len(beliefs)
        payload = {
            "objective": objective.strip(),
            "steps": [step.strip() for step in steps if step.strip()],
            "rationale": rationale.strip(),
            "belief_updates": beliefs,
            "reconsider_when": [item.strip() for item in reconsider_when or [] if item.strip()],
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
            if ignored_belief_updates:
                result["ignored_optional_belief_updates"] = ignored_belief_updates
        return self._stage("update_plan", payload, result, idempotency_key=idempotency_key)

    def schedule_revisit(
        self,
        after_days: int,
        reason: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {"after_days": after_days, "reason": reason.strip()}
        tick, _ = self._tick_and_projection()
        due_tick = tick + after_days
        boundary = self.service.pack.crisis.simulation_boundary.maximum_tick
        if "schedule_revisit" not in self._actor().world_authority:
            result = {"status": "rejected", "code": "authority_denied"}
        elif self._has_resolution_knowledge():
            result = {"status": "rejected", "code": "aftermath_revisit_closed"}
        elif after_days <= 0 or not payload["reason"]:
            result = {"status": "rejected", "code": "invalid_revisit"}
        elif due_tick >= boundary:
            result = {"status": "rejected", "code": "crosses_simulation_boundary"}
        else:
            result = {
                "status": "accepted",
                "revisit_id": f"revisit-{uuid.uuid4().hex[:16]}",
                "due_tick": due_tick,
            }
        return self._stage("schedule_revisit", payload, result, idempotency_key=idempotency_key)


def world_tool_signatures() -> dict[str, inspect.Signature]:
    """Inspectable contract used by tests and the MCP adapter."""

    return {
        name: inspect.signature(getattr(WorldAffordanceSession, name))
        for name in (
            "communicate",
            "investigate",
            "manage_offer",
            "operate",
            "update_plan",
            "schedule_revisit",
        )
    }

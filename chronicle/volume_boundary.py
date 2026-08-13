from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_TERMINAL_CRISIS_STATUSES = frozenset({"SETTLED", "SUPPRESSED"})


@dataclass(frozen=True)
class VolumeBoundaryDecision:
    ready: bool
    code: str
    message: str
    evidence_event_ids: tuple[str, ...] = ()
    evidence_assertion_ids: tuple[str, ...] = ()
    fallback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "code": self.code,
            "message": self.message,
            "evidence_event_ids": list(self.evidence_event_ids),
            "evidence_assertion_ids": list(self.evidence_assertion_ids),
            "fallback": self.fallback,
        }


class VolumeBoundaryPolicy:
    """Keep the V6 structural ending separate from Crisis settlement."""

    id = "jiashen-north-south-recognition-v1"

    def evaluate(
        self,
        *,
        current_tick: int,
        projection: dict[str, Any],
        events: list[dict[str, Any]],
        instances: list[dict[str, Any]],
        due_wakes: list[dict[str, Any]],
        next_tick: int | None,
        safety_horizon_tick: int | None,
        required_field_event_ids: tuple[str, ...] = (),
    ) -> VolumeBoundaryDecision:
        fallback = safety_horizon_tick is not None and current_tick >= int(safety_horizon_tick)
        if projection.get("pending_moment"):
            return self._blocked("pending_logical_moment", "仍有一个未提交的历史时刻", fallback)
        if not instances:
            return self._blocked("no_crisis_settlement", "尚未有任何已经落地的局势结果", fallback)
        if any(str(item.get("status")) not in _TERMINAL_CRISIS_STATUSES for item in instances):
            return self._blocked("crisis_unsettled", "仍有局势没有成为已经落地的结果", fallback)

        if due_wakes:
            return self._blocked("due_wake_pending", "仍有待处理的人生时刻", fallback)
        if any(message.get("status") == "in_transit" for message in projection.get("messages", [])):
            return self._blocked("message_in_transit", "仍有消息在路上", fallback)
        if any(field.get("status") == "PENDING" for field in projection.get("field_events", [])):
            return self._blocked("public_history_pending", "公共历史仍有未落地的记录", fallback)
        if next_tick is not None:
            return self._blocked("future_historical_trigger", "世界仍有下一项真实触发", fallback)

        applied_field_ids = {
            str(event.get("payload", {}).get("field_event", {}).get("id", ""))
            for event in events
            if event.get("event_type") == "FIELD_EVENT_APPLIED"
        }
        missing_field_ids = set(required_field_event_ids) - applied_field_ids
        if missing_field_ids:
            return self._blocked(
                "public_boundary_not_reached",
                "南北现实尚未正式进入彼此的判断范围",
                fallback,
            )

        evidence = tuple(
            str(event["id"])
            for event in events
            if event.get("event_type") in {"CRISIS_SETTLED", "FIELD_EVENT_APPLIED"}
            and (
                event.get("event_type") == "CRISIS_SETTLED"
                or str(event.get("payload", {}).get("field_event", {}).get("id", ""))
                in set(required_field_event_ids)
            )
        )
        evidence_assertions = tuple(
            sorted(
                {
                    str(assertion_id)
                    for event in events
                    if event.get("event_type") == "FIELD_EVENT_APPLIED"
                    and str(event.get("payload", {}).get("field_event", {}).get("id", ""))
                    in set(required_field_event_ids)
                    for assertion_id in event.get("payload", {}).get("field_event", {}).get(
                        "assertion_ids", []
                    )
                }
            )
        )
        return VolumeBoundaryDecision(
            ready=True,
            code="structural_boundary",
            message="南北现实已经开始正式互相成为判断对象",
            evidence_event_ids=evidence,
            evidence_assertion_ids=evidence_assertions,
        )

    @staticmethod
    def _blocked(code: str, message: str, fallback: bool = False) -> VolumeBoundaryDecision:
        return VolumeBoundaryDecision(ready=False, code=code, message=message, fallback=fallback)

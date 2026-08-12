from __future__ import annotations

import difflib
import json
import re
from typing import Any

from .config import AppConfig
from .db import ChronicleDB
from .hermes import (
    HermesClient,
    HermesRuntimeError,
    profile_api_key,
    read_profile_memory,
    restore_profile_memory,
)


class VolumeActorDriverError(HermesRuntimeError):
    """A controlled failure while running one live V5 Lifetime Wake."""


class HermesVolumeActorDriver:
    """Run one fresh Hermes session and require one V5 logical intent."""

    source = "hermes"

    def __init__(self, config: AppConfig, db: ChronicleDB):
        self.config = config
        self.db = db

    def run_wake(self, wake: dict[str, Any], perspective: dict[str, Any]) -> dict[str, Any]:
        actor_id = str(wake["actor_id"])
        lifetime = self.db.worldline_lifetime(str(wake["worldline_id"]), actor_id)
        if lifetime is None or not lifetime["profile_name"]:
            raise VolumeActorDriverError(f"live V5 Profile is missing for {actor_id}")
        profile = str(lifetime["profile_name"])
        key = profile_api_key(self.config, profile)
        if not key:
            raise VolumeActorDriverError(f"live V5 Profile key is missing for {actor_id}")

        client = HermesClient(self.config)
        session_id = client.create_fresh_session(profile, key, str(wake["id"]))
        if not session_id:
            raise VolumeActorDriverError(f"live V5 Session creation failed for {actor_id}")
        before_text, before_hash = read_profile_memory(self.config, profile)
        before_existed = (
            self.config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md"
        ).exists()
        expected_hash = str(lifetime.get("memory_hash") or before_hash)
        if expected_hash != before_hash:
            raise VolumeActorDriverError(f"live V5 Memory hash drifted for {actor_id}")

        self.db.update_crisis_wake(
            str(wake["id"]),
            status="RUNNING",
            hermes_session_id=session_id,
            frozen_perspective=perspective,
        )
        try:
            response_text, returned_session = client.chat(
                profile,
                key,
                self._messages(wake, perspective),
                session_id,
                f"{wake['worldline_id']}:{actor_id}",
            )
        except Exception as exc:
            self._fail_wake(wake, actor_id, profile, before_text, before_hash, before_existed)
            raise VolumeActorDriverError(f"live V5 Wake failed for {actor_id}") from exc

        after_text, after_hash = read_profile_memory(self.config, profile)
        if after_hash != before_hash:
            self._rollback_memory(
                wake,
                actor_id,
                profile,
                before_text,
                before_hash,
                before_existed,
                after_text,
                after_hash,
            )
            self._fail_wake(wake, actor_id)
            raise VolumeActorDriverError(
                f"ordinary live V5 Wake attempted a durable Memory mutation for {actor_id}"
            )

        operation = self._logical_operation(str(wake["id"]), perspective)
        if operation is None:
            try:
                repair_text, repaired_session = client.chat(
                    profile,
                    key,
                    self._repair_messages(),
                    session_id,
                    f"{wake['worldline_id']}:{actor_id}",
                )
            except Exception as exc:
                self._fail_wake(
                    wake, actor_id, profile, before_text, before_hash, before_existed
                )
                raise VolumeActorDriverError(f"live V5 Wake repair failed for {actor_id}") from exc
            response_text = repair_text or response_text
            returned_session = repaired_session or returned_session
            repaired_text, repaired_hash = read_profile_memory(self.config, profile)
            if repaired_hash != before_hash:
                self._rollback_memory(
                    wake,
                    actor_id,
                    profile,
                    before_text,
                    before_hash,
                    before_existed,
                    repaired_text,
                    repaired_hash,
                )
                self._fail_wake(wake, actor_id)
                raise VolumeActorDriverError(
                    f"repair V5 Wake attempted a durable Memory mutation for {actor_id}"
                )
            operation = self._logical_operation(str(wake["id"]), perspective)
        if operation is None:
            try:
                self._stage_fallback(wake, response_text)
            except Exception as exc:
                self._fail_wake(wake, actor_id)
                raise VolumeActorDriverError(
                    f"live V5 Wake returned an invalid structured logical intent for {actor_id}"
                ) from exc
            operation = self._logical_operation(str(wake["id"]), perspective)
        if operation is None:
            self._fail_wake(wake, actor_id)
            raise VolumeActorDriverError(
                f"live V5 Wake did not produce one logical_intent operation for {actor_id}"
            )

        self.db.update_crisis_wake(
            str(wake["id"]),
            status="STAGED",
            hermes_session_id=returned_session or session_id,
            result={
                "summary": response_text.strip()[:1200]
                or "本次 Wake 已提交一个逻辑意图。",
                "operation_id": operation["id"],
                "session_id": returned_session or session_id,
            },
        )
        return {
            "summary": response_text.strip()[:1200]
            or "本次 Wake 已提交一个逻辑意图。",
            "session_id": returned_session or session_id,
            "operation_id": operation["id"],
        }

    def _messages(
        self, wake: dict[str, Any], perspective: dict[str, Any]
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是 Chronicle V5 中一个持续存在的历史主体，不是旁白、史官或主持人。"
                    "只使用本次冻结视角中的事实、已知证据、当前计划与有限主体记忆；禁止使用后世知识，"
                    "也不要推断其他主体的私有信息。普通 Wake 不得调用 memory。"
                    "你必须调用 chronicle-world 的一个世界写工具恰好一次，提交一个且只有一个行动。"
                    "可用工具是 communicate、investigate、manage_offer、operate、update_plan、schedule_revisit；"
                    "没有足够依据改变行动时，使用 logical_intent 提交 {type: wait}。"
                    "logical_intent 也可提交 message 或 update_plan，但不得再调用第二个工具。"
                    "update_plan 的 belief_updates 只能引用冻结视角中可见的 evidence event_id；没有证据就留空。"
                    "工具完成后，用简体中文返回一句短说明，不要返回思维过程或内部 Profile、Session、Wake 信息。"
                    "如果工具不可用，必须只返回一个符合上述 schema 的 JSON 意图对象；不要返回自然语言。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "wake_id": str(wake["id"]),
                        "wake_type": str(wake["wake_type"]),
                        "frozen_perspective": perspective,
                        "logical_intent_schema": {
                            "type": "wait|message|update_plan",
                            "recipient": "required for message",
                            "content": "required for message",
                            "delivery_tick": "required for message",
                            "objective": "required for update_plan",
                            "steps": "required for update_plan",
                            "rationale": "optional; only what follows from the current evidence",
                            "belief_updates": "optional evidence-backed list",
                            "reconsider_when": "optional list",
                        },
                        "logical_intent_tool_call": {
                            "name": "logical_intent",
                            "arguments": {
                                "intent": {"type": "wait"},
                                "idempotency_key": f"{wake['id']}:logical-intent",
                            },
                        },
                        "tool_call_rule": (
                            "logical_intent 的 arguments 必须同时包含顶层 intent 和 idempotency_key；"
                            "不要把 intent 的字段提升为顶层参数，也不要省略任一字段。"
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _repair_messages() -> list[dict[str, str]]:
        return [
            {
                "role": "user",
                "content": (
                    "上一条输出没有提交任何逻辑意图。现在只做协议修复：必须调用一次 logical_intent，"
                    "提交一个 wait、message 或 update_plan；如果工具确实不可用，只返回一个符合 schema 的 JSON 意图对象。"
                    "不要解释、不要返回自然语言、不要调用 memory。"
                ),
            }
        ]

    def _logical_operation(
        self, wake_id: str, perspective: dict[str, Any]
    ) -> dict[str, Any] | None:
        moment_id = str(perspective.get("moment_id", ""))
        operations = [
            operation
            for operation in self.db.crisis_wake_operations(wake_id)
            if operation["tool_name"] in {
                "logical_intent",
                "communicate",
                "investigate",
                "manage_offer",
                "operate",
                "update_plan",
                "schedule_revisit",
            }
            and operation["status"] == "PROPOSED"
            and operation["payload"].get("moment_id") == moment_id
        ]
        if len(operations) > 1:
            raise VolumeActorDriverError("one V5 Wake produced multiple logical intents")
        return operations[0] if operations else None

    def _stage_fallback(self, wake: dict[str, Any], response_text: str) -> None:
        """Accept only an explicit structured model response; never invent wait."""

        intent = _parse_structured_intent(response_text)
        if intent is None:
            return
        from .host import ChronicleHost

        ChronicleHost(self.config).volume_runtime.stage_intent(
            str(wake["worldline_id"]),
            str(wake["actor_id"]),
            intent,
            source="agent",
            idempotency_key=f"{wake['id']}:model-response",
        )

    def _fail_wake(
        self,
        wake: dict[str, Any],
        actor_id: str,
        profile: str = "",
        before_text: str = "",
        before_hash: str = "",
        before_existed: bool = False,
    ) -> None:
        if profile and before_hash:
            _current_text, current_hash = read_profile_memory(self.config, profile)
            if current_hash != before_hash:
                restore_profile_memory(self.config, profile, before_existed, before_text)
        try:
            self.db.update_crisis_wake(
                str(wake["id"]), status="FAILED", error={"actor_id": actor_id}
            )
        except KeyError:
            pass

    def _rollback_memory(
        self,
        wake: dict[str, Any],
        actor_id: str,
        profile: str,
        before_text: str,
        before_hash: str,
        before_existed: bool,
        after_text: str,
        after_hash: str,
    ) -> None:
        restore_profile_memory(self.config, profile, before_existed, before_text)
        self.db.add_protocol_violation(
            {
                "seat": f"{wake['worldline_id']}:{actor_id}",
                "tick": int(wake["tick"]),
                "wake_type": wake["wake_type"],
                "reason": "ordinary live V5 Wake attempted a durable Memory mutation",
                "memory_hash_before": before_hash,
                "memory_hash_after": after_hash,
                "memory_diff": "".join(
                    difflib.unified_diff(
                        before_text.splitlines(keepends=True),
                        after_text.splitlines(keepends=True),
                        fromfile="memory.before",
                        tofile="memory.after",
                    )
                ),
                "action": "rollback",
                "runtime_epoch": self.db.worldline(str(wake["worldline_id"]))["runtime_epoch"],
            }
        )


def _parse_structured_intent(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("intent"), dict):
        payload = payload["intent"]
    if not isinstance(payload, dict) or payload.get("type") not in {
        "wait",
        "message",
        "update_plan",
    }:
        return None
    return dict(payload)

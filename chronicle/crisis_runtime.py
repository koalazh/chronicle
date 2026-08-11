from __future__ import annotations

import copy
import difflib
import json
import sqlite3
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .config import AppConfig
from .crisis import (
    AgreementStatus,
    AgreementTerm,
    CrisisPack,
    OfferAction,
    OfferStatus,
    PressureStatus,
    VolumeRegistry,
)
from .db import ChronicleDB, content_hash, stable_hash
from .decision import (
    DecisionInterpreter,
    FixtureDecisionInterpreter,
    ModelDecisionInterpreter,
)
from .resolution import get_resolution_contract
from .resolution.base import ResolutionGateStatus, ResolutionKind
from .world import WorldAffordanceSession, WorldService, token_hash


class CrisisRunError(ValueError):
    """A controlled error at the V3 Run boundary."""


class CrisisRunConflict(CrisisRunError):
    """A Run state conflicts with the requested mutation."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "run_conflict",
        state: str = "",
        tick: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.state = state
        self.tick = tick


class RunMode(StrEnum):
    WATCH = "WATCH"
    TAKEOVER = "TAKEOVER"


class CrisisWakeType(StrEnum):
    ORIENT = "ORIENT"
    MESSAGE = "MESSAGE"
    OBSERVATION = "OBSERVATION"
    INVESTIGATION_RESULT = "INVESTIGATION_RESULT"
    OFFER_CHANGE = "OFFER_CHANGE"
    AGREEMENT_CHANGE = "AGREEMENT_CHANGE"
    OPERATION_RESULT = "OPERATION_RESULT"
    PRESSURE = "PRESSURE"
    RESOLUTION_GATE = "RESOLUTION_GATE"
    RESOLUTION_RESULT = "RESOLUTION_RESULT"
    REVISIT_DUE = "REVISIT_DUE"
    REFLECTION = "REFLECTION"


WATCH_ATTENTION_EVENT_TYPES = frozenset(
    {
        "OFFER_PROPOSED",
        "OFFER_COUNTERED",
        "OFFER_ACCEPTED",
        "OFFER_REJECTED",
        "OFFER_WITHDRAWN",
        "OFFER_EXPIRED",
        "AGREEMENT_CREATED",
        "AGREEMENT_FULFILLED",
        "AGREEMENT_BREACHED",
        "OPERATION_STARTED",
        "OPERATION_COMPLETED",
        "INVESTIGATION_COMPLETED",
        "OBSERVATION_OBTAINED",
        "MOVEMENT_STARTED",
        "MOVEMENT_ARRIVED",
        "PRESSURE_APPLIED",
        "RESOLUTION_GATE_REACHED",
        "RESOLUTION_APPLIED",
        "CRISIS_SETTLED",
    }
)


@dataclass(frozen=True)
class ActorTurnResult:
    summary: str
    session_id: str = ""
    memory_before_text: str = ""
    memory_before_hash: str = ""
    memory_before_existed: bool = False
    memory_text: str = ""
    memory_hash: str = ""
    memory_changed: bool = False


class ActorDriver(Protocol):
    source: str

    def run_wake(
        self,
        actor_id: str,
        wake: dict[str, Any],
        perspective: dict[str, Any],
        world: WorldAffordanceSession,
    ) -> ActorTurnResult: ...


class FixtureActorDriver:
    """Deterministic model double; all world effects still cross WorldService."""

    source = "fixture"

    def run_wake(
        self,
        actor_id: str,
        wake: dict[str, Any],
        perspective: dict[str, Any],
        world: WorldAffordanceSession,
    ) -> ActorTurnResult:
        wake_type = wake["wake_type"]
        tick = int(wake["tick"])
        if wake_type == CrisisWakeType.ORIENT.value:
            objectives = {
                "li-zicheng": ("稳住北京并测试山海关的条件", ["等待来使回音", "保留东部处置选项"]),
                "wu-sangui": ("在两方压力间保住所部与关口", ["核验北京条件", "等待关外回音"]),
                "dorgon": ("保持西进行动自由并核验关内局势", ["继续西行", "等待可靠来使"]),
            }
            objective, steps = objectives[actor_id]
            world.update_plan(
                objective,
                steps,
                rationale="先建立可修正计划，不把未到达的消息当作事实。",
                idempotency_key=f"{wake['id']}:orient-plan",
            )
            return ActorTurnResult("已形成可修正的初始计划。")

        if wake_type == CrisisWakeType.MESSAGE.value:
            message = perspective.get("trigger", {})
            sender = message.get("sender", "")
            if actor_id == "wu-sangui" and sender == "li-zicheng":
                world.update_plan(
                    "拖住北京条件，同时等待关外答复",
                    ["不作不可逆承诺", "要求验证家属与军队条件"],
                    rationale="北京来信增加压力，但尚不足以证明条件会被履行。",
                    idempotency_key=f"{wake['id']}:li-letter-plan",
                )
                world.communicate(
                    "li-zicheng",
                    "关口愿继续议条件；请先给出家属安全与所部处置的可验证答复。",
                    idempotency_key=f"{wake['id']}:reply-li",
                )
            elif actor_id == "li-zicheng" and sender == "wu-sangui":
                world.update_plan(
                    "继续以条件争取关口，但准备替代方案",
                    ["回复可验证条件", "评估东部压力手段"],
                    rationale="吴没有拒绝，也没有承诺。",
                    idempotency_key=f"{wake['id']}:wu-reply-plan",
                )
            elif actor_id == "dorgon" and sender == "wu-sangui":
                world.update_plan(
                    "把山海关求助转化为可检验的合作机会",
                    ["要求明确政治与通行条件", "保持军队不被来使牵制"],
                    rationale="来信是真实机会，也可能是诱使改变行军的风险。",
                    belief_updates=[
                        {
                            "subject": "shanhai-request",
                            "assessment": "求助提供机会，但政治与通行条件仍未明确。",
                            "confidence": "medium",
                        }
                    ],
                    idempotency_key=f"{wake['id']}:wu-letter-plan",
                )
                world.communicate(
                    "wu-sangui",
                    "关外已收到来意。若要共同行动，请说明关口通行、指挥与承诺边界。",
                    idempotency_key=f"{wake['id']}:reply-wu",
                )
            elif actor_id == "wu-sangui" and sender == "dorgon":
                world.update_plan(
                    "把两方书面条件并列核验，延后不可逆选择",
                    ["整理关外提出的边界", "等待北京方面可验证答复", "准备关口应急部署"],
                    rationale="关外回信改变了可选项，但仍未构成必须接受的结论。",
                    idempotency_key=f"{wake['id']}:dorgon-reply-plan",
                )
            return ActorTurnResult("已按收到的信修正判断；没有替世界声明对方真实意图。")

        if wake_type == CrisisWakeType.REVISIT_DUE.value:
            return ActorTurnResult(f"第 {tick} 日复查后，暂不追加行动。")
        if wake_type == CrisisWakeType.RESOLUTION_RESULT.value:
            world.update_plan(
                "根据已经形成的局部结果调整后续处置",
                ["核验新现实是否稳定", "只保留仍可执行的有限行动"],
                rationale="危局已经形成结果，后续判断必须以已经兑现的世界事实为准。",
                idempotency_key=f"{wake['id']}:aftermath-plan",
            )
            return ActorTurnResult("已依据危局结果重新安排后续处置。")
        return ActorTurnResult("没有足够的新触发，保持当前计划。")


class HermesActorDriver:
    """Run one fresh Hermes Agent session; World effects arrive only through MCP."""

    source = "hermes"

    def __init__(self, config: AppConfig, db: ChronicleDB):
        self.config = config
        self.db = db

    def run_wake(
        self,
        actor_id: str,
        wake: dict[str, Any],
        perspective: dict[str, Any],
        world: WorldAffordanceSession,
    ) -> ActorTurnResult:
        from .hermes import (
            HermesClient,
            HermesRuntimeError,
            profile_api_key,
            read_profile_memory,
        )

        lifetime = self.db.worldline_lifetime(str(wake["worldline_id"]), actor_id)
        if lifetime is None or not lifetime["profile_name"]:
            raise HermesRuntimeError(f"live Actor Profile is missing for {actor_id}")
        profile = str(lifetime["profile_name"])
        key = profile_api_key(self.config, profile)
        if not key:
            raise HermesRuntimeError(f"live Actor Profile key is missing for {actor_id}")
        client = HermesClient(self.config)
        session_id = str(wake.get("hermes_session_id") or "")
        if not session_id:
            session_id = client.create_fresh_session(profile, key, str(wake["id"])) or ""
        if not session_id:
            raise HermesRuntimeError(f"live Hermes session creation failed for {actor_id}")
        memory_text, memory_hash = read_profile_memory(self.config, profile)
        memory_existed = (self.config.hermes_home / "profiles" / profile / "memories" / "MEMORY.md").exists()
        expected_memory_hash = str(
            wake.get("_expected_memory_hash") or lifetime["memory_hash"] or ""
        )
        if expected_memory_hash and expected_memory_hash != memory_hash:
            raise HermesRuntimeError(f"live Actor Memory hash drifted for {actor_id}")
        ordinary = wake["wake_type"] != CrisisWakeType.REFLECTION.value
        messages = self._messages(actor_id, wake, perspective)
        try:
            response_text, returned_session = client.chat(
                profile,
                key,
                messages,
                session_id,
                f"{wake['worldline_id']}:{actor_id}",
            )
        except Exception as exc:
            self._rollback_memory(
                wake,
                actor_id,
                profile,
                memory_text,
                memory_hash,
                memory_existed,
                "ordinary live Wake failed after a Memory mutation"
                if ordinary
                else "Reflection failed after an unaudited Memory mutation",
            )
            raise HermesRuntimeError(f"live Hermes Wake failed for {actor_id}") from exc
        after_text, after_hash = read_profile_memory(self.config, profile)
        if ordinary:
            if after_hash != memory_hash:
                self._rollback_memory(
                    wake,
                    actor_id,
                    profile,
                    memory_text,
                    memory_hash,
                    memory_existed,
                    "ordinary live Wake attempted a durable Memory mutation",
                )
                raise HermesRuntimeError(
                    f"ordinary live Wake attempted a durable Memory mutation for {actor_id}"
                )
        summary = response_text.strip()[:1200] or "本次 Wake 未返回文字说明。"
        return ActorTurnResult(
            summary=summary,
            session_id=returned_session or session_id,
            memory_before_text=memory_text,
            memory_before_hash=memory_hash,
            memory_before_existed=memory_existed,
            memory_text=after_text,
            memory_hash=after_hash,
            memory_changed=not ordinary and after_hash != memory_hash,
        )

    def _rollback_memory(
        self,
        wake: dict[str, Any],
        actor_id: str,
        profile: str,
        before_text: str,
        before_hash: str,
        before_existed: bool,
        reason: str,
    ) -> None:
        from .hermes import HermesRuntimeError, read_profile_memory, restore_profile_memory

        after_text, after_hash = read_profile_memory(self.config, profile)
        if after_hash == before_hash:
            return
        diff = "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile="memory.before",
                tofile="memory.after",
            )
        )
        restore_profile_memory(self.config, profile, before_existed, before_text)
        _, restored_hash = read_profile_memory(self.config, profile)
        if restored_hash != before_hash:
            raise HermesRuntimeError(f"live Actor Memory rollback failed for {actor_id}")
        self.db.add_protocol_violation(
            {
                "seat": f"{wake['worldline_id']}:{actor_id}",
                "tick": int(wake["tick"]),
                "wake_type": wake["wake_type"],
                "reason": reason,
                "memory_hash_before": before_hash,
                "memory_hash_after": after_hash,
                "memory_diff": diff,
                "action": "rollback",
                "runtime_epoch": self.db.worldline(str(wake["worldline_id"]))["runtime_epoch"],
            }
        )

    def _messages(
        self,
        actor_id: str,
        wake: dict[str, Any],
        perspective: dict[str, Any],
    ) -> list[dict[str, str]]:
        memory_rule = (
            "这是 Reflection Wake；只有确有长期经验需要保留时才可调用 memory，否则保持不变。"
            if wake["wake_type"] == CrisisWakeType.REFLECTION.value
            else "这是普通 Wake；不得调用 memory。"
        )
        orient_rule = (
            "这是 ORIENT：你必须用 update_plan 登记当前准备如何处理危局；内容由你决定。"
            "可以有计划而不安排 Revisit；直到真的有新信息再醒来也完全合法。"
            if wake["wake_type"] == CrisisWakeType.ORIENT.value
            else "只在本次触发确实改变判断时更新计划；没有新行动是合法结果。"
        )
        return [
            {
                "role": "system",
                "content": (
                    "你是 Chronicle 危局中的长期历史主体，不是旁白、史官或游戏主持。"
                    "只依据本次私有视野判断；不要使用后世知识。世界事实只能通过 chronicle-world 工具改变。"
                    "你可以更新自己的计划和少量信念、安排未来 Revisit、通信或请求有限行动。"
                    "工具拒绝不是 Wake 失败：可在同一 Agent Loop 中修正参数或选择不行动。"
                    "调用参数：update_plan(objective, steps, rationale, belief_updates, reconsider_when, idempotency_key)；"
                    "schedule_revisit(after_days, reason, idempotency_key)；"
                    "communicate(recipient, content, idempotency_key)；"
                    "investigate(question, target, method, idempotency_key)，"
                    "可用调查及其 target/method 已在私有视野 available_investigations 中列出；"
                    "manage_offer(action, offer_id, recipient, terms, message, expires_after_days, idempotency_key)，"
                    "可用条件、待回应 Offer 与生效 Agreement 已在私有视野中列出；"
                    "operate(operation_definition_id, targets, description, idempotency_key)，"
                    "可用 Operation 及其 target 已在私有视野 available_operations 中列出。"
                    "每个 idempotency_key 在本次 Wake 内唯一。"
                    "不要声称工具尚未确认的结果。最终只用简体中文简短说明你如何处置本次触发。"
                    + orient_rule
                    + memory_rule
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "wake_id": wake["id"],
                        "wake_type": wake["wake_type"],
                        "actor_id": actor_id,
                        "private_perspective": perspective,
                        "available_world_tools": [
                            "communicate",
                            "investigate",
                            "manage_offer",
                            "operate",
                            "update_plan",
                            "schedule_revisit",
                        ],
                        "tool_budget": 8,
                    },
                    ensure_ascii=False,
                ),
            },
        ]


class CrisisRunEngine:
    def __init__(
        self,
        config: AppConfig,
        *,
        db: ChronicleDB | None = None,
        pack: CrisisPack | None = None,
        actor_driver: ActorDriver | None = None,
    ):
        self.config = config
        self.db = db or ChronicleDB(config.database_path)
        self.registry = VolumeRegistry.load(config.volume_path)
        self.pack = pack or self.registry.default_pack
        active = self.db.active_run()
        self._actor_driver_provided = actor_driver is not None
        self.actor_driver = actor_driver or (
            HermesActorDriver(config, self.db)
            if active is not None and active["runtime_mode"] == "live"
            else FixtureActorDriver()
        )
        self.world = WorldService(self.db, self.pack)

    def select_crisis(self, crisis_id: str) -> CrisisPack:
        pack = self.registry.pack(crisis_id)
        self.pack = pack
        self.world = WorldService(self.db, pack)
        return pack

    def _activate_run_pack(self, run_id: str) -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run not found")
        if self.pack.crisis.id != run["crisis_id"]:
            self.select_crisis(str(run["crisis_id"]))
        return run

    def create(
        self,
        mode: RunMode | str,
        *,
        runtime_mode: str = "fixture",
        human_actor_id: str | None = None,
        crisis_id: str | None = None,
    ) -> dict[str, Any]:
        mode = RunMode(mode)
        if crisis_id is not None:
            self.select_crisis(crisis_id)
        if self.db.active_run() is not None or self.db.active_human_worldline() is not None:
            raise CrisisRunConflict("an active Chronicle Run already exists")
        if runtime_mode not in {"fixture", "live"}:
            raise CrisisRunError("runtime_mode must be fixture or live")
        if mode == RunMode.WATCH and human_actor_id is not None:
            raise CrisisRunError("WATCH Runs cannot select a Human actor")
        selected_human_actor: str | None = None
        if mode == RunMode.TAKEOVER:
            selected_human_actor = human_actor_id or next(
                iter(self.pack.crisis.playable_actor_ids), None
            )
            if selected_human_actor is None:
                raise CrisisRunError("this Crisis has no playable actor")
            if selected_human_actor not in self.pack.crisis.playable_actor_ids:
                raise CrisisRunError("Human actor is not playable in this Crisis")

        run_id = f"run-{uuid.uuid4().hex[:16]}"
        controllers = {
            actor.id: (
                "HUMAN"
                if actor.id == selected_human_actor
                else "AGENT"
            )
            for actor in self.pack.crisis.actors
        }
        epoch = (
            f"fixture-{stable_hash({'crisis': self.pack.crisis.id})[:12]}"
            if runtime_mode == "fixture"
            else f"hermes-{self.config.provider_hash()}-{uuid.uuid4().hex[:8]}"
        )
        if runtime_mode == "live" and not self._actor_driver_provided:
            self.actor_driver = HermesActorDriver(self.config, self.db)
        projection = {
            "crisis_id": self.pack.crisis.id,
            "tick": 0,
            "positions": {
                actor.id: actor.initial_location for actor in self.pack.crisis.actors
            },
            "messages": [
                {
                    "id": message.id,
                    "sender": message.sender,
                    "recipient": message.recipient,
                    "content": message.content,
                    "dispatch_tick": message.dispatch_tick,
                    "arrival_tick": message.delivery_tick,
                    "status": "in_transit",
                    "source": "checkpoint",
                    "disputed": message.disputed,
                    "assertion_ids": list(message.assertion_ids),
                }
                for message in self.pack.crisis.checkpoint.in_transit
            ],
            "movements": [],
            "entities": {
                entity.id: {
                    "id": entity.id,
                    "type": entity.type.value,
                    "display_name": entity.display_name,
                    "state": entity.initial_state,
                    "assertion_ids": list(entity.assertion_ids),
                }
                for entity in self.pack.crisis.entities
            },
            "operations": [],
            "investigations": [],
            "offers": [],
            "agreements": [],
            "resolution": {"status": "OPEN"},
            "resolution_reports": [],
            "settlement": {"status": "OPEN"},
            "pressures": [
                {
                    "id": pressure.id,
                    "kind": pressure.kind.value,
                    "title": pressure.title,
                    "description": pressure.description,
                    "trigger_tick": pressure.trigger_tick,
                    "preconditions": [
                        condition.model_dump(mode="json")
                        for condition in pressure.preconditions
                    ],
                    "effects": [effect.model_dump(mode="json") for effect in pressure.effects],
                    "status": PressureStatus.PENDING.value,
                    "visibility": pressure.visibility.value,
                    "visible_actor_ids": list(pressure.visible_actor_ids),
                    "provenance": pressure.provenance.value,
                    "assertion_ids": list(pressure.assertion_ids),
                }
                for pressure in self.pack.crisis.pressures
            ],
        }
        events = [
            self._event(
                run_id,
                0,
                "RUN_CREATED",
                {
                    "volume_id": self.registry.volume.id,
                    "crisis_id": self.pack.crisis.id,
                    "crisis_version": self.pack.crisis.version,
                    "crisis_hash": self.pack.content_hash,
                    "resolution_contract_id": self.pack.crisis.resolution_contract.id,
                    "resolution_contract_version": self.pack.crisis.resolution_contract.version,
                    "resolution_seed": uuid.uuid4().hex,
                    "crisis_phase": "OPEN",
                    "mode": mode.value,
                    "controller_map": controllers,
                    "runtime_mode": runtime_mode,
                },
            ),
            self._event(
                run_id,
                0,
                "CRISIS_CHECKPOINT_ENTERED",
                {
                    "native_date_window": self.pack.crisis.checkpoint.native_date_window,
                    "fact_assertion_ids": self.pack.crisis.checkpoint.facts,
                    "unresolved": self.pack.crisis.checkpoint.unresolved,
                },
                provenance="historical",
            ),
        ]
        events[1]["causal_parent_ids"] = [events[0]["id"]]
        checkpoint_event_id = events[-1]["id"]
        for entity in projection["entities"].values():
            events.append(
                self._event(
                    run_id,
                    0,
                    "ENTITY_INITIALIZED",
                    entity,
                    provenance="scenario_assumption",
                    causal_parent_ids=[checkpoint_event_id],
                )
            )
        for message in projection["messages"]:
            dispatch = self._event(
                run_id,
                0,
                "MESSAGE_DISPATCHED",
                message,
                seat_id=message["sender"],
                provenance="scenario_assumption",
                causal_parent_ids=[checkpoint_event_id],
            )
            message["dispatch_event_id"] = dispatch["id"]
            events.append(dispatch)
        for pressure in projection["pressures"]:
            scheduled = self._event(
                run_id,
                0,
                "PRESSURE_SCHEDULED",
                {"pressure": pressure, "visibility": []},
                provenance=pressure["provenance"],
                causal_parent_ids=[checkpoint_event_id],
            )
            pressure["scheduled_event_id"] = scheduled["id"]
            events.append(scheduled)

        lifetimes: list[dict[str, Any]] = []
        for actor in self.pack.crisis.actors:
            perspective = self.pack.initial_perspective(actor.id)
            memory_text = ""
            memory_hash = content_hash("")
            if controllers[actor.id] == "AGENT":
                if runtime_mode == "fixture":
                    profile_name = f"fixture://{actor.id}"
                    profile_metadata = {"source": runtime_mode}
                else:
                    from .hermes import (
                        _crisis_profile_name,
                        _crisis_world_server_name,
                        stable_profile_marker,
                    )

                    profile_name = _crisis_profile_name(run_id, actor.id)
                    profile_metadata = {
                        "source": runtime_mode,
                        "ownership_marker": stable_profile_marker(run_id, actor.id, profile_name),
                        "world_server_name": _crisis_world_server_name(run_id, actor.id),
                    }
            else:
                profile_name = ""
                profile_metadata = {}
            lifetimes.append(
                {
                    "id": f"life-{uuid.uuid4().hex[:16]}",
                    "actor_id": actor.id,
                    "controller": controllers[actor.id],
                    "profile_name": profile_name,
                    "profile_metadata": profile_metadata,
                    "genesis_hash": stable_hash(perspective),
                    "memory_text": memory_text,
                    "memory_hash": memory_hash,
                    "knowledge": list(perspective["knowledge"]),
                    "beliefs": dict(actor.initial_beliefs),
                    "authority": list(actor.world_authority),
                    "role_charter": actor.role_charter.model_dump(mode="json"),
                    "plan": [],
                    "revisits": [],
                    "resources": dict(actor.resources),
                    "last_perspective": perspective,
                }
            )
        try:
            run = self.db.create_crisis_run_bundle(
                {
                    "id": run_id,
                    "volume_id": self.registry.volume.id,
                    "crisis_id": self.pack.crisis.id,
                    "crisis_version": self.pack.crisis.version,
                    "crisis_hash": self.pack.content_hash,
                    "resolution_contract_id": self.pack.crisis.resolution_contract.id,
                    "resolution_contract_version": self.pack.crisis.resolution_contract.version,
                    "resolution_seed": events[0]["payload"]["resolution_seed"],
                    "crisis_phase": "OPEN",
                    "controller_map": controllers,
                    "simulation_boundary": self.pack.crisis.simulation_boundary.model_dump(mode="json"),
                    "runtime_mode": runtime_mode,
                    "runtime_epoch": epoch,
                    "runtime_phase": "BOOTSTRAPPING" if runtime_mode == "live" else "READY",
                },
                events,
                lifetimes,
                projection,
            )
        except Exception:
            raise
        if runtime_mode == "live":
            return {"run": run, "lifetimes": self.db.worldline_lifetimes(run_id)}
        for actor_id, controller in controllers.items():
            if controller != "AGENT":
                continue
            profile_name = f"fixture://{actor_id}"
            self.db.create_agent_binding(
                {
                    "worldline_id": run_id,
                    "actor_id": actor_id,
                    "profile_name": profile_name,
                    "ownership_marker": (
                        stable_hash(
                            {"run_id": run_id, "actor_id": actor_id, "source": "fixture"}
                        )
                    ),
                    "token_hash": "",
                }
            )
            self._queue_wake(run_id, actor_id, CrisisWakeType.ORIENT, 0)
        return {"run": run, "lifetimes": self.db.worldline_lifetimes(run_id)}

    def live_profile_specs(self, run_id: str) -> list[dict[str, Any]]:
        run = self._activate_run_pack(run_id)
        if run is None or run["kind"] != "CRISIS" or run["runtime_mode"] != "live":
            raise CrisisRunError("live Run not found")
        specs: list[dict[str, Any]] = []
        for lifetime in self.db.worldline_lifetimes(run_id):
            if lifetime["controller"] != "AGENT":
                continue
            actor = self.pack.actor_by_id[lifetime["seat"]]
            metadata = dict(lifetime["profile_metadata"])
            specs.append(
                {
                    "id": actor.id,
                    "profile": lifetime["profile_name"],
                    "world_server_name": metadata.get("world_server_name", ""),
                    "ownership_marker": metadata.get("ownership_marker", ""),
                    "role_charter": actor.role_charter.model_dump(mode="json"),
                    "genesis_hash": lifetime["genesis_hash"],
                    "initial_memory_snapshot": {
                        "memory_text": lifetime["memory_text"],
                        "memory_hash": lifetime["memory_hash"],
                    },
                }
            )
        return specs

    def activate_live_runtime(self, run_id: str, records: dict[str, dict[str, Any]]) -> None:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        if run["runtime_mode"] != "live":
            raise CrisisRunError("Run does not use the live runtime")
        specs = self.live_profile_specs(run_id)
        bindings: list[dict[str, Any]] = []
        wakes: list[dict[str, Any]] = []
        for spec in specs:
            actor_id = str(spec["id"])
            record = records.get(actor_id)
            if record is None:
                raise CrisisRunError("live Profile materialization is incomplete")
            if (
                record.get("profile") != spec["profile"]
                or record.get("ownership_marker") != spec["ownership_marker"]
                or record.get("world_server_name") != spec["world_server_name"]
            ):
                raise CrisisRunError("live Profile identity does not match the Run")
            bindings.append(
                {
                    "actor_id": actor_id,
                    "profile_name": str(record["profile"]),
                    "ownership_marker": str(record["ownership_marker"]),
                    "token_hash": token_hash(str(record["world_token"])),
                }
            )
            wakes.append(
                {
                    "actor_id": actor_id,
                    "wake_type": CrisisWakeType.ORIENT.value,
                    "tick": 0,
                    "source": "hermes",
                }
            )
        self.db.activate_crisis_runtime(run_id, bindings, wakes)

    def initial_orient_completed(self, run_id: str) -> bool:
        expected = {str(spec["id"]) for spec in self.live_profile_specs(run_id)}
        wakes = [
            wake
            for wake in self.db.crisis_wakes(run_id, tick=0)
            if wake["wake_type"] == CrisisWakeType.ORIENT.value
        ]
        by_actor = {str(wake["actor_id"]): wake for wake in wakes}
        if set(by_actor) != expected or not expected:
            return False
        for wake in by_actor.values():
            if wake["status"] != "COMPLETED":
                return False
            if not any(
                operation["tool_name"] == "update_plan" and operation["status"] == "COMMITTED"
                for operation in self.db.crisis_wake_operations(wake["id"])
            ):
                return False
        return True

    def mark_live_runtime_ready(self, run_id: str) -> dict[str, Any]:
        if not self.initial_orient_completed(run_id):
            raise CrisisRunError("initial live Orient has not completed")
        return self.db.set_crisis_runtime_state(run_id, "READY")

    def mark_live_runtime_failed(self, run_id: str, code: str) -> dict[str, Any]:
        return self.db.set_crisis_runtime_state(run_id, "FAILED", error_code=code)

    def run_until_idle(self, run_id: str, *, max_moments: int = 80) -> dict[str, Any]:
        moments = 0
        while moments < max_moments and self.advance_one(run_id):
            moments += 1
        if moments >= max_moments and self._next_tick(run_id) is not None:
            raise CrisisRunError("fixture exceeded the finite moment budget")
        run = self.db.active_run() or self.db.worldline(run_id)
        return {
            "run": run,
            "moments": moments,
            "wakes": self.db.crisis_wakes(run_id),
            "events": self.db.worldline_events(run_id),
        }

    def advance_to_attention(self, run_id: str, *, max_moments: int = 80) -> dict[str, Any]:
        run = self._activate_run_pack(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        start_tick = int(run["current_tick"])
        human_attention = self._human_attention(run_id)
        if human_attention is not None:
            return {
                "advanced": False,
                "attention": human_attention,
                "moments": 0,
                "from_tick": start_tick,
                "to_tick": start_tick,
            }

        moments = 0
        while moments < max_moments:
            event_count = len(self.db.worldline_events(run_id))
            if not self.advance_one(run_id):
                current = self.db.worldline(run_id)
                return {
                    "advanced": moments > 0,
                    "attention": None,
                    "moments": moments,
                    "from_tick": start_tick,
                    "to_tick": int(current["current_tick"]) if current is not None else start_tick,
                }
            moments += 1
            current = self.db.worldline(run_id)
            if current is None:
                raise CrisisRunError("Run disappeared while advancing")
            if current["status"] == "SEALED":
                return {
                    "advanced": True,
                    "attention": {
                        "mode": "SETTLEMENT",
                        "tick": int(current["current_tick"]),
                        "event_type": "CRISIS_SETTLED",
                    },
                    "moments": moments,
                    "from_tick": start_tick,
                    "to_tick": int(current["current_tick"]),
                }
            if self._human_actor_id(run_id) is not None:
                human_attention = self._human_attention(run_id)
                if human_attention is not None:
                    return {
                        "advanced": True,
                        "attention": human_attention,
                        "moments": moments,
                        "from_tick": start_tick,
                        "to_tick": int(current["current_tick"]),
                    }
                continue
            watch_attention = self._watch_attention(self.db.worldline_events(run_id)[event_count:])
            if watch_attention is not None:
                return {
                    "advanced": True,
                    "attention": watch_attention,
                    "moments": moments,
                    "from_tick": start_tick,
                    "to_tick": int(current["current_tick"]),
                }

        if self._next_tick(run_id) is not None:
            raise CrisisRunError("attention scheduler exceeded the finite moment budget")
        current = self.db.worldline(run_id)
        return {
            "advanced": moments > 0,
            "attention": None,
            "moments": moments,
            "from_tick": start_tick,
            "to_tick": int(current["current_tick"]) if current is not None else start_tick,
        }

    def _human_attention(self, run_id: str) -> dict[str, Any] | None:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run not found")
        actor_id = self._human_actor_id(run_id)
        if actor_id is None:
            return None
        tick = int(run["current_tick"])
        if self.human_decision_state(run_id, tick)["state"] != "NONE":
            return None
        interruptions = [
            event
            for event in self.db.worldline_events(run_id)
            if event["event_type"] == "HUMAN_INTERRUPTION_READY"
            and event["seat_id"] == actor_id
            and int(event["tick"]) == tick
        ]
        if interruptions:
            return {
                "mode": "TAKEOVER",
                "actor_id": actor_id,
                "tick": tick,
                "reasons": [
                    {
                        "wake_type": event["payload"]["wake_type"],
                        "trigger_event_id": event["payload"]["trigger_event_id"],
                    }
                    for event in interruptions
                ],
            }
        if tick == self.pack.crisis.checkpoint.start_tick:
            return {
                "mode": "TAKEOVER",
                "actor_id": actor_id,
                "tick": tick,
                "reasons": [{"wake_type": "INITIAL_DECISION", "trigger_event_id": ""}],
            }
        return None

    @staticmethod
    def _watch_attention(events: list[dict[str, Any]]) -> dict[str, Any] | None:
        for event in events:
            event_type = str(event["event_type"])
            if event_type in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
                if event["payload"].get("source") == "checkpoint":
                    continue
            elif event_type not in WATCH_ATTENTION_EVENT_TYPES:
                continue
            return {
                "mode": "WATCH",
                "tick": int(event["tick"]),
                "event_id": event["id"],
                "event_type": event_type,
            }
        return None

    def human_decision_state(self, run_id: str, tick: int | None = None) -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run not found")
        human_actor_id = self._human_actor_id(run_id)
        current_tick = int(run["current_tick"] if tick is None else tick)
        if human_actor_id is None:
            return {"state": "NONE", "kind": "", "tick": current_tick}
        decision_wake = next(
            (
                wake
                for wake in self.db.crisis_wakes(run_id, tick=current_tick)
                if wake["actor_id"] == human_actor_id
                and wake["wake_type"] == "DECISION"
                and wake["trigger_event_id"] == ""
            ),
            None,
        )
        if decision_wake is not None:
            wake_state = {
                "COMPLETED": "COMMITTED",
                "FAILED": "FAILED",
            }.get(str(decision_wake["status"]), "RUNNING")
            return {
                "state": wake_state,
                "kind": (
                    "silence"
                    if decision_wake.get("result", {}).get("silence")
                    else "decision"
                ),
                "tick": current_tick,
            }
        if any(
            event["event_type"] == "HUMAN_SILENCE"
            and event["seat_id"] == human_actor_id
            and int(event["tick"]) == current_tick
            for event in self.db.worldline_events(run_id)
        ):
            return {"state": "COMMITTED", "kind": "silence", "tick": current_tick}
        return {"state": "NONE", "kind": "", "tick": current_tick}

    def _human_decision_conflict(self, run_id: str, tick: int) -> CrisisRunConflict:
        state = self.human_decision_state(run_id, tick)
        if state["state"] == "COMMITTED":
            return CrisisRunConflict(
                "当前模拟日已经提交过决定，请先继续推进。",
                code="decision_already_exists",
                state="COMMITTED",
                tick=tick,
            )
        if state["state"] == "FAILED":
            return CrisisRunConflict(
                "当前模拟日的决定处理失败，请先核对这一局的状态。",
                code="decision_failed",
                state="FAILED",
                tick=tick,
            )
        return CrisisRunConflict(
            "当前模拟日的决定仍在处理中，请稍候。",
            code="decision_in_progress",
            state="RUNNING",
            tick=tick,
        )

    def submit_human_decision(
        self,
        run_id: str,
        text: str,
        *,
        interpreter: DecisionInterpreter | None = None,
    ) -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        self._activate_run_pack(run_id)
        if run["runtime_mode"] == "live" and run.get("runtime_phase") != "READY":
            raise CrisisRunConflict(
                "这一局正在准备或恢复，暂不能提交决定。",
                code="runtime_not_ready",
                state=str(run.get("runtime_phase") or "FAILED"),
            )
        human_actor_id = self._human_actor_id(run_id)
        if human_actor_id is None:
            raise CrisisRunError("this Run has no Human decision desk")
        tick = int(run["current_tick"])
        if self.human_decision_state(run_id, tick)["state"] != "NONE":
            raise self._human_decision_conflict(run_id, tick)
        if not text.strip():
            snapshot = self.db.worldline_snapshot(run_id)
            if snapshot is None:
                raise CrisisRunError("Run snapshot is missing")
            lifetime = self.db.worldline_lifetime(run_id, human_actor_id)
            if lifetime is None:
                raise CrisisRunError("Human life state is missing")
            try:
                wake = self.db.create_crisis_wake(
                    {
                        "worldline_id": run_id,
                        "actor_id": human_actor_id,
                        "wake_type": "DECISION",
                        "tick": tick,
                        "status": "RUNNING",
                        "source": "human",
                        "hermes_session_id": f"human-{uuid.uuid4().hex[:12]}",
                        "frozen_perspective": self._perspective_from(
                            run_id, human_actor_id, snapshot["projection"]
                        ),
                    }
                )
            except sqlite3.IntegrityError as exc:
                raise self._human_decision_conflict(run_id, tick) from exc
            try:
                event = self._event(
                    run_id,
                    tick,
                    "HUMAN_SILENCE",
                    {"visibility": [human_actor_id]},
                    seat_id=human_actor_id,
                )
                revisits = list(lifetime["revisits"])
                fulfilled_events = self._resolve_human_revisits(
                    run_id,
                    tick,
                    revisits,
                    event["id"],
                    human_actor_id,
                )
                self.db.commit_worldline_moment(
                    run_id,
                    [event, *fulfilled_events],
                    current_tick=tick,
                    lifetime_updates=[
                        {
                            "seat": human_actor_id,
                            "revisits_json": json.dumps(
                                revisits, ensure_ascii=False, sort_keys=True
                            ),
                        }
                    ],
                    snapshot=snapshot["projection"],
                )
            except Exception as exc:
                self.db.update_crisis_wake(
                    wake["id"], status="FAILED", error={"type": type(exc).__name__}
                )
                raise CrisisRunError("Human silence could not be safely applied") from exc
            self.db.update_crisis_wake(
                wake["id"],
                status="COMPLETED",
                result={"silence": True, "summary": "暂不追加命令，继续观察。"},
            )
            self._advance_crisis_lifecycle(run_id)
            return {"silence": True, "events": [event, *fulfilled_events], "operations": []}

        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        perspective = self._perspective_from(run_id, human_actor_id, projection)
        try:
            wake = self.db.create_crisis_wake(
                {
                    "worldline_id": run_id,
                    "actor_id": human_actor_id,
                    "wake_type": "DECISION",
                    "tick": tick,
                    "status": "RUNNING",
                    "source": "human",
                    "hermes_session_id": f"human-{uuid.uuid4().hex[:12]}",
                    "frozen_perspective": perspective,
                }
            )
        except sqlite3.IntegrityError as exc:
            raise self._human_decision_conflict(run_id, tick) from exc
        selected = interpreter or (
            ModelDecisionInterpreter(
                self.config,
                recipient_catalog=tuple(
                    {
                        "id": actor.id,
                        "display_name": actor.display_name,
                    }
                    for actor in self.pack.crisis.actors
                    if actor.id != human_actor_id
                ),
            )
            if run["runtime_mode"] == "live"
            else FixtureDecisionInterpreter()
        )
        try:
            interpretation = selected.interpret(text.strip(), perspective)
            world = self.world.human_session(wake["id"], human_actor_id)
            for index, operation in enumerate(interpretation.operations):
                self._invoke_decision_operation(
                    world,
                    operation.tool,
                    operation.arguments,
                    idempotency_key=f"{wake['id']}:{index}",
                )
            events = self._commit_human_wake(
                run_id,
                tick,
                projection,
                wake,
                interpretation.summary,
                selected.source,
                human_actor_id,
            )
        except Exception as exc:
            self.db.update_crisis_wake(
                wake["id"], status="FAILED", error={"type": type(exc).__name__}
            )
            raise CrisisRunError("Human decision could not be safely applied") from exc
        self._advance_crisis_lifecycle(run_id)
        return {
            "silence": False,
            "summary": interpretation.summary,
            "events": events,
            "operations": self.db.crisis_wake_operations(wake["id"]),
        }

    @staticmethod
    def _invoke_decision_operation(
        world: WorldAffordanceSession,
        tool: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        values = dict(arguments)
        values["idempotency_key"] = idempotency_key
        if tool == "communicate":
            return world.communicate(**values)
        if tool == "investigate":
            return world.investigate(**values)
        if tool == "manage_offer":
            return world.manage_offer(**values)
        if tool == "operate":
            return world.operate(**values)
        if tool == "update_plan":
            return world.update_plan(**values)
        if tool == "schedule_revisit":
            return world.schedule_revisit(**values)
        raise CrisisRunError(f"unsupported decision operation: {tool}")

    def _commit_human_wake(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        summary: str,
        source: str,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        lifetime = self.db.worldline_lifetime(run_id, actor_id)
        if lifetime is None:
            raise CrisisRunError("Human life state is missing")
        state = {
            "plan": list(lifetime["plan"]),
            "beliefs": dict(lifetime["beliefs"]),
            "revisits": list(lifetime["revisits"]),
        }
        decision_event = self._event(
            run_id,
            tick,
            "HUMAN_DECISION_APPLIED",
            {
                "summary": summary,
                "interpreter_source": source,
                "operation_count": len(self.db.crisis_wake_operations(wake["id"])),
                "visibility": [actor_id],
            },
            seat_id=actor_id,
        )
        events: list[dict[str, Any]] = [decision_event]
        events.extend(
            self._resolve_human_revisits(
                run_id,
                tick,
                state["revisits"],
                decision_event["id"],
                actor_id,
            )
        )
        queued_wakes: list[dict[str, Any]] = []
        commit_time_refusals: list[dict[str, Any]] = []
        operations = self.db.crisis_wake_operations(wake["id"])
        causal_parent_id = decision_event["id"]
        for operation in operations:
            if operation["status"] == "REJECTED":
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "HUMAN_REQUEST_REJECTED",
                        {
                            "tool": operation["tool_name"],
                            "code": operation["result"].get("code", "rejected"),
                            "visibility": [actor_id],
                        },
                        seat_id=actor_id,
                        causal_parent_ids=[decision_event["id"]],
                    )
                )
                continue
            events.append(
                self._event(
                    run_id,
                    tick,
                    "HUMAN_REQUEST_INTERPRETED",
                    {"tool": operation["tool_name"], "visibility": [actor_id]},
                    seat_id=actor_id,
                    causal_parent_ids=[causal_parent_id],
                )
            )
            causal_parent_id = self._apply_operation(
                run_id,
                tick,
                projection,
                wake,
                operation,
                state,
                events,
                queued_wakes,
                commit_refusals=commit_time_refusals,
                source="human",
                causal_parent_id=causal_parent_id,
            )
        projection["tick"] = tick
        perspective = self._perspective_from(
            run_id,
            actor_id,
            projection,
            beliefs=state["beliefs"],
            plan=state["plan"],
            revisits=state["revisits"],
        )
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=[
                {
                    "seat": actor_id,
                    "belief_json": json.dumps(state["beliefs"], ensure_ascii=False, sort_keys=True),
                    "plan_json": json.dumps(state["plan"], ensure_ascii=False, sort_keys=True),
                    "revisits_json": json.dumps(
                        state["revisits"], ensure_ascii=False, sort_keys=True
                    ),
                    "last_perspective_json": json.dumps(
                        perspective, ensure_ascii=False, sort_keys=True
                    ),
                }
            ],
            snapshot=projection,
        )
        for operation in operations:
            if operation["status"] == "PROPOSED":
                self.db.update_crisis_wake_operation_status(operation["id"], "COMMITTED")
            elif operation["status"] == "REJECTED":
                self.db.update_crisis_wake_operation_status(
                    operation["id"],
                    "REJECTED",
                    result=operation["result"],
                )
        self.db.update_crisis_wake(
            wake["id"], status="COMPLETED", result={"summary": summary}
        )
        for item in queued_wakes:
            self._queue_wake(**item)
        return events

    def _resolve_human_revisits(
        self,
        run_id: str,
        tick: int,
        revisits: list[dict[str, Any]],
        decision_event_id: str,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for revisit in revisits:
            if revisit["status"] != "DUE":
                continue
            revisit["status"] = "FULFILLED"
            parents = [decision_event_id]
            if revisit.get("due_event_id") or revisit.get("event_id"):
                parents.insert(0, revisit.get("due_event_id") or revisit["event_id"])
            events.append(
                self._event(
                    run_id,
                    tick,
                    "REVISIT_FULFILLED",
                    {
                        "revisit_id": revisit["id"],
                        "visibility": [actor_id],
                    },
                    seat_id=actor_id,
                    causal_parent_ids=parents,
                )
            )
        return events

    @staticmethod
    def _mark_revisits_due(revisits: list[dict[str, Any]], tick: int) -> list[dict[str, Any]]:
        due: list[dict[str, Any]] = []
        for revisit in revisits:
            if revisit["status"] != "PENDING" or int(revisit["due_tick"]) != tick:
                continue
            revisit["status"] = "DUE"
            due.append(revisit)
        return due

    def _resolution_contract_for_run(self, run: dict[str, Any]):
        return get_resolution_contract(
            str(run["resolution_contract_id"]), int(run["resolution_contract_version"])
        )

    def _advance_crisis_lifecycle(self, run_id: str) -> None:
        """Move the Crisis phase only after a committed world moment."""

        run = self.db.worldline(run_id)
        if run is None or run["status"] != "ACTIVE":
            return
        phase = str(run.get("crisis_phase") or "OPEN")
        if phase == "OPEN":
            self._begin_resolution_if_ready(run_id, run)
        elif phase == "AFTERMATH":
            self._settle_if_stable(run_id, run)

    def _begin_resolution_if_ready(self, run_id: str, run: dict[str, Any]) -> bool:
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        contract = self._resolution_contract_for_run(run)
        readiness = contract.evaluate_gate(projection)
        if readiness.status != ResolutionGateStatus.READY:
            return False
        tick = int(run["current_tick"])
        existing_events = self.db.worldline_events(run_id)
        gate = self._event(
            run_id,
            tick,
            "RESOLUTION_GATE_REACHED",
            {
                "readiness": readiness.to_dict(),
                "visibility": sorted(self.pack.actor_by_id),
            },
            causal_parent_ids=[existing_events[-1]["id"]] if existing_events else [],
        )
        projection["resolution"] = {
            "status": "PENDING",
            "gate_event_id": gate["id"],
            "gate_tick": tick,
            "readiness": readiness.to_dict(),
        }
        self.db.commit_worldline_moment(
            run_id,
            [gate],
            current_tick=tick,
            snapshot=projection,
            crisis_phase="RESOLUTION_PENDING",
        )
        human_actor_id = self._human_actor_id(run_id)
        if human_actor_id is not None:
            self._queue_wake(
                run_id,
                human_actor_id,
                CrisisWakeType.RESOLUTION_GATE,
                tick,
                trigger_event_id=gate["id"],
            )
        return True

    def _queued_human_resolution_gate(self, run_id: str, actor_id: str) -> bool:
        return any(
            wake["actor_id"] == actor_id
            and wake["wake_type"] == CrisisWakeType.RESOLUTION_GATE.value
            and wake["status"] == "QUEUED"
            for wake in self.db.crisis_wakes(run_id)
        )

    def _apply_resolution(self, run_id: str, run: dict[str, Any]) -> bool:
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        tick = int(run["current_tick"])
        projection["tick"] = tick
        contract = self._resolution_contract_for_run(run)
        readiness = contract.evaluate_gate(projection)
        if readiness.status != ResolutionGateStatus.READY:
            existing_events = self.db.worldline_events(run_id)
            reopened = self._event(
                run_id,
                tick,
                "RESOLUTION_GATE_REOPENED",
                {
                    "readiness": readiness.to_dict(),
                    "visibility": sorted(self.pack.actor_by_id),
                },
                causal_parent_ids=[existing_events[-1]["id"]] if existing_events else [],
            )
            projection["resolution"] = {"status": "OPEN", "readiness": readiness.to_dict()}
            self.db.commit_worldline_moment(
                run_id,
                [reopened],
                current_tick=tick,
                snapshot=projection,
                crisis_phase="OPEN",
            )
            return True

        result = contract.resolve(projection, str(run["resolution_seed"]))
        immediate_actor_ids = sorted(
            set(result.immediate_actor_ids).intersection(self.pack.actor_by_id)
        )
        if not immediate_actor_ids:
            raise CrisisRunError("Resolution result must reach at least one Actor immediately")
        result_payload = result.to_dict()
        resolved = self._event(
            run_id,
            tick,
            "RESOLUTION_APPLIED",
            {"result": result_payload, "visibility": immediate_actor_ids},
            causal_parent_ids=[
                str(projection.get("resolution", {}).get("gate_event_id") or "")
            ]
            if projection.get("resolution", {}).get("gate_event_id")
            else [],
        )
        projection["resolution"] = {
            "status": "APPLIED",
            "event_id": resolved["id"],
            "applied_tick": tick,
            "readiness": readiness.to_dict(),
            "result": result_payload,
        }
        events: list[dict[str, Any]] = [resolved]
        for effect in result.entity_effects:
            entity = projection.get("entities", {}).get(effect.entity_id)
            if entity is None:
                raise CrisisRunError(f"Resolution references unknown entity {effect.entity_id}")
            before = str(entity["state"])
            entity["state"] = effect.state
            if before == effect.state:
                continue
            events.append(
                self._event(
                    run_id,
                    tick,
                    "RESOLUTION_ENTITY_EFFECT",
                    {
                        "entity_id": effect.entity_id,
                        "before": before,
                        "after": effect.state,
                        "description": effect.description,
                        "visibility": immediate_actor_ids,
                    },
                    causal_parent_ids=[resolved["id"]],
                )
            )
        agreements = {
            str(agreement["id"]): agreement
            for agreement in projection.get("agreements", [])
        }
        for effect in result.agreement_effects:
            agreement = agreements.get(effect.agreement_id)
            if agreement is None:
                raise CrisisRunError(f"Resolution references unknown agreement {effect.agreement_id}")
            before = str(agreement["status"])
            agreement["status"] = effect.status
            if before == effect.status:
                continue
            events.append(
                self._event(
                    run_id,
                    tick,
                    "RESOLUTION_AGREEMENT_EFFECT",
                    {
                        "agreement_id": effect.agreement_id,
                        "before": before,
                        "after": effect.status,
                        "description": effect.description,
                        "visibility": sorted(set(agreement.get("parties", []))),
                    },
                    causal_parent_ids=[resolved["id"]],
                )
            )

        knowledge_by_actor: dict[str, list[Any]] = {}
        for actor_id in immediate_actor_ids:
            lifetime = self.db.worldline_lifetime(run_id, actor_id)
            if lifetime is None:
                raise CrisisRunError("resolution observer life state is missing")
            knowledge = list(lifetime["knowledge"])
            knowledge.append(
                {
                    "kind": "resolution",
                    "event_id": resolved["id"],
                    "resolution_kind": result.kind.value,
                    "content": result.summary,
                    "obtained_tick": tick,
                }
            )
            knowledge_by_actor[actor_id] = knowledge

        reports = projection.setdefault("resolution_reports", [])
        for actor_id in sorted(set(self.pack.actor_by_id) - set(immediate_actor_ids)):
            report = {
                "id": f"resolution-report-{uuid.uuid4().hex[:16]}",
                "recipient": actor_id,
                "resolution_event_id": resolved["id"],
                "resolution_kind": result.kind.value,
                "content": result.summary,
                "dispatched_tick": tick,
                "expected_tick": tick + 2,
                "status": "IN_TRANSIT",
            }
            reports.append(report)
            dispatched = self._event(
                run_id,
                tick,
                "RESOLUTION_REPORT_DISPATCHED",
                {"report": report, "visibility": [actor_id]},
                causal_parent_ids=[resolved["id"]],
            )
            report["dispatch_event_id"] = dispatched["id"]
            events.append(dispatched)

        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
            crisis_phase="AFTERMATH",
        )
        for actor_id in immediate_actor_ids:
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.RESOLUTION_RESULT,
                tick + 1,
                trigger_event_id=resolved["id"],
            )
        return True

    @staticmethod
    def _resolution_reports_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            report
            for report in projection.get("resolution_reports", [])
            if report.get("status") == "IN_TRANSIT" and int(report["expected_tick"]) == tick
        ]

    def _commit_resolution_reports(
        self, run_id: str, tick: int, projection: dict[str, Any]
    ) -> None:
        due = self._resolution_reports_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        knowledge_by_actor: dict[str, list[Any]] = {}
        for report in due:
            actor_id = str(report["recipient"])
            report["status"] = "DELIVERED"
            delivered = self._event(
                run_id,
                tick,
                "RESOLUTION_REPORT_DELIVERED",
                {"report": report, "visibility": [actor_id]},
                seat_id=actor_id,
                causal_parent_ids=[report["dispatch_event_id"]]
                if report.get("dispatch_event_id")
                else [],
            )
            report["delivery_event_id"] = delivered["id"]
            events.append(delivered)
            lifetime = self.db.worldline_lifetime(run_id, actor_id)
            if lifetime is None:
                raise CrisisRunError("resolution report recipient life state is missing")
            knowledge = list(lifetime["knowledge"])
            knowledge.append(
                {
                    "kind": "resolution",
                    "event_id": delivered["id"],
                    "resolution_event_id": report["resolution_event_id"],
                    "resolution_kind": report["resolution_kind"],
                    "content": report["content"],
                    "obtained_tick": tick,
                }
            )
            knowledge_by_actor[actor_id] = knowledge
        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for event in events:
            self._queue_wake(
                run_id,
                str(event["seat_id"]),
                CrisisWakeType.RESOLUTION_RESULT,
                tick,
                trigger_event_id=event["id"],
            )

    def _human_resolution_attention_pending(self, run_id: str) -> bool:
        run = self.db.worldline(run_id)
        if run is None:
            return False
        actor_id = self._human_actor_id(run_id)
        if actor_id is None:
            return False
        tick = int(run["current_tick"])
        if self.human_decision_state(run_id, tick)["state"] != "NONE":
            return False
        return any(
            event["event_type"] == "HUMAN_INTERRUPTION_READY"
            and event["seat_id"] == actor_id
            and int(event["tick"]) == tick
            and event["payload"].get("wake_type") == CrisisWakeType.RESOLUTION_RESULT.value
            for event in self.db.worldline_events(run_id)
        )

    def _settlement_outcome(self, projection: dict[str, Any]) -> dict[str, Any]:
        resolution = projection.get("resolution", {})
        result = dict(resolution.get("result", {}))
        kind = str(result.get("kind") or ResolutionKind.DEFERRED.value)
        effected_entity_ids = {
            str(effect["entity_id"])
            for effect in result.get("entity_effects", [])
            if isinstance(effect, dict) and effect.get("entity_id")
        }
        return {
            "settlement_type": "DEFERRED" if kind == ResolutionKind.DEFERRED.value else "RESOLVED",
            "resolution_kind": kind,
            "resolution_variant": str(result.get("variant") or ""),
            "final_stakes": list(result.get("factors", [])),
            "actor_positions": [
                {"actor_id": actor_id, "position": projection["positions"][actor_id]}
                for actor_id in sorted(self.pack.actor_by_id)
            ],
            "critical_assets": [
                {
                    "id": entity_id,
                    "display_name": projection["entities"][entity_id]["display_name"],
                    "state": projection["entities"][entity_id]["state"],
                }
                for entity_id in sorted(effected_entity_ids)
                if entity_id in projection.get("entities", {})
            ],
            "agreements": [
                {
                    "id": agreement["id"],
                    "parties": list(agreement["parties"]),
                    "terms": list(agreement["terms"]),
                    "status": agreement["status"],
                }
                for agreement in projection.get("agreements", [])
            ],
            "major_operations": [
                {
                    "id": operation["id"],
                    "definition_id": operation["definition_id"],
                    "actor_id": operation["actor_id"],
                    "status": operation["status"],
                    "result_state": dict(operation.get("result_state", {})),
                }
                for operation in projection.get("operations", [])
                if operation.get("status") == "COMPLETED"
            ],
            "historical_compatibility": [],
            "material_causal_roots": [str(resolution.get("event_id") or "")],
        }

    def _settle_if_stable(self, run_id: str, run: dict[str, Any]) -> bool:
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        if projection.get("resolution", {}).get("status") != "APPLIED":
            return False
        if any(
            operation.get("status") in {"PLANNED", "IN_PROGRESS"}
            for operation in projection.get("operations", [])
        ):
            return False
        if any(
            investigation.get("status") in {"PLANNED", "IN_PROGRESS"}
            for investigation in projection.get("investigations", [])
        ):
            return False
        if any(movement.get("status") == "in_transit" for movement in projection.get("movements", [])):
            return False
        if any(message.get("status") == "in_transit" for message in projection.get("messages", [])):
            return False
        if any(report.get("status") == "IN_TRANSIT" for report in projection.get("resolution_reports", [])):
            return False
        if any(
            offer.get("status") == OfferStatus.PROPOSED.value
            for offer in projection.get("offers", [])
        ):
            return False
        if any(
            wake["status"] in {"QUEUED", "RUNNING", "STAGED"}
            for wake in self.db.nonterminal_crisis_wakes(run_id)
        ):
            return False
        if self._human_resolution_attention_pending(run_id):
            return False

        outcome = self._settlement_outcome(projection)
        reason = (
            "deferred_resolution"
            if outcome["settlement_type"] == "DEFERRED"
            else "resolution_stabilized"
        )
        tick = int(run["current_tick"])
        settlement = self._event(
            run_id,
            tick,
            "CRISIS_SETTLED",
            {
                "settlement_type": outcome["settlement_type"],
                "reason": reason,
                "outcome": outcome,
                "visibility": sorted(self.pack.actor_by_id),
            },
            causal_parent_ids=[str(projection["resolution"].get("event_id") or "")]
            if projection["resolution"].get("event_id")
            else [],
        )
        projection["settlement"] = {
            "status": "SETTLED",
            "reason": reason,
            "tick": tick,
            "outcome": outcome,
        }
        sealed = self._event(
            run_id,
            tick,
            "RUN_SEALED",
            {"reason": "crisis_settled", "visibility": sorted(self.pack.actor_by_id)},
            causal_parent_ids=[settlement["id"]],
        )
        self.db.commit_worldline_seal(
            run_id,
            sealed,
            reason="crisis_settled",
            outcome=str(projection["resolution"]["result"].get("summary") or "危局已经形成局部结果。"),
            pre_events=[settlement],
            snapshot=projection,
            revoke_agent_bindings=True,
            runtime_phase="CLEANUP_PENDING" if run["runtime_mode"] == "live" else None,
            runtime_error_code="runtime_cleanup_pending" if run["runtime_mode"] == "live" else "",
            cancel_queued_wakes=True,
            crisis_phase="SETTLED",
            outcome_json=json.dumps(outcome, ensure_ascii=False, sort_keys=True),
            settlement_reason=reason,
        )
        return True

    def _settle_at_safety_horizon(self, run_id: str, run: dict[str, Any]) -> bool:
        """Produce a bounded Deferred outcome when the internal harness is exhausted."""

        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        tick = self.pack.crisis.simulation_boundary.maximum_tick
        projection["tick"] = tick
        horizon = self._event(
            run_id,
            tick,
            "SAFETY_HORIZON_REACHED",
            {
                "maximum_tick": tick,
                "visibility": sorted(self.pack.actor_by_id),
            },
            causal_parent_ids=[self.db.worldline_events(run_id)[-1]["id"]]
            if self.db.worldline_events(run_id)
            else [],
        )
        result = {
            "contract_id": str(run["resolution_contract_id"]),
            "contract_version": int(run["resolution_contract_version"]),
            "kind": ResolutionKind.DEFERRED.value,
            "variant": "SAFETY_HORIZON",
            "ambiguity_used": False,
            "summary": "危局尚未形成足以可靠裁定的局部结果，模拟在安全上限处以延期状态封存。",
            "immediate_actor_ids": [],
            "factors": ["内部模拟安全上限已经到达。"],
            "entity_effects": [],
            "agreement_effects": [],
        }
        projection["resolution"] = {
            "status": "SAFETY_HORIZON",
            "event_id": horizon["id"],
            "applied_tick": tick,
            "result": result,
        }
        outcome = self._settlement_outcome(projection)
        outcome["settlement_type"] = "SAFETY_HORIZON"
        projection["settlement"] = {
            "status": "SETTLED",
            "reason": "safety_horizon",
            "tick": tick,
            "outcome": outcome,
        }
        settlement = self._event(
            run_id,
            tick,
            "CRISIS_SETTLED",
            {
                "settlement_type": "SAFETY_HORIZON",
                "reason": "safety_horizon",
                "outcome": outcome,
                "visibility": sorted(self.pack.actor_by_id),
            },
            causal_parent_ids=[horizon["id"]],
        )
        sealed = self._event(
            run_id,
            tick,
            "RUN_SEALED",
            {"reason": "safety_horizon", "visibility": sorted(self.pack.actor_by_id)},
            causal_parent_ids=[settlement["id"]],
        )
        self.db.commit_worldline_seal(
            run_id,
            sealed,
            reason="safety_horizon",
            outcome=result["summary"],
            pre_events=[horizon, settlement],
            snapshot=projection,
            revoke_agent_bindings=True,
            runtime_phase="CLEANUP_PENDING" if run["runtime_mode"] == "live" else None,
            runtime_error_code="runtime_cleanup_pending" if run["runtime_mode"] == "live" else "",
            cancel_queued_wakes=True,
            crisis_phase="SETTLED",
            outcome_json=json.dumps(outcome, ensure_ascii=False, sort_keys=True),
            settlement_reason="safety_horizon",
            current_tick=tick,
        )
        return True

    def advance_one(self, run_id: str, *, allow_runtime_bootstrap: bool = False) -> bool:
        run = self._activate_run_pack(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run is not active")
        if run["status"] == "SEALED":
            return False
        if run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        if run["runtime_mode"] == "live" and run.get("runtime_phase") != "READY":
            if not (
                allow_runtime_bootstrap
                and run.get("runtime_phase") in {"BOOTSTRAPPING", "RECONCILING"}
            ):
                raise CrisisRunConflict(
                    "这一局正在准备或恢复，暂不能继续推进。",
                    code="runtime_not_ready",
                    state=str(run.get("runtime_phase") or "FAILED"),
                )
        if run.get("crisis_phase") == "RESOLUTION_PENDING":
            human_actor_id = self._human_actor_id(run_id)
            if human_actor_id is not None:
                if self._queued_human_resolution_gate(run_id, human_actor_id):
                    pass
                elif self._human_attention(run_id) is not None:
                    return False
                elif self.human_decision_state(run_id, int(run["current_tick"]))["state"] == "NONE":
                    return False
                else:
                    return self._apply_resolution(run_id, run)
            else:
                return self._apply_resolution(run_id, run)
        next_tick = self._next_tick(run_id)
        if next_tick is None:
            return False
        if next_tick >= self.pack.crisis.simulation_boundary.maximum_tick:
            return self._settle_at_safety_horizon(run_id, run)
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        if self._operations_due(projection, next_tick):
            self._commit_operations(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._investigations_due(projection, next_tick):
            self._commit_investigations(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._offers_due(projection, next_tick):
            self._expire_offers(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._pressures_due(projection, next_tick):
            self._commit_pressures(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._movements_due(projection, next_tick):
            self._commit_movements(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._deliveries_due(projection, next_tick):
            self._commit_deliveries(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        if self._resolution_reports_due(projection, next_tick):
            self._commit_resolution_reports(run_id, next_tick, projection)
            self._advance_crisis_lifecycle(run_id)
            return True
        wakes = self.db.crisis_wakes(run_id, status="QUEUED", tick=next_tick)
        if not wakes:
            return False
        controllers = self._controller_map(run_id)
        human_wakes = [wake for wake in wakes if controllers[wake["actor_id"]] == "HUMAN"]
        if human_wakes:
            self._commit_human_interruptions(run_id, next_tick, projection, human_wakes)
            return True
        self._run_wake_moment(run_id, next_tick, projection, wakes)
        self._advance_crisis_lifecycle(run_id)
        return True

    def _commit_human_interruptions(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wakes: list[dict[str, Any]],
    ) -> None:
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for actor_id in sorted({wake["actor_id"] for wake in wakes}):
            lifetime = self.db.worldline_lifetime(run_id, actor_id)
            if lifetime is None:
                raise CrisisRunError("Human life state is missing")
            revisits = list(lifetime["revisits"])
            due_revisits = self._mark_revisits_due(revisits, tick)
            for revisit in due_revisits:
                due_event = self._event(
                    run_id,
                    tick,
                    "REVISIT_DUE",
                    {"revisit_id": revisit["id"], "visibility": [actor_id]},
                    seat_id=actor_id,
                    causal_parent_ids=[revisit["event_id"]]
                    if revisit.get("event_id")
                    else [],
                )
                revisit["due_event_id"] = due_event["id"]
                events.append(due_event)
            perspective = self._perspective_from(
                run_id,
                actor_id,
                projection,
                revisits=revisits,
            )
            updates.append(
                {
                    "seat": actor_id,
                    "revisits_json": json.dumps(
                        revisits, ensure_ascii=False, sort_keys=True
                    ),
                    "last_perspective_json": json.dumps(
                        perspective, ensure_ascii=False, sort_keys=True
                    ),
                }
            )
        for wake in wakes:
            events.append(
                self._event(
                    run_id,
                    tick,
                    "HUMAN_INTERRUPTION_READY",
                    {
                        "wake_type": wake["wake_type"],
                        "trigger_event_id": wake["trigger_event_id"],
                        "visibility": [wake["actor_id"]],
                    },
                    seat_id=wake["actor_id"],
                )
            )
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for wake in wakes:
            self.db.update_crisis_wake(
                wake["id"],
                status="COMPLETED",
                result={"summary": "等待 Human 决定或选择沉默。"},
            )

    def _next_tick(self, run_id: str) -> int | None:
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            return None
        candidates = [
            int(wake["tick"])
            for wake in self.db.crisis_wakes(run_id, status="QUEUED")
        ]
        candidates.extend(
            int(message["arrival_tick"])
            for message in snapshot["projection"].get("messages", [])
            if message["status"] == "in_transit"
        )
        candidates.extend(
            int(operation["expected_complete_tick"])
            for operation in snapshot["projection"].get("operations", [])
            if operation["status"] == "IN_PROGRESS"
        )
        candidates.extend(
            int(investigation["expected_result_tick"])
            for investigation in snapshot["projection"].get("investigations", [])
            if investigation["status"] == "IN_PROGRESS"
        )
        candidates.extend(
            int(offer["expires_tick"])
            for offer in snapshot["projection"].get("offers", [])
            if offer.get("status") == OfferStatus.PROPOSED.value
            and offer.get("expires_tick") is not None
        )
        candidates.extend(
            int(pressure["trigger_tick"])
            for pressure in snapshot["projection"].get("pressures", [])
            if pressure.get("status") == PressureStatus.PENDING.value
        )
        candidates.extend(
            int(movement["arrival_tick"])
            for movement in snapshot["projection"].get("movements", [])
            if movement["status"] == "in_transit"
        )
        candidates.extend(
            int(report["expected_tick"])
            for report in snapshot["projection"].get("resolution_reports", [])
            if report.get("status") == "IN_TRANSIT"
        )
        return min(candidates) if candidates else None

    @staticmethod
    def _operations_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            operation
            for operation in projection.get("operations", [])
            if operation["status"] == "IN_PROGRESS"
            and int(operation["expected_complete_tick"]) == tick
        ]

    def _operation_visible_actor_ids(self, operation: dict[str, Any]) -> list[str]:
        definition = self.pack.operation_by_id[str(operation["definition_id"])]
        if definition.visibility.value == "PUBLIC":
            return sorted(self.pack.actor_by_id)
        return [str(operation["actor_id"])]

    def _apply_operation_state_effects(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        operation: dict[str, Any],
        effects: list[Any],
        *,
        phase: str,
        causal_parent_id: str,
        visible_actor_ids: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        events: list[dict[str, Any]] = []
        result_state: dict[str, str] = {}
        target_map = dict(operation["target_map"])
        for effect in effects:
            entity_id = target_map.get(effect.subject, effect.subject)
            entity = projection["entities"][entity_id]
            previous_state = str(entity["state"])
            entity["state"] = effect.state
            result_state[entity_id] = effect.state
            if previous_state == effect.state:
                continue
            events.append(
                self._event(
                    run_id,
                    tick,
                    "ENTITY_STATE_CHANGED",
                    {
                        "operation_id": operation["id"],
                        "entity_id": entity_id,
                        "before": previous_state,
                        "after": effect.state,
                        "phase": phase,
                        "visibility": visible_actor_ids,
                    },
                    seat_id=operation["actor_id"],
                    causal_parent_ids=[causal_parent_id],
                )
            )
        return events, result_state

    def _commit_operations(self, run_id: str, tick: int, projection: dict[str, Any]) -> None:
        due = self._operations_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        knowledge_by_actor: dict[str, list[Any]] = {}
        queued: set[tuple[str, str]] = set()
        agreement_changes: set[tuple[str, str]] = set()
        for operation in due:
            definition = self.pack.operation_by_id[str(operation["definition_id"])]
            visible_actor_ids = self._operation_visible_actor_ids(operation)
            operation["status"] = "COMPLETED"
            completed = self._event(
                run_id,
                tick,
                "OPERATION_COMPLETED",
                {
                    "operation": operation,
                    "visibility": visible_actor_ids,
                },
                seat_id=operation["actor_id"],
                causal_parent_ids=[operation["start_event_id"]]
                if operation.get("start_event_id")
                else [],
            )
            operation["completion_event_id"] = completed["id"]
            events.append(completed)
            state_events, result_state = self._apply_operation_state_effects(
                run_id,
                tick,
                projection,
                operation,
                definition.completion_effects,
                phase="completion",
                causal_parent_id=completed["id"],
                visible_actor_ids=visible_actor_ids,
            )
            operation["result_state"] = result_state
            events.extend(state_events)
            observation = f"{definition.display_name}已经完成。"
            if definition.kind.value == "MOVEMENT":
                movement = next(
                    (
                        item
                        for item in projection.get("movements", [])
                        if item.get("operation_id") == operation["id"]
                        and item.get("status") == "in_transit"
                    ),
                    None,
                )
                if movement is None:
                    raise CrisisRunError("movement Operation lost its in-transit projection")
                movement["status"] = "arrived"
                projection["positions"][operation["actor_id"]] = movement["to"]
                arrived = self._event(
                    run_id,
                    tick,
                    "MOVEMENT_ARRIVED",
                    movement,
                    seat_id=operation["actor_id"],
                    causal_parent_ids=[completed["id"]],
                )
                movement["arrival_event_id"] = arrived["id"]
                events.append(arrived)
                observation = (
                    f"{definition.display_name}已经完成，"
                    f"已抵达{self.pack.location_by_id[movement['to']].display_name}。"
                )
            agreement_events, agreement_triggers = self._operation_agreement_outcomes(
                run_id,
                tick,
                projection,
                operation,
                definition,
                visible_actor_ids=visible_actor_ids,
                causal_parent_id=completed["id"],
            )
            events.extend(agreement_events)
            agreement_changes.update(agreement_triggers)
            for actor_id in visible_actor_ids:
                lifetime = self.db.worldline_lifetime(run_id, actor_id)
                if lifetime is None:
                    raise CrisisRunError("operation observer life state is missing")
                knowledge = knowledge_by_actor.setdefault(actor_id, list(lifetime["knowledge"]))
                knowledge.append(
                    {
                        "kind": "observation",
                        "event_id": completed["id"],
                        "observation": observation,
                        "received_tick": tick,
                        "provenance": "branch_derived",
                    }
                )
                queued.add((actor_id, completed["id"]))
        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for actor_id, trigger_event_id in sorted(queued):
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.OPERATION_RESULT,
                tick,
                trigger_event_id=trigger_event_id,
            )
        for actor_id, trigger_event_id in sorted(agreement_changes):
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.AGREEMENT_CHANGE,
                tick,
                trigger_event_id=trigger_event_id,
            )

    def _operation_agreement_outcomes(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        operation: dict[str, Any],
        definition: Any,
        *,
        visible_actor_ids: list[str],
        causal_parent_id: str,
    ) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
        events: list[dict[str, Any]] = []
        queued: set[tuple[str, str]] = set()
        agreements_by_id = {
            str(agreement["id"]): agreement
            for agreement in projection.get("agreements", [])
        }
        for event_type, status, requirements in (
            ("AGREEMENT_FULFILLED", AgreementStatus.FULFILLED, definition.agreement_fulfillments),
            ("AGREEMENT_BREACHED", AgreementStatus.BREACHED, definition.agreement_breaches),
        ):
            for requirement in requirements:
                for agreement_id in self.pack.active_agreement_ids(projection, requirement):
                    agreement = agreements_by_id[agreement_id]
                    agreement["status"] = status.value
                    visible_agreement_actor_ids = sorted(
                        set(str(party_id) for party_id in agreement["parties"])
                        .intersection(visible_actor_ids)
                    )
                    event = self._event(
                        run_id,
                        tick,
                        event_type,
                        {
                            "agreement": agreement,
                            "operation_id": operation["id"],
                            "visibility": visible_agreement_actor_ids,
                        },
                        seat_id=operation["actor_id"],
                        causal_parent_ids=[causal_parent_id],
                    )
                    agreement[f"{status.value.lower()}_event_id"] = event["id"]
                    events.append(event)
                    queued.update(
                        (actor_id, event["id"])
                        for actor_id in visible_agreement_actor_ids
                    )
        return events, queued

    @staticmethod
    def _investigations_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            investigation
            for investigation in projection.get("investigations", [])
            if investigation["status"] == "IN_PROGRESS"
            and int(investigation["expected_result_tick"]) == tick
        ]

    def _investigation_visible_actor_ids(self, investigation: dict[str, Any]) -> list[str]:
        definition = self.pack.investigation_by_id[str(investigation["definition_id"])]
        if definition.visibility.value == "PUBLIC":
            return sorted(self.pack.actor_by_id)
        return [str(investigation["actor_id"])]

    def _commit_investigations(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
    ) -> None:
        due = self._investigations_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        knowledge_by_actor: dict[str, list[Any]] = {}
        queued: set[tuple[str, str]] = set()
        for investigation in due:
            definition = self.pack.investigation_by_id[str(investigation["definition_id"])]
            visible_actor_ids = self._investigation_visible_actor_ids(investigation)
            investigation["status"] = "COMPLETED"
            completed = self._event(
                run_id,
                tick,
                "INVESTIGATION_COMPLETED",
                {"investigation": investigation, "visibility": visible_actor_ids},
                seat_id=investigation["actor_id"],
                causal_parent_ids=[investigation["start_event_id"]]
                if investigation.get("start_event_id")
                else [],
            )
            investigation["completion_event_id"] = completed["id"]
            events.append(completed)
            observation = {
                "id": f"observation-{uuid.uuid4().hex[:16]}",
                "investigation_id": investigation["id"],
                "content": definition.observation.content,
                "source": definition.observation.source,
                "source_ids": list(definition.observation.source_ids),
                "reliability": definition.observation.reliability.value,
                "obtained_tick": tick,
                "related_assertions": list(definition.observation.related_assertion_ids),
            }
            investigation["observation"] = observation
            observed = self._event(
                run_id,
                tick,
                "OBSERVATION_OBTAINED",
                {"observation": observation, "visibility": visible_actor_ids},
                seat_id=investigation["actor_id"],
                causal_parent_ids=[completed["id"]],
            )
            observation["event_id"] = observed["id"]
            events.append(observed)
            for actor_id in visible_actor_ids:
                lifetime = self.db.worldline_lifetime(run_id, actor_id)
                if lifetime is None:
                    raise CrisisRunError("investigation observer life state is missing")
                knowledge = knowledge_by_actor.setdefault(actor_id, list(lifetime["knowledge"]))
                knowledge.append(
                    {
                        "kind": "observation",
                        "event_id": observed["id"],
                        "observation": observation["content"],
                        "source": observation["source"],
                        "source_ids": observation["source_ids"],
                        "reliability": observation["reliability"],
                        "obtained_tick": tick,
                        "related_assertions": observation["related_assertions"],
                        "investigation_id": investigation["id"],
                    }
                )
                queued.add((actor_id, observed["id"]))
        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for actor_id, trigger_event_id in sorted(queued):
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.INVESTIGATION_RESULT,
                tick,
                trigger_event_id=trigger_event_id,
            )

    @staticmethod
    def _offers_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            offer
            for offer in projection.get("offers", [])
            if offer.get("status") == OfferStatus.PROPOSED.value
            and offer.get("expires_tick") is not None
            and int(offer["expires_tick"]) == tick
        ]

    @staticmethod
    def _offer_visible_actor_ids(offer: dict[str, Any]) -> list[str]:
        return sorted({str(offer["issuer"]), str(offer["recipient"])})

    def _expire_offers(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
    ) -> None:
        due = self._offers_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        queued: set[tuple[str, str]] = set()
        for offer in due:
            visible_actor_ids = self._offer_visible_actor_ids(offer)
            offer["status"] = OfferStatus.EXPIRED.value
            expired = self._event(
                run_id,
                tick,
                "OFFER_EXPIRED",
                {"offer": offer, "visibility": visible_actor_ids},
                seat_id=offer["issuer"],
                causal_parent_ids=[offer["proposal_event_id"]]
                if offer.get("proposal_event_id")
                else [],
            )
            offer["expiry_event_id"] = expired["id"]
            events.append(expired)
            queued.update((actor_id, expired["id"]) for actor_id in visible_actor_ids)
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            snapshot=projection,
        )
        for actor_id, trigger_event_id in sorted(queued):
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.OFFER_CHANGE,
                tick,
                trigger_event_id=trigger_event_id,
            )

    @staticmethod
    def _pressures_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            pressure
            for pressure in projection.get("pressures", [])
            if pressure.get("status") == PressureStatus.PENDING.value
            and int(pressure["trigger_tick"]) == tick
        ]

    def _pressure_visible_actor_ids(self, pressure: dict[str, Any]) -> list[str]:
        if pressure.get("visibility") == "PUBLIC":
            return sorted(self.pack.actor_by_id)
        return sorted(str(actor_id) for actor_id in pressure.get("visible_actor_ids", []))

    @staticmethod
    def _pressure_preconditions_met(
        pressure: dict[str, Any], projection: dict[str, Any]
    ) -> bool:
        return all(
            str(projection.get("entities", {}).get(condition["subject"], {}).get("state", ""))
            in condition["states"]
            for condition in pressure.get("preconditions", [])
        )

    def _commit_pressures(self, run_id: str, tick: int, projection: dict[str, Any]) -> None:
        due = self._pressures_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        knowledge_by_actor: dict[str, list[Any]] = {}
        queued: set[tuple[str, str]] = set()
        for pressure in due:
            scheduled_event_id = str(pressure.get("scheduled_event_id") or "")
            parent_ids = [scheduled_event_id] if scheduled_event_id else []
            if not self._pressure_preconditions_met(pressure, projection):
                pressure["status"] = PressureStatus.SKIPPED.value
                skipped = self._event(
                    run_id,
                    tick,
                    "PRESSURE_SKIPPED",
                    {"pressure": pressure, "visibility": []},
                    provenance=str(pressure["provenance"]),
                    causal_parent_ids=parent_ids,
                )
                pressure["skip_event_id"] = skipped["id"]
                events.append(skipped)
                continue
            pressure["status"] = PressureStatus.APPLIED.value
            visible_actor_ids = self._pressure_visible_actor_ids(pressure)
            applied = self._event(
                run_id,
                tick,
                "PRESSURE_APPLIED",
                {"pressure": pressure, "visibility": visible_actor_ids},
                provenance=str(pressure["provenance"]),
                causal_parent_ids=parent_ids,
            )
            pressure["applied_event_id"] = applied["id"]
            events.append(applied)
            for effect in pressure["effects"]:
                entity = projection["entities"][effect["subject"]]
                previous_state = str(entity["state"])
                entity["state"] = effect["state"]
                if previous_state == effect["state"]:
                    continue
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "ENTITY_STATE_CHANGED",
                        {
                            "pressure_id": pressure["id"],
                            "entity_id": effect["subject"],
                            "before": previous_state,
                            "after": effect["state"],
                            "phase": "pressure",
                            "visibility": visible_actor_ids,
                        },
                        provenance=str(pressure["provenance"]),
                        causal_parent_ids=[applied["id"]],
                    )
                )
            for actor_id in visible_actor_ids:
                lifetime = self.db.worldline_lifetime(run_id, actor_id)
                if lifetime is None:
                    raise CrisisRunError("pressure observer life state is missing")
                knowledge = knowledge_by_actor.setdefault(actor_id, list(lifetime["knowledge"]))
                knowledge.append(
                    {
                        "kind": "pressure",
                        "event_id": applied["id"],
                        "pressure_id": pressure["id"],
                        "title": pressure["title"],
                        "content": pressure["description"],
                        "obtained_tick": tick,
                        "provenance": pressure["provenance"],
                        "assertion_ids": list(pressure["assertion_ids"]),
                    }
                )
                queued.add((actor_id, applied["id"]))
        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for actor_id, trigger_event_id in sorted(queued):
            self._queue_wake(
                run_id,
                actor_id,
                CrisisWakeType.PRESSURE,
                tick,
                trigger_event_id=trigger_event_id,
            )

    @staticmethod
    def _movements_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            movement
            for movement in projection.get("movements", [])
            if movement["status"] == "in_transit" and int(movement["arrival_tick"]) == tick
        ]

    def _commit_movements(self, run_id: str, tick: int, projection: dict[str, Any]) -> None:
        due = self._movements_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        queued: list[tuple[str, str]] = []
        for movement in due:
            actor_id = movement["actor_id"]
            movement["status"] = "arrived"
            projection["positions"][actor_id] = movement["to"]
            event = self._event(
                run_id,
                tick,
                "MOVEMENT_ARRIVED",
                movement,
                seat_id=actor_id,
                causal_parent_ids=[movement["start_event_id"]]
                if movement.get("start_event_id")
                else [],
            )
            events.append(event)
            lifetime = self.db.worldline_lifetime(run_id, actor_id)
            if lifetime is None:
                raise CrisisRunError("moving actor life state is missing")
            knowledge = list(lifetime["knowledge"])
            knowledge.append(
                {
                    "kind": "observation",
                    "event_id": event["id"],
                    "observation": f"已到达{self.pack.location_by_id[movement['to']].display_name}",
                    "received_tick": tick,
                }
            )
            updates.append(
                {
                    "seat": actor_id,
                    "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                    "last_perspective_json": json.dumps(
                        self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
            queued.append((actor_id, event["id"]))
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for actor_id, trigger_event_id in queued:
            if self._controller_map(run_id)[actor_id] == "AGENT":
                self._queue_wake(
                    run_id,
                    actor_id,
                    CrisisWakeType.OBSERVATION,
                    tick,
                    trigger_event_id=trigger_event_id,
                )

    @staticmethod
    def _deliveries_due(projection: dict[str, Any], tick: int) -> list[dict[str, Any]]:
        return [
            message
            for message in projection.get("messages", [])
            if message["status"] == "in_transit" and int(message["arrival_tick"]) == tick
        ]

    def _commit_deliveries(self, run_id: str, tick: int, projection: dict[str, Any]) -> None:
        due = self._deliveries_due(projection, tick)
        projection["tick"] = tick
        events: list[dict[str, Any]] = []
        knowledge_by_actor: dict[str, list[Any]] = {}
        queued: list[tuple[str, str]] = []
        for message in due:
            message["status"] = "delivered"
            delivery = self._event(
                run_id,
                tick,
                "MESSAGE_DELIVERED",
                message,
                seat_id=message["recipient"],
                causal_parent_ids=[message["dispatch_event_id"]]
                if message.get("dispatch_event_id")
                else [],
            )
            events.append(delivery)
            lifetime = self.db.worldline_lifetime(run_id, message["recipient"])
            if lifetime is None:
                raise CrisisRunError("message recipient life state is missing")
            knowledge = knowledge_by_actor.setdefault(
                message["recipient"], list(lifetime["knowledge"])
            )
            knowledge.append(
                {
                    "kind": "message",
                    "message_id": message["id"],
                    "sender": message["sender"],
                    "content": message["content"],
                    "received_tick": tick,
                    "assertion_ids": list(message.get("assertion_ids", [])),
                    "provenance": "scenario_assumption"
                    if message.get("source") == "checkpoint"
                    else "branch_derived",
                    "delivery_event_id": delivery["id"],
                }
            )
            queued.append((message["recipient"], delivery["id"]))
        updates = [
            {
                "seat": actor_id,
                "knowledge_json": json.dumps(knowledge, ensure_ascii=False, sort_keys=True),
                "last_perspective_json": json.dumps(
                    self._perspective_from(run_id, actor_id, projection, knowledge=knowledge),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for actor_id, knowledge in knowledge_by_actor.items()
        ]
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=updates,
            snapshot=projection,
        )
        for recipient, trigger_event_id in queued:
            self._queue_wake(
                run_id,
                recipient,
                CrisisWakeType.MESSAGE,
                tick,
                trigger_event_id=trigger_event_id,
            )

    def _run_wake_moment(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wakes: list[dict[str, Any]],
    ) -> None:
        projection["tick"] = tick
        frozen: dict[str, dict[str, Any]] = {}
        frozen_revisits: dict[str, list[dict[str, Any]]] = {}
        actors_with_due_revisits = {
            str(wake["actor_id"])
            for wake in wakes
            if wake["wake_type"] == CrisisWakeType.REVISIT_DUE.value
        }
        for actor_id in {str(wake["actor_id"]) for wake in wakes}:
            lifetime = self.db.worldline_lifetime(run_id, actor_id)
            if lifetime is None:
                raise CrisisRunError("actor life state is missing")
            revisits = list(lifetime["revisits"])
            if actor_id in actors_with_due_revisits:
                self._mark_revisits_due(revisits, tick)
            frozen_revisits[actor_id] = revisits
        for wake in wakes:
            perspective = self._perspective_from(
                run_id,
                wake["actor_id"],
                projection,
                revisits=frozen_revisits[str(wake["actor_id"])],
            )
            perspective["trigger"] = self._trigger_for(wake)
            frozen[wake["id"]] = perspective

        groups: dict[str, list[dict[str, Any]]] = {}
        for wake in wakes:
            groups.setdefault(wake["actor_id"], []).append(wake)
        results: dict[str, ActorTurnResult] = {}
        failures: list[tuple[str, Exception]] = []
        with ThreadPoolExecutor(max_workers=len(groups)) as executor:
            futures = {
                executor.submit(
                    self._execute_actor_wakes,
                    actor_wakes,
                    frozen,
                ): actor_id
                for actor_id, actor_wakes in groups.items()
            }
            for future in as_completed(futures):
                actor_id = futures[future]
                try:
                    results.update(future.result())
                except Exception as exc:
                    failures.append((actor_id, exc))
        if failures:
            self._rollback_staged_reflections(run_id, wakes, results)
            actor_id, exc = failures[0]
            raise CrisisRunError(f"actor wake failed for {actor_id}") from exc

        events: list[dict[str, Any]] = []
        actor_states: dict[str, dict[str, Any]] = {}
        actor_lifetimes: dict[str, dict[str, Any]] = {}
        queued_wakes: list[dict[str, Any]] = []
        commit_time_refusals: list[dict[str, Any]] = []
        memory_audits: list[dict[str, Any]] = []
        for wake in sorted(wakes, key=lambda item: (item["actor_id"], item["id"])):
            lifetime = self.db.worldline_lifetime(run_id, wake["actor_id"])
            if lifetime is None:
                raise CrisisRunError("actor life state is missing")
            actor_lifetimes[wake["actor_id"]] = lifetime
            state = actor_states.setdefault(
                wake["actor_id"],
                {
                    "plan": list(lifetime["plan"]),
                    "beliefs": dict(lifetime["beliefs"]),
                    "revisits": list(lifetime["revisits"]),
                    "memory_text": str(lifetime["memory_text"]),
                    "memory_hash": str(lifetime["memory_hash"]),
                    "wake_count": int(lifetime["wake_count"]),
                },
            )
            state["wake_count"] += 1
            turn_result = results[wake["id"]]
            if wake["wake_type"] == CrisisWakeType.REFLECTION.value:
                if turn_result.memory_before_hash and (
                    turn_result.memory_before_hash != state["memory_hash"]
                ):
                    raise CrisisRunError("Reflection Memory lineage does not match Life State")
                if turn_result.memory_changed:
                    previous_hash = state["memory_hash"]
                    state["memory_text"] = turn_result.memory_text
                    state["memory_hash"] = turn_result.memory_hash
                    reflected = self._event(
                        run_id,
                        tick,
                        "MEMORY_REFLECTED",
                        {
                            "wake_id": wake["id"],
                            "memory_hash": turn_result.memory_hash,
                            "visibility": [wake["actor_id"]],
                        },
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[wake["trigger_event_id"]]
                        if wake["trigger_event_id"]
                        else [],
                    )
                    events.append(reflected)
                    memory_audits.append(
                        {
                            "seat": f"{run_id}:{wake['actor_id']}",
                            "profile_name": lifetime["profile_name"],
                            "memory_before_text": turn_result.memory_before_text,
                            "memory_before_existed": turn_result.memory_before_existed,
                            "memory_text": turn_result.memory_text,
                            "previous_hash": previous_hash,
                            "memory_hash": turn_result.memory_hash,
                            "wake_id": wake["id"],
                        }
                    )
            revisit_due_events: dict[str, str] = {}
            if wake["wake_type"] == CrisisWakeType.REVISIT_DUE.value:
                for revisit in self._mark_revisits_due(state["revisits"], tick):
                    due_event = self._event(
                        run_id,
                        tick,
                        "REVISIT_DUE",
                        {"wake_id": wake["id"], "revisit_id": revisit["id"]},
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[revisit["event_id"]]
                        if revisit.get("event_id")
                        else [],
                    )
                    events.append(due_event)
                    revisit["due_event_id"] = due_event["id"]
                    revisit_due_events[revisit["id"]] = due_event["id"]
            operations = self.db.crisis_wake_operations(wake["id"])
            accepted = sorted(
                (operation for operation in operations if operation["status"] == "PROPOSED"),
                key=lambda operation: (
                    operation["tool_name"] != "update_plan",
                    int(operation["sequence"]),
                ),
            )
            rejected = [operation for operation in operations if operation["status"] == "REJECTED"]
            causal_parent_id = str(wake["trigger_event_id"] or "")
            for operation in rejected:
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "ACTOR_TOOL_REJECTED",
                        {
                            "wake_id": wake["id"],
                            "tool": operation["tool_name"],
                            "code": operation["result"].get("code", "rejected"),
                            "visibility": [wake["actor_id"]],
                        },
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                    )
                )
            if not accepted:
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "WAKE_NOOP",
                        {"wake_id": wake["id"], "wake_type": wake["wake_type"]},
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                    )
                )
            for operation in accepted:
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "ACTOR_TOOL_REQUESTED",
                        {
                            "wake_id": wake["id"],
                            "tool": operation["tool_name"],
                            "visibility": [wake["actor_id"]],
                        },
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                    )
                )
                causal_parent_id = self._apply_operation(
                    run_id,
                    tick,
                    projection,
                    wake,
                    operation,
                    state,
                    events,
                    queued_wakes,
                    commit_refusals=commit_time_refusals,
                    causal_parent_id=causal_parent_id,
                )
            for revisit in state["revisits"]:
                if revisit["id"] not in revisit_due_events:
                    continue
                revisit["status"] = "FULFILLED"
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "REVISIT_FULFILLED",
                        {"wake_id": wake["id"], "revisit_id": revisit["id"]},
                        seat_id=wake["actor_id"],
                        causal_parent_ids=[revisit_due_events[revisit["id"]]],
                    )
                )
            fingerprint = stable_hash(
                {
                    "summary": results[wake["id"]].summary,
                    "operations": [
                        {"tool": item["tool_name"], "payload": item["payload"]}
                        for item in operations
                    ],
                }
            )
            previous_count = self._previous_repetition_count(run_id, wake["actor_id"], fingerprint)
            events.append(
                self._event(
                    run_id,
                    tick,
                    "ACTOR_WAKE_COMPLETED",
                    {
                        "wake_id": wake["id"],
                        "wake_type": wake["wake_type"],
                        "source": self.actor_driver.source,
                        "session_id": self.db.crisis_wake(wake["id"])["hermes_session_id"],
                        "operation_count": len(operations),
                        "decision_fingerprint": fingerprint,
                        "repetition_count": previous_count + 1,
                    },
                    seat_id=wake["actor_id"],
                    causal_parent_ids=[wake["trigger_event_id"]]
                    if wake["trigger_event_id"]
                    else [],
                )
            )
        lifetime_updates: list[dict[str, Any]] = []
        for actor_id, state in actor_states.items():
            lifetime = actor_lifetimes[actor_id]
            perspective = self._perspective_from(
                run_id,
                actor_id,
                projection,
                beliefs=state["beliefs"],
                plan=state["plan"],
                revisits=state["revisits"],
            )
            lifetime_updates.append(
                {
                    "seat": actor_id,
                    "belief_json": json.dumps(state["beliefs"], ensure_ascii=False, sort_keys=True),
                    "plan_json": json.dumps(state["plan"], ensure_ascii=False, sort_keys=True),
                    "revisits_json": json.dumps(
                        state["revisits"], ensure_ascii=False, sort_keys=True
                    ),
                    "last_perspective_json": json.dumps(
                        perspective, ensure_ascii=False, sort_keys=True
                    ),
                    "memory_text": state["memory_text"],
                    "memory_hash": state["memory_hash"],
                    "wake_count": state["wake_count"],
                }
            )
        try:
            self.db.commit_worldline_moment(
                run_id,
                events,
                current_tick=tick,
                lifetime_updates=lifetime_updates,
                memory_versions=[
                    {
                        "seat": audit["seat"],
                        "memory_text": audit["memory_text"],
                        "previous_hash": audit["previous_hash"],
                        "memory_hash": audit["memory_hash"],
                        "source_record_ids": [audit["wake_id"]],
                        "mutation_kind": "reflection",
                    }
                    for audit in memory_audits
                ],
                snapshot=projection,
            )
        except Exception:
            if self.actor_driver.source == "hermes":
                from .hermes import restore_profile_memory

                for audit in reversed(memory_audits):
                    restore_profile_memory(
                        self.config,
                        audit["profile_name"],
                        audit["memory_before_existed"],
                        audit["memory_before_text"],
                    )
            raise
        for refusal in commit_time_refusals:
            self.db.update_crisis_wake_operation_status(
                refusal["operation_id"],
                "REJECTED",
                result=refusal["result"],
            )
        for wake in wakes:
            result = results[wake["id"]]
            self.db.update_crisis_wake(
                wake["id"], status="COMPLETED", result={"summary": result.summary}
            )
            for operation in self.db.crisis_wake_operations(wake["id"]):
                if operation["status"] == "PROPOSED":
                    self.db.update_crisis_wake_operation_status(operation["id"], "COMMITTED")
        for item in queued_wakes:
            self._queue_wake(**item)

    def _execute_actor_wakes(
        self,
        wakes: list[dict[str, Any]],
        frozen: dict[str, dict[str, Any]],
    ) -> dict[str, ActorTurnResult]:
        results: dict[str, ActorTurnResult] = {}
        expected_memory_hash = ""
        for wake in sorted(wakes, key=lambda item: item["id"]):
            perspective = frozen[wake["id"]]
            session_id = (
                f"fixture-{wake['id']}-{uuid.uuid4().hex[:8]}"
                if self.actor_driver.source == "fixture"
                else ""
            )
            self.db.update_crisis_wake(
                wake["id"],
                status="RUNNING",
                hermes_session_id=session_id,
                frozen_perspective=perspective,
            )
            active_wake = self.db.crisis_wake(wake["id"])
            if active_wake is None:
                raise CrisisRunError("wake disappeared before execution")
            if expected_memory_hash:
                active_wake["_expected_memory_hash"] = expected_memory_hash
            try:
                world = self.world.fixture_session(wake["id"], wake["actor_id"])
                results[wake["id"]] = self.actor_driver.run_wake(
                    wake["actor_id"], active_wake, perspective, world
                )
                if (
                    self.actor_driver.source == "hermes"
                    and wake["wake_type"] == CrisisWakeType.ORIENT.value
                    and not any(
                        operation["tool_name"] == "update_plan"
                        and operation["status"] in {"PROPOSED", "COMMITTED"}
                        for operation in self.db.crisis_wake_operations(wake["id"])
                    )
                ):
                    raise CrisisRunError(
                        "live ORIENT did not produce a World MCP update_plan operation"
                    )
                if results[wake["id"]].session_id:
                    self.db.update_crisis_wake(
                        wake["id"], hermes_session_id=results[wake["id"]].session_id
                    )
                if results[wake["id"]].memory_hash:
                    expected_memory_hash = results[wake["id"]].memory_hash
                self.db.update_crisis_wake(wake["id"], status="STAGED")
            except Exception as exc:
                self.db.update_crisis_wake(
                    wake["id"], status="FAILED", error={"type": type(exc).__name__}
                )
                self._rollback_staged_reflections(
                    str(wake["worldline_id"]), wakes, results
                )
                raise CrisisRunError(f"actor wake failed for {wake['actor_id']}") from exc
        return results

    def _rollback_staged_reflections(
        self,
        run_id: str,
        wakes: list[dict[str, Any]],
        results: dict[str, ActorTurnResult],
    ) -> None:
        if self.actor_driver.source != "hermes":
            return
        from .hermes import read_profile_memory, restore_profile_memory

        wakes_by_id = {str(wake["id"]): wake for wake in wakes}
        for wake_id in sorted(results, reverse=True):
            result = results[wake_id]
            if not result.memory_changed:
                continue
            wake = wakes_by_id[wake_id]
            lifetime = self.db.worldline_lifetime(run_id, str(wake["actor_id"]))
            if lifetime is None or not lifetime["profile_name"]:
                raise CrisisRunError("cannot compensate a staged Reflection without its Profile")
            profile = str(lifetime["profile_name"])
            restore_profile_memory(
                self.config,
                profile,
                result.memory_before_existed,
                result.memory_before_text,
            )
            if read_profile_memory(self.config, profile)[1] != result.memory_before_hash:
                raise CrisisRunError("staged Reflection Memory compensation failed")

    def _apply_operation(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        state: dict[str, Any],
        events: list[dict[str, Any]],
        queued_wakes: list[dict[str, Any]],
        *,
        commit_refusals: list[dict[str, Any]] | None = None,
        source: str | None = None,
        causal_parent_id: str = "",
    ) -> str:
        actor_id = wake["actor_id"]
        payload = operation["payload"]
        result = operation["result"]
        tool_name = operation["tool_name"]
        if tool_name == "update_plan":
            current_plan = state["plan"][0] if state["plan"] else None
            if self._same_material_plan(current_plan, payload):
                plan_event = self._event(
                    run_id,
                    tick,
                    "PLAN_REAFFIRMED",
                    {
                        "wake_id": wake["id"],
                        "plan": current_plan,
                        "visibility": [actor_id],
                    },
                    seat_id=actor_id,
                    causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                )
            else:
                state["plan"] = [
                    {
                        "version": result["plan_version"],
                        "objective": payload["objective"],
                        "steps": payload["steps"],
                        "rationale": payload["rationale"],
                        "reconsider_when": payload.get("reconsider_when", []),
                        "updated_tick": tick,
                    }
                ]
                plan_event = self._event(
                    run_id,
                    tick,
                    "PLAN_UPDATED",
                    {"wake_id": wake["id"], "plan": state["plan"][0], "visibility": [actor_id]},
                    seat_id=actor_id,
                    causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
                )
            events.append(plan_event)
            for belief in payload.get("belief_updates", []):
                state["beliefs"][belief["subject"]] = {
                    "assessment": belief["assessment"],
                    "confidence": belief["confidence"],
                    "updated_tick": tick,
                    "evidence_event_ids": [wake["trigger_event_id"]]
                    if wake["trigger_event_id"]
                    else [],
                }
                events.append(
                    self._event(
                        run_id,
                        tick,
                        "BELIEF_UPDATED",
                        {
                            "wake_id": wake["id"],
                            "subject": belief["subject"],
                            "visibility": [actor_id],
                        },
                        seat_id=actor_id,
                        causal_parent_ids=[plan_event["id"]],
                    )
                )
            return plan_event["id"]
        elif tool_name == "schedule_revisit":
            revisit = {
                "id": result["revisit_id"],
                "actor_id": actor_id,
                "reason": payload["reason"],
                "created_tick": tick,
                "due_tick": result["due_tick"],
                "status": "PENDING",
            }
            state["revisits"].append(revisit)
            event = self._event(
                run_id,
                tick,
                "REVISIT_SCHEDULED",
                {"wake_id": wake["id"], "revisit": revisit, "visibility": [actor_id]},
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            revisit["event_id"] = event["id"]
            events.append(event)
            queued_wakes.append(
                {
                    "run_id": run_id,
                    "actor_id": actor_id,
                    "wake_type": CrisisWakeType.REVISIT_DUE,
                    "tick": int(result["due_tick"]),
                    "trigger_event_id": event["id"],
                }
            )
            return event["id"]
        elif tool_name == "communicate":
            message = {
                "id": result["message_id"],
                "sender": actor_id,
                "recipient": payload["recipient"],
                "content": payload["content"],
                "dispatch_tick": tick,
                "arrival_tick": result["arrival_tick"],
                "status": "in_transit",
                "source": source or self.actor_driver.source,
                "disputed": False,
                "assertion_ids": [],
            }
            projection["messages"].append(message)
            dispatch = self._event(
                run_id,
                tick,
                "MESSAGE_DISPATCHED",
                message,
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            message["dispatch_event_id"] = dispatch["id"]
            events.append(dispatch)
            return dispatch["id"]
        elif tool_name == "manage_offer":
            return self._manage_offer(
                run_id,
                tick,
                projection,
                wake,
                operation,
                events,
                queued_wakes,
                commit_refusals=commit_refusals,
                causal_parent_id=causal_parent_id,
            )
        elif tool_name == "investigate":
            return self._start_investigation(
                run_id,
                tick,
                projection,
                wake,
                operation,
                events,
                causal_parent_id=causal_parent_id,
            )
        elif tool_name == "operate":
            return self._start_operation(
                run_id,
                tick,
                projection,
                wake,
                operation,
                events,
                causal_parent_id=causal_parent_id,
            )
        return causal_parent_id

    def _manage_offer(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        queued_wakes: list[dict[str, Any]],
        *,
        commit_refusals: list[dict[str, Any]] | None,
        causal_parent_id: str,
    ) -> str:
        actor_id = str(wake["actor_id"])
        payload = operation["payload"]
        result = operation["result"]
        action = OfferAction(str(payload["action"]))
        offers = projection.setdefault("offers", [])
        if action == OfferAction.PROPOSE:
            terms = [AgreementTerm.model_validate(term) for term in payload["terms"]]
            validated_terms, code = self.pack.offer_terms_request(
                actor_id,
                str(payload["recipient"]),
                terms,
            )
            if validated_terms is None:
                return self._refuse_commit_time_offer(
                    run_id,
                    tick,
                    wake,
                    operation,
                    events,
                    commit_refusals,
                    code,
                    causal_parent_id=causal_parent_id,
                )
            offer = {
                "id": result["offer_id"],
                "issuer": actor_id,
                "recipient": payload["recipient"],
                "terms": [term.model_dump(mode="json") for term in validated_terms],
                "message": payload["message"],
                "created_tick": tick,
                "expires_tick": result.get("expires_tick"),
                "status": OfferStatus.PROPOSED.value,
                "parent_offer_id": "",
                "visibility": "PRIVATE",
            }
            offers.append(offer)
            visible_actor_ids = self._offer_visible_actor_ids(offer)
            proposed = self._event(
                run_id,
                tick,
                "OFFER_PROPOSED",
                {"offer": offer, "visibility": visible_actor_ids},
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            offer["proposal_event_id"] = proposed["id"]
            events.append(proposed)
            queued_wakes.append(
                {
                    "run_id": run_id,
                    "actor_id": offer["recipient"],
                    "wake_type": CrisisWakeType.OFFER_CHANGE,
                    "tick": tick,
                    "trigger_event_id": proposed["id"],
                }
            )
            return proposed["id"]

        offer = next(
            (item for item in offers if item.get("id") == payload["offer_id"]),
            None,
        )
        if offer is None:
            return self._refuse_commit_time_offer(
                run_id,
                tick,
                wake,
                operation,
                events,
                commit_refusals,
                "unknown_offer",
                causal_parent_id=causal_parent_id,
            )
        if offer.get("status") != OfferStatus.PROPOSED.value:
            return self._refuse_commit_time_offer(
                run_id,
                tick,
                wake,
                operation,
                events,
                commit_refusals,
                "offer_not_open",
                causal_parent_id=causal_parent_id,
            )
        visible_actor_ids = self._offer_visible_actor_ids(offer)
        if action in {OfferAction.ACCEPT, OfferAction.REJECT, OfferAction.COUNTER} and (
            offer.get("recipient") != actor_id
        ):
            return self._refuse_commit_time_offer(
                run_id,
                tick,
                wake,
                operation,
                events,
                commit_refusals,
                "offer_response_denied",
                causal_parent_id=causal_parent_id,
            )
        if action == OfferAction.WITHDRAW and offer.get("issuer") != actor_id:
            return self._refuse_commit_time_offer(
                run_id,
                tick,
                wake,
                operation,
                events,
                commit_refusals,
                "offer_withdrawal_denied",
                causal_parent_id=causal_parent_id,
            )
        if action == OfferAction.COUNTER:
            terms = [AgreementTerm.model_validate(term) for term in payload["terms"]]
            validated_terms, code = self.pack.offer_terms_request(
                actor_id,
                str(offer["issuer"]),
                terms,
            )
            if validated_terms is None:
                return self._refuse_commit_time_offer(
                    run_id,
                    tick,
                    wake,
                    operation,
                    events,
                    commit_refusals,
                    code,
                    causal_parent_id=causal_parent_id,
                )
            offer["status"] = OfferStatus.COUNTERED.value
            counter_offer = {
                "id": result["offer_id"],
                "issuer": actor_id,
                "recipient": offer["issuer"],
                "terms": [term.model_dump(mode="json") for term in validated_terms],
                "message": payload["message"],
                "created_tick": tick,
                "expires_tick": result.get("expires_tick"),
                "status": OfferStatus.PROPOSED.value,
                "parent_offer_id": offer["id"],
                "visibility": "PRIVATE",
            }
            offers.append(counter_offer)
            countered = self._event(
                run_id,
                tick,
                "OFFER_COUNTERED",
                {
                    "offer": offer,
                    "counter_offer": counter_offer,
                    "visibility": visible_actor_ids,
                },
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            offer["counter_event_id"] = countered["id"]
            counter_offer["proposal_event_id"] = countered["id"]
            events.append(countered)
            queued_wakes.append(
                {
                    "run_id": run_id,
                    "actor_id": counter_offer["recipient"],
                    "wake_type": CrisisWakeType.OFFER_CHANGE,
                    "tick": tick,
                    "trigger_event_id": countered["id"],
                }
            )
            return countered["id"]

        if action == OfferAction.ACCEPT:
            offer["status"] = OfferStatus.ACCEPTED.value
            accepted = self._event(
                run_id,
                tick,
                "OFFER_ACCEPTED",
                {"offer": offer, "visibility": visible_actor_ids},
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            offer["accept_event_id"] = accepted["id"]
            events.append(accepted)
            agreement = {
                "id": result["agreement_id"],
                "parties": visible_actor_ids,
                "terms": list(offer["terms"]),
                "effective_tick": tick,
                "status": AgreementStatus.ACTIVE.value,
                "source_offer_ids": self._offer_lineage_ids(offers, offer),
                "visibility": "PRIVATE",
            }
            projection.setdefault("agreements", []).append(agreement)
            created = self._event(
                run_id,
                tick,
                "AGREEMENT_CREATED",
                {"agreement": agreement, "visibility": visible_actor_ids},
                seat_id=actor_id,
                causal_parent_ids=[accepted["id"]],
            )
            agreement["creation_event_id"] = created["id"]
            events.append(created)
            for party_id in visible_actor_ids:
                queued_wakes.append(
                    {
                        "run_id": run_id,
                        "actor_id": party_id,
                        "wake_type": CrisisWakeType.AGREEMENT_CHANGE,
                        "tick": tick,
                        "trigger_event_id": created["id"],
                    }
                )
            return created["id"]

        if action == OfferAction.REJECT:
            offer["status"] = OfferStatus.REJECTED.value
            event_type = "OFFER_REJECTED"
            counterpart = offer["issuer"]
        elif action == OfferAction.WITHDRAW:
            offer["status"] = OfferStatus.WITHDRAWN.value
            event_type = "OFFER_WITHDRAWN"
            counterpart = offer["recipient"]
        else:
            raise CrisisRunError("unsupported accepted Offer action")
        changed = self._event(
            run_id,
            tick,
            event_type,
            {"offer": offer, "visibility": visible_actor_ids},
            seat_id=actor_id,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
        )
        offer["status_event_id"] = changed["id"]
        events.append(changed)
        queued_wakes.append(
            {
                "run_id": run_id,
                "actor_id": counterpart,
                "wake_type": CrisisWakeType.OFFER_CHANGE,
                "tick": tick,
                "trigger_event_id": changed["id"],
            }
        )
        return changed["id"]

    def _refuse_commit_time_offer(
        self,
        run_id: str,
        tick: int,
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        commit_refusals: list[dict[str, Any]] | None,
        code: str,
        *,
        causal_parent_id: str,
    ) -> str:
        result = {"status": "rejected", "code": code}
        operation["status"] = "REJECTED"
        operation["result"] = result
        if commit_refusals is not None:
            commit_refusals.append({"operation_id": operation["id"], "result": result})
        event_type = (
            "HUMAN_REQUEST_REJECTED"
            if wake["source"] == "human"
            else "ACTOR_TOOL_REJECTED"
        )
        events.append(
            self._event(
                run_id,
                tick,
                event_type,
                {
                    "wake_id": wake["id"],
                    "tool": operation["tool_name"],
                    "code": code,
                    "visibility": [wake["actor_id"]],
                },
                seat_id=wake["actor_id"],
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
        )
        return causal_parent_id

    @staticmethod
    def _offer_lineage_ids(offers: list[dict[str, Any]], offer: dict[str, Any]) -> list[str]:
        by_id = {str(item["id"]): item for item in offers}
        lineage: list[str] = []
        current = offer
        while current:
            lineage.append(str(current["id"]))
            parent_id = str(current.get("parent_offer_id") or "")
            current = by_id.get(parent_id)
        return list(reversed(lineage))

    def _start_investigation(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        causal_parent_id: str,
    ) -> str:
        actor_id = str(wake["actor_id"])
        payload = operation["payload"]
        result = operation["result"]
        request, code = self.pack.investigation_request(
            actor_id,
            str(payload["target"]),
            str(payload.get("method", "")),
            projection,
            tick,
        )
        if request is None:
            raise CrisisRunError(f"accepted Investigation became unavailable: {code}")
        if result["definition_id"] != request.definition.id:
            raise CrisisRunError("accepted Investigation definition changed before commit")
        if int(result["expected_result_tick"]) != request.expected_result_tick:
            raise CrisisRunError("accepted Investigation result time changed before commit")
        visible_actor_ids = (
            sorted(self.pack.actor_by_id)
            if request.definition.visibility.value == "PUBLIC"
            else [actor_id]
        )
        started = {
            "id": result["investigation_id"],
            "definition_id": request.definition.id,
            "actor_id": actor_id,
            "question": payload["question"],
            "target_id": request.target_id,
            "method": request.definition.method,
            "started_tick": tick,
            "expected_result_tick": request.expected_result_tick,
            "status": "IN_PROGRESS",
            "visibility": request.definition.visibility.value,
        }
        projection.setdefault("investigations", []).append(started)
        started_event = self._event(
            run_id,
            tick,
            "INVESTIGATION_STARTED",
            {"wake_id": wake["id"], "investigation": started, "visibility": visible_actor_ids},
            seat_id=actor_id,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
        )
        started["start_event_id"] = started_event["id"]
        events.append(started_event)
        return started_event["id"]

    def _start_operation(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        operation: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        causal_parent_id: str,
    ) -> str:
        actor_id = str(wake["actor_id"])
        payload = operation["payload"]
        result = operation["result"]
        request, code = self.pack.operation_request(
            actor_id,
            str(payload["operation_definition_id"]),
            list(payload["targets"]),
            projection,
            tick,
        )
        if request is None:
            raise CrisisRunError(f"accepted Operation became unavailable: {code}")
        if int(result["expected_complete_tick"]) != request.expected_complete_tick:
            raise CrisisRunError("accepted Operation completion time changed before commit")
        visible_actor_ids = (
            sorted(self.pack.actor_by_id)
            if request.definition.visibility.value == "PUBLIC"
            else [actor_id]
        )
        started = {
            "id": result["operation_id"],
            "definition_id": request.definition.id,
            "actor_id": actor_id,
            "target_ids": list(request.target_ids),
            "target_map": request.target_map,
            "started_tick": tick,
            "expected_complete_tick": request.expected_complete_tick,
            "status": "IN_PROGRESS",
            "visibility": request.definition.visibility.value,
            "interruptibility": request.definition.interruptibility,
            "input_state": request.input_state,
            "result_state": {},
            "description": payload["description"],
        }
        projection.setdefault("operations", []).append(started)
        started_event = self._event(
            run_id,
            tick,
            "OPERATION_STARTED",
            {"wake_id": wake["id"], "operation": started, "visibility": visible_actor_ids},
            seat_id=actor_id,
            causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
        )
        started["start_event_id"] = started_event["id"]
        events.append(started_event)
        state_events, _ = self._apply_operation_state_effects(
            run_id,
            tick,
            projection,
            started,
            request.definition.start_effects,
            phase="start",
            causal_parent_id=started_event["id"],
            visible_actor_ids=visible_actor_ids,
        )
        events.extend(state_events)
        if request.definition.kind.value == "MOVEMENT":
            destination_id = request.target_map[request.definition.movement_destination_target]
            movement = {
                "id": f"movement-{uuid.uuid4().hex[:16]}",
                "operation_id": started["id"],
                "actor_id": actor_id,
                "from": projection["positions"][actor_id],
                "to": destination_id,
                "started_tick": tick,
                "arrival_tick": request.expected_complete_tick,
                "status": "in_transit",
            }
            projection.setdefault("movements", []).append(movement)
            movement_event = self._event(
                run_id,
                tick,
                "MOVEMENT_STARTED",
                movement,
                seat_id=actor_id,
                causal_parent_ids=[started_event["id"]],
            )
            movement["start_event_id"] = movement_event["id"]
            started["movement_id"] = movement["id"]
            events.append(movement_event)
        return started_event["id"]

    @staticmethod
    def _same_material_plan(current: dict[str, Any] | None, candidate: dict[str, Any]) -> bool:
        if current is None:
            return False
        return (
            CrisisRunEngine._plan_text_key(current.get("objective", ""))
            == CrisisRunEngine._plan_text_key(candidate.get("objective", ""))
            and CrisisRunEngine._plan_texts_key(current.get("steps", []))
            == CrisisRunEngine._plan_texts_key(candidate.get("steps", []))
            and CrisisRunEngine._plan_texts_key(current.get("reconsider_when", []))
            == CrisisRunEngine._plan_texts_key(candidate.get("reconsider_when", []))
        )

    @staticmethod
    def _plan_texts_key(values: list[Any]) -> tuple[str, ...]:
        return tuple(CrisisRunEngine._plan_text_key(value) for value in values)

    @staticmethod
    def _plan_text_key(value: Any) -> str:
        return "".join(
            character
            for character in unicodedata.normalize("NFKC", str(value)).casefold()
            if not character.isspace() and not unicodedata.category(character).startswith("P")
        )

    def _perspective_from(
        self,
        run_id: str,
        actor_id: str,
        projection: dict[str, Any],
        *,
        knowledge: list[Any] | None = None,
        beliefs: dict[str, Any] | None = None,
        plan: list[Any] | None = None,
        revisits: list[Any] | None = None,
    ) -> dict[str, Any]:
        lifetime = self.db.worldline_lifetime(run_id, actor_id)
        if lifetime is None:
            raise CrisisRunError("actor life state is missing")
        known = list(lifetime["knowledge"] if knowledge is None else knowledge)
        current_revisits = list(lifetime["revisits"] if revisits is None else revisits)
        return {
            "run_id": run_id,
            "actor_id": actor_id,
            "tick": int(projection["tick"]),
            "location": projection["positions"][actor_id],
            "knowledge": known,
            "beliefs": dict(lifetime["beliefs"] if beliefs is None else beliefs),
            "plan": list(lifetime["plan"] if plan is None else plan),
            "revisits": current_revisits,
            "resources": dict(lifetime["resources"]),
            "authority": list(lifetime["authority"]),
            **self._affordance_manifest(actor_id, projection, current_revisits),
        }

    def _affordance_manifest(
        self,
        actor_id: str,
        projection: dict[str, Any],
        revisits: list[Any],
    ) -> dict[str, Any]:
        actor = self.pack.actor_by_id[actor_id]
        location_id = str(projection["positions"][actor_id])
        location = self.pack.location_by_id[location_id]
        contactable_actors = [
            {"id": candidate.id, "display_name": candidate.display_name}
            for candidate in self.pack.crisis.actors
            if candidate.id != actor_id
            and self.world.route_days(location_id, projection["positions"][candidate.id]) is not None
        ]
        projected_entities = projection.get("entities", {})
        own_assets = [
            {
                "id": asset_id,
                "type": projected_entities[asset_id]["type"],
                "display_name": projected_entities[asset_id]["display_name"],
                "state": projected_entities[asset_id]["state"],
            }
            for asset_id in actor.asset_ids
            if asset_id in projected_entities
        ]
        known_entities = []
        if location_id in projected_entities:
            location_entity = projected_entities[location_id]
            known_entities.append(
                {
                    "id": location_id,
                    "type": location_entity["type"],
                    "display_name": location_entity["display_name"],
                    "state": location_entity["state"],
                }
            )
        else:
            known_entities.append(
                {"id": location.id, "type": "PLACE", "display_name": location.display_name}
            )
        known_entities.extend(
            asset for asset in own_assets if asset["id"] not in {item["id"] for item in known_entities}
        )
        active_operations = [
            operation
            for operation in projection.get("operations", [])
            if operation.get("actor_id") == actor_id
            and operation.get("status") in {"PLANNED", "IN_PROGRESS"}
        ]
        active_investigations = [
            investigation
            for investigation in projection.get("investigations", [])
            if investigation.get("actor_id") == actor_id
            and investigation.get("status") in {"PLANNED", "IN_PROGRESS"}
        ]
        available_investigations = self.pack.investigation_affordances(
            actor_id,
            projection,
            int(projection["tick"]),
        )
        available_offer_terms = self.pack.offer_term_affordances(actor_id)
        active_offers = [
            offer
            for offer in projection.get("offers", [])
            if offer.get("status") == OfferStatus.PROPOSED.value
            and actor_id in {offer.get("issuer"), offer.get("recipient")}
        ]
        active_agreements = [
            agreement
            for agreement in projection.get("agreements", [])
            if agreement.get("status") == AgreementStatus.ACTIVE.value
            and actor_id in agreement.get("parties", [])
        ]
        visible_pressures = [
            pressure
            for pressure in projection.get("pressures", [])
            if pressure.get("status") == PressureStatus.APPLIED.value
            and actor_id in self._pressure_visible_actor_ids(pressure)
        ]
        known_entity_ids = {item["id"] for item in known_entities}
        investigation_target_ids = {
            affordance["target"]["id"] for affordance in available_investigations
        }
        investigation_target_ids.update(
            str(investigation["target_id"]) for investigation in active_investigations
        )
        for target_id in sorted(investigation_target_ids):
            target = projected_entities.get(target_id)
            if target is None or target_id in known_entity_ids:
                continue
            known_entities.append(
                {
                    "id": target_id,
                    "type": target["type"],
                    "display_name": target["display_name"],
                    "state": target["state"],
                }
            )
            known_entity_ids.add(target_id)
        agreement_subject_ids = {
            affordance["subject"]["id"] for affordance in available_offer_terms
        }
        agreement_subject_ids.update(
            str(term["subject"])
            for offer in active_offers
            for term in offer.get("terms", [])
        )
        agreement_subject_ids.update(
            str(term["subject"])
            for agreement in active_agreements
            for term in agreement.get("terms", [])
        )
        agreement_subject_ids.update(
            str(effect["subject"])
            for pressure in visible_pressures
            for effect in pressure.get("effects", [])
        )
        for subject_id in sorted(agreement_subject_ids):
            subject = projected_entities.get(subject_id)
            if subject is None or subject_id in known_entity_ids:
                continue
            known_entities.append(
                {
                    "id": subject_id,
                    "type": subject["type"],
                    "display_name": subject["display_name"],
                    "state": subject["state"],
                }
            )
            known_entity_ids.add(subject_id)
        constraints = [{"kind": "authority", "description": "只能使用当前职权内的行动。"}]
        if self.pack.crisis.routes:
            constraints.append(
                {"kind": "travel_time", "description": "通信与行动需要沿已知路线或时程等待。"}
            )
        if available_investigations:
            constraints.append(
                {"kind": "information", "description": "调查会在模拟时间后带回带来源和可靠性的观察。"}
            )
        if active_offers or active_agreements:
            constraints.append(
                {"kind": "agreement", "description": "已经提出或生效的条件会约束之后可采取的行动。"}
            )
        constraints.extend(
            {"kind": "pressure", "description": str(pressure["description"])}
            for pressure in visible_pressures
        )
        return {
            "contactable_actors": contactable_actors,
            "known_entities": known_entities,
            "own_assets": own_assets,
            "available_operations": self.pack.operation_affordances(
                actor_id, projection, int(projection["tick"])
            ),
            "active_operations": active_operations,
            "available_investigations": available_investigations,
            "active_investigations": active_investigations,
            "available_offer_terms": available_offer_terms,
            "active_offers": active_offers,
            "active_agreements": active_agreements,
            "visible_pressures": visible_pressures,
            "current_revisits": revisits,
            "meaningful_world_constraints": constraints,
        }

    def actor_perspective(self, run_id: str, actor_id: str) -> dict[str, Any]:
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        return self._perspective_from(run_id, actor_id, snapshot["projection"])

    def run_summary(self, run_id: str) -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run not found")
        controllers = json.loads(run["controller_map_json"])
        maximum_tick = json.loads(run["simulation_boundary_json"])["maximum_tick"]
        next_tick = self._next_tick(run_id)
        outcome_json = json.loads(run.get("outcome_json", "{}"))
        return {
            "id": run_id,
            "volume_id": run.get("volume_id", ""),
            "crisis_id": run["crisis_id"],
            "crisis_version": int(run.get("crisis_version", 0)),
            "crisis_hash": run.get("crisis_hash", ""),
            "resolution_contract_id": run.get("resolution_contract_id", ""),
            "resolution_contract_version": int(run.get("resolution_contract_version", 0)),
            "resolution_seed": run.get("resolution_seed", ""),
            "crisis_phase": run.get("crisis_phase", ""),
            "outcome_json": outcome_json,
            "settlement_reason": run.get("settlement_reason", ""),
            "mode": "TAKEOVER" if "HUMAN" in controllers.values() else "WATCH",
            "status": run["status"],
            "current_tick": int(run["current_tick"]),
            "maximum_tick": maximum_tick,
            "can_continue": (
                run["status"] == "ACTIVE"
                and (next_tick is not None or run.get("crisis_phase") == "RESOLUTION_PENDING")
            ),
            "runtime_mode": run["runtime_mode"],
            "runtime_phase": run.get("runtime_phase", "READY"),
            "runtime_error_code": run.get("runtime_error_code", ""),
            "human_actor": next(
                (actor_id for actor_id, controller in controllers.items() if controller == "HUMAN"),
                None,
            ),
            "human_decision": self.human_decision_state(run_id, int(run["current_tick"])),
            "created_at": run["created_at"],
            "seal_reason": run["seal_reason"],
        }

    def world_view(self, run_id: str) -> dict[str, Any]:
        self._activate_run_pack(run_id)
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = snapshot["projection"]
        movements = {
            movement["actor_id"]: movement
            for movement in projection.get("movements", [])
            if movement["status"] == "in_transit"
        }
        return {
            "tick": int(projection["tick"]),
            "surface": self.pack.surface_projection(projection, include_messages=True),
            "corridor": [
                location.model_dump(mode="json")
                for location in sorted(self.pack.crisis.corridor, key=lambda item: item.order)
            ],
            "actors": [
                {
                    "id": actor.id,
                    "display_name": actor.display_name,
                    "location": projection["positions"][actor.id],
                    "movement": movements.get(actor.id),
                }
                for actor in self.pack.crisis.actors
            ],
            "messages": list(projection.get("messages", [])),
            "entities": list(projection.get("entities", {}).values()),
            "operations": list(projection.get("operations", [])),
            "investigations": list(projection.get("investigations", [])),
            "offers": list(projection.get("offers", [])),
            "agreements": list(projection.get("agreements", [])),
            "pressures": [
                pressure
                for pressure in projection.get("pressures", [])
                if pressure.get("status") == PressureStatus.APPLIED.value
            ],
            "resolution": dict(projection.get("resolution", {})),
            "settlement": dict(projection.get("settlement", {})),
            "boundary": self.pack.crisis.simulation_boundary.model_dump(mode="json"),
        }

    def _human_decision_operation_results(
        self, run_id: str, tick: int, actor_id: str
    ) -> list[dict[str, Any]]:
        wake = next(
            (
                item
                for item in self.db.crisis_wakes(run_id, tick=tick)
                if item["actor_id"] == actor_id
                and item["wake_type"] == "DECISION"
            ),
            None,
        )
        if wake is None:
            return []
        results: list[dict[str, Any]] = []
        for operation in self.db.crisis_wake_operations(wake["id"]):
            result = {
                "tool": operation["tool_name"],
                "status": operation["status"],
            }
            if operation["tool_name"] == "communicate":
                recipient = str(operation["payload"].get("recipient") or "")
                actor = self.pack.actor_by_id.get(recipient)
                result["recipient"] = actor.display_name if actor else "未识别收件人"
                if operation["status"] == "COMMITTED":
                    result["arrival_tick"] = operation["result"].get("arrival_tick")
                elif operation["result"].get("code") == "invalid_recipient":
                    result["reason"] = "收件人无法识别"
                else:
                    result["reason"] = "这项请求未执行"
            elif operation["tool_name"] == "investigate":
                target_id = str(operation["payload"].get("target") or "")
                target = self.pack.entity_by_id.get(target_id)
                result["target"] = target.display_name if target else "未识别目标"
                if operation["status"] == "COMMITTED":
                    result["expected_result_tick"] = operation["result"].get(
                        "expected_result_tick"
                    )
                else:
                    result["reason"] = "这项调查未能开始"
            elif operation["tool_name"] == "manage_offer":
                action = str(operation["payload"].get("action") or "")
                result["action"] = action
                if operation["status"] == "COMMITTED":
                    result["offer_id"] = operation["result"].get("offer_id", "")
                    result["agreement_id"] = operation["result"].get("agreement_id", "")
                else:
                    result["reason"] = "这项条件未能进入世界"
            results.append(result)
        return results

    def product_perspective(self, run_id: str, actor_id: str) -> dict[str, Any]:
        self._activate_run_pack(run_id)
        if actor_id not in self.pack.actor_by_id:
            raise CrisisRunError("Actor not found")
        actor = self.pack.actor_by_id[actor_id]
        perspective = self.actor_perspective(run_id, actor_id)
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        known_situation = []
        for item in perspective["knowledge"]:
            if isinstance(item, str):
                assertion = self.pack.assertion_by_id.get(item) or next(
                    (candidate for candidate in self.pack.assertions if candidate.claim == item),
                    None,
                )
                known_situation.append(
                    {
                        "text": assertion.normalized_evidence if assertion else item,
                        "evidence_status": (
                            assertion.evidence_status.value if assertion else "known"
                        ),
                    }
                )
            elif isinstance(item, dict) and item.get("kind") == "observation":
                known_situation.append(
                    {
                        "text": str(item["observation"]),
                        "evidence_status": "observed",
                        "source": str(item.get("source", "")),
                        "reliability": str(item.get("reliability", "")),
                    }
                )
            elif isinstance(item, dict) and item.get("kind") == "resolution":
                known_situation.append(
                    {
                        "text": str(item.get("content", "危局已经形成局部结果。")),
                        "evidence_status": "resolved",
                    }
                )
        decisions = []
        for event in self.db.worldline_events(run_id):
            if event["seat_id"] != actor_id:
                continue
            if event["event_type"] == "HUMAN_DECISION_APPLIED":
                decisions.append(
                    {
                        "tick": int(event["tick"]),
                        "summary": str(event["payload"]["summary"]),
                        "operation_results": self._human_decision_operation_results(
                            run_id, int(event["tick"]), actor_id
                        ),
                    }
                )
            elif event["event_type"] == "HUMAN_SILENCE":
                decisions.append(
                    {
                        "tick": int(event["tick"]),
                        "summary": "暂不追加命令，继续观察。",
                        "operation_results": [],
                    }
                )
        return {
            "actor": {"id": actor.id, "display_name": actor.display_name},
            "tick": perspective["tick"],
            "location": perspective["location"],
            "knowledge": perspective["knowledge"],
            "beliefs": perspective["beliefs"],
            "plan": perspective["plan"],
            "revisits": perspective["revisits"],
            "resources": perspective["resources"],
            "contactable_actors": perspective["contactable_actors"],
            "known_entities": perspective["known_entities"],
            "own_assets": perspective["own_assets"],
            "available_operations": perspective["available_operations"],
            "active_operations": perspective["active_operations"],
            "available_investigations": perspective["available_investigations"],
            "active_investigations": perspective["active_investigations"],
            "available_offer_terms": perspective["available_offer_terms"],
            "active_offers": perspective["active_offers"],
            "active_agreements": perspective["active_agreements"],
            "visible_pressures": perspective["visible_pressures"],
            "current_revisits": perspective["current_revisits"],
            "meaningful_world_constraints": perspective["meaningful_world_constraints"],
            "known_situation": known_situation,
            "outgoing_messages": [
                message
                for message in snapshot["projection"].get("messages", [])
                if message["sender"] == actor_id
            ],
            "decisions": decisions,
            "role_charter": actor.role_charter.model_dump(mode="json"),
            "surface": self.pack.surface_projection(
                snapshot["projection"], visible_actor_ids={actor_id}
            ),
        }

    def seal(self, run_id: str, reason: str = "user_exit") -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        running = [
            wake
            for wake in self.db.nonterminal_crisis_wakes(run_id)
            if wake["status"] in {"RUNNING", "STAGED"}
        ]
        if running:
            if run["runtime_mode"] == "live":
                self.db.set_crisis_runtime_state(run_id, "SEALING")
            raise CrisisRunConflict(
                "这一刻仍在结束，暂不能封存。",
                code="seal_waits_for_wake",
                state="SEALING",
            )
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        event = self._event(
            run_id,
            int(run["current_tick"]),
            "RUN_SEALED",
            {"reason": reason},
            causal_parent_ids=[self.db.worldline_events(run_id)[-1]["id"]]
            if self.db.worldline_events(run_id)
            else [],
        )
        self.db.commit_worldline_seal(
            run_id,
            event,
            reason=reason,
            outcome=f"危局在第 {run['current_tick']} 日封存",
            snapshot=snapshot["projection"],
            revoke_agent_bindings=True,
            runtime_phase="CLEANUP_PENDING" if run["runtime_mode"] == "live" else None,
            runtime_error_code="runtime_cleanup_pending" if run["runtime_mode"] == "live" else "",
            cancel_queued_wakes=True,
        )
        return self.run_summary(run_id)

    def replay(self, run_id: str) -> dict[str, Any]:
        self._activate_run_pack(run_id)
        run = self.run_summary(run_id)
        if run["status"] != "SEALED":
            raise CrisisRunError("Replay becomes available after the Run is sealed")
        labels = {
            "RUN_CREATED": "危局开始",
            "CRISIS_CHECKPOINT_ENTERED": "三方进入同一段未决时间",
            "MESSAGE_DISPATCHED": "一封信已经上路",
            "MESSAGE_DELIVERED": "一封信抵达收信人",
            "PLAN_UPDATED": "有人修正了自己的打算",
            "BELIEF_UPDATED": "有人重新判断一项不确定之事",
            "REVISIT_SCHEDULED": "有人决定稍后重新判断",
            "REVISIT_DUE": "一次重新判断已经到期",
            "REVISIT_FULFILLED": "一次重新判断已经发生",
            "COMMITMENT_SCHEDULED": "有人决定稍后再作判断",
            "COMMITMENT_FULFILLED": "一次约定的复查已经发生",
            "INVESTIGATION_STARTED": "一项调查已经开始",
            "INVESTIGATION_COMPLETED": "一项调查已经完成",
            "OBSERVATION_OBTAINED": "一条调查观察已经抵达",
            "OFFER_PROPOSED": "一项条件已经提出",
            "OFFER_COUNTERED": "一项条件被重新提出",
            "OFFER_ACCEPTED": "一项条件已经接受",
            "OFFER_REJECTED": "一项条件被拒绝",
            "OFFER_WITHDRAWN": "一项条件被撤回",
            "OFFER_EXPIRED": "一项条件已经失效",
            "AGREEMENT_CREATED": "一项约定已经生效",
            "AGREEMENT_FULFILLED": "一项约定已经履行",
            "AGREEMENT_BREACHED": "一项约定已经被违背",
            "PRESSURE_APPLIED": "外部压力进入危局",
            "OPERATION_STARTED": "一项行动已经开始",
            "OPERATION_COMPLETED": "一项行动已经完成",
            "ENTITY_STATE_CHANGED": "一项关键资产状态已经改变",
            "RESOLUTION_GATE_REACHED": "局势进入不可逆节点",
            "RESOLUTION_APPLIED": "危局形成局部结果",
            "RESOLUTION_REPORT_DELIVERED": "危局结果传到一位主体",
            "CRISIS_SETTLED": "危局已经结算",
            "MOVEMENT_STARTED": "一支队伍开始移动",
            "MOVEMENT_ARRIVED": "一支队伍抵达新的位置",
            "ACTOR_ACTION_RECORDED": "有人作出有限行动",
            "HUMAN_SILENCE": "你选择暂不追加命令",
            "HUMAN_DECISION_APPLIED": "你的决定进入这段历史",
            "RUN_SEALED": "这一局已封存",
        }
        items = []
        all_actor_ids = set(self.pack.actor_by_id)
        events = self.db.worldline_events(run_id)
        events_by_id = {str(event["id"]): event for event in events}
        for event in events:
            if event["event_type"] not in labels:
                continue
            visible_to = self._replay_visible_to(event)
            causes = []
            for parent_id in event["causal_parent_ids"]:
                parent = events_by_id.get(str(parent_id))
                if parent is None:
                    continue
                causes.append(
                    {
                        "id": str(parent_id),
                        "title": labels.get(parent["event_type"], "一项当时的行动"),
                        "actor_id": parent["seat_id"],
                    }
                )
            items.append(
                {
                    "id": event["id"],
                    "tick": int(event["tick"]),
                    "title": labels[event["event_type"]],
                    "actor_id": event["seat_id"],
                    "private": set(visible_to) != all_actor_ids,
                    "visible_to": visible_to,
                    "causal_parent_ids": list(event["causal_parent_ids"]),
                    "causes": causes,
                    "detail": self._replay_detail(event),
                }
            )
        return {
            "run": run,
            "items": items,
            "world": self.world_view(run_id),
            "actors": [
                {"id": actor.id, "display_name": actor.display_name}
                for actor in self.pack.crisis.actors
            ],
        }

    def _replay_visible_to(self, event: dict[str, Any]) -> list[str]:
        payload = event["payload"]
        explicit = payload.get("visibility")
        if isinstance(explicit, list):
            return sorted(actor_id for actor_id in explicit if actor_id in self.pack.actor_by_id)
        if event["event_type"] == "MESSAGE_DISPATCHED":
            return [str(payload["sender"])]
        if event["event_type"] == "MESSAGE_DELIVERED":
            return sorted({str(payload["sender"]), str(payload["recipient"])})
        if event["event_type"] in {"RUN_CREATED", "CRISIS_CHECKPOINT_ENTERED", "RUN_SEALED"}:
            return sorted(self.pack.actor_by_id)
        if event["seat_id"] in self.pack.actor_by_id:
            return [str(event["seat_id"])]
        return sorted(self.pack.actor_by_id)

    def _replay_detail(self, event: dict[str, Any]) -> str:
        payload = event["payload"]
        if event["event_type"] in {"MESSAGE_DISPATCHED", "MESSAGE_DELIVERED"}:
            sender = self.pack.actor_by_id[payload["sender"]].display_name
            recipient = self.pack.actor_by_id[payload["recipient"]].display_name
            return f"{sender} → {recipient}：{payload['content']}"
        if event["event_type"] == "PLAN_UPDATED":
            return str(payload["plan"]["objective"])
        if event["event_type"] in {"INVESTIGATION_STARTED", "INVESTIGATION_COMPLETED"}:
            investigation = payload["investigation"]
            definition = self.pack.investigation_by_id.get(str(investigation["definition_id"]))
            if definition is None:
                return str(investigation.get("question", ""))
            question = str(investigation.get("question", ""))
            return f"{definition.display_name}：{question}" if question else definition.display_name
        if event["event_type"] == "OBSERVATION_OBTAINED":
            observation = payload["observation"]
            return (
                f"{observation['content']}"
                f"（来源：{observation['source']}；可靠性：{observation['reliability']}）"
            )
        if event["event_type"] in {
            "OFFER_PROPOSED",
            "OFFER_COUNTERED",
            "OFFER_ACCEPTED",
            "OFFER_REJECTED",
            "OFFER_WITHDRAWN",
            "OFFER_EXPIRED",
        }:
            offer = payload.get("counter_offer") or payload["offer"]
            issuer = self.pack.actor_by_id[str(offer["issuer"])].display_name
            recipient = self.pack.actor_by_id[str(offer["recipient"])].display_name
            terms = "；".join(
                f"{term['type']} {term['subject']}={term['value']}"
                for term in offer.get("terms", [])
            )
            message = str(offer.get("message", ""))
            detail = f"{issuer} → {recipient}：{terms}"
            return f"{detail}。{message}" if message else detail
        if event["event_type"] in {
            "AGREEMENT_CREATED",
            "AGREEMENT_FULFILLED",
            "AGREEMENT_BREACHED",
        }:
            agreement = payload["agreement"]
            parties = "、".join(
                self.pack.actor_by_id[str(actor_id)].display_name
                for actor_id in agreement["parties"]
            )
            terms = "；".join(
                f"{term['type']} {term['subject']}={term['value']}"
                for term in agreement.get("terms", [])
            )
            return f"{parties}：{terms}"
        if event["event_type"] == "PRESSURE_APPLIED":
            pressure = payload["pressure"]
            return f"{pressure['title']}：{pressure['description']}"
        if event["event_type"] in {"OPERATION_STARTED", "OPERATION_COMPLETED"}:
            operation = payload["operation"]
            definition = self.pack.operation_by_id.get(str(operation["definition_id"]))
            if definition is None:
                return str(operation.get("description", ""))
            description = str(operation.get("description", ""))
            return f"{definition.display_name}：{description}" if description else definition.display_name
        if event["event_type"] == "ENTITY_STATE_CHANGED":
            entity = self.pack.entity_by_id.get(str(payload["entity_id"]))
            display_name = entity.display_name if entity is not None else str(payload["entity_id"])
            return f"{display_name}：{payload['before']} → {payload['after']}"
        if event["event_type"] == "RESOLUTION_GATE_REACHED":
            return "；".join(payload["readiness"].get("reasons", []))
        if event["event_type"] == "RESOLUTION_APPLIED":
            return str(payload["result"].get("summary", ""))
        if event["event_type"] == "RESOLUTION_REPORT_DELIVERED":
            return str(payload["report"].get("content", ""))
        if event["event_type"] == "CRISIS_SETTLED":
            return str(payload["outcome"].get("resolution_variant", ""))
        if event["event_type"] == "MOVEMENT_ARRIVED":
            return f"抵达{self.pack.location_by_id[payload['to']].display_name}"
        if event["event_type"] == "HUMAN_DECISION_APPLIED":
            return str(payload["summary"])
        return ""

    def _trigger_for(self, wake: dict[str, Any]) -> dict[str, Any]:
        if not wake["trigger_event_id"]:
            return {"type": wake["wake_type"]}
        event = next(
            (
                item
                for item in self.db.worldline_events(wake["worldline_id"])
                if item["id"] == wake["trigger_event_id"]
            ),
            None,
        )
        if event is None:
            return {"type": wake["wake_type"]}
        if event["event_type"] == "MESSAGE_DELIVERED":
            return {
                "type": wake["wake_type"],
                "message_id": event["payload"]["id"],
                "sender": event["payload"]["sender"],
                "content": event["payload"]["content"],
            }
        if event["event_type"] == "OBSERVATION_OBTAINED":
            observation = event["payload"]["observation"]
            return {
                "type": wake["wake_type"],
                "observation_id": observation["id"],
                "investigation_id": observation["investigation_id"],
                "content": observation["content"],
                "source": observation["source"],
                "reliability": observation["reliability"],
            }
        if event["event_type"] == "PRESSURE_APPLIED":
            pressure = event["payload"]["pressure"]
            return {
                "type": wake["wake_type"],
                "pressure_id": pressure["id"],
                "title": pressure["title"],
                "content": pressure["description"],
            }
        if event["event_type"] == "RESOLUTION_APPLIED":
            result = event["payload"]["result"]
            return {
                "type": wake["wake_type"],
                "resolution_kind": result["kind"],
                "content": result["summary"],
            }
        if event["event_type"] == "RESOLUTION_REPORT_DELIVERED":
            report = event["payload"]["report"]
            return {
                "type": wake["wake_type"],
                "resolution_kind": report["resolution_kind"],
                "content": report["content"],
            }
        if event["event_type"].startswith("OFFER_"):
            offer = event["payload"].get("counter_offer") or event["payload"].get("offer", {})
            return {
                "type": wake["wake_type"],
                "offer_id": offer.get("id", ""),
                "issuer": offer.get("issuer", ""),
                "recipient": offer.get("recipient", ""),
                "terms": offer.get("terms", []),
                "message": offer.get("message", ""),
                "status": offer.get("status", ""),
            }
        if event["event_type"].startswith("AGREEMENT_"):
            agreement = event["payload"].get("agreement", {})
            return {
                "type": wake["wake_type"],
                "agreement_id": agreement.get("id", ""),
                "parties": agreement.get("parties", []),
                "terms": agreement.get("terms", []),
                "status": agreement.get("status", ""),
            }
        return {"type": wake["wake_type"], "event_id": event["id"]}

    def _controller_map(self, run_id: str) -> dict[str, str]:
        run = self.db.worldline(run_id)
        if run is None:
            raise CrisisRunError("Run not found")
        return json.loads(run["controller_map_json"])

    def _human_actor_id(self, run_id: str) -> str | None:
        human_actors = [
            actor_id
            for actor_id, controller in self._controller_map(run_id).items()
            if controller == "HUMAN"
        ]
        if len(human_actors) > 1:
            raise CrisisRunError("a Crisis Run can have only one Human actor")
        return human_actors[0] if human_actors else None

    def _queue_wake(
        self,
        run_id: str,
        actor_id: str,
        wake_type: CrisisWakeType | str,
        tick: int,
        *,
        trigger_event_id: str = "",
    ) -> dict[str, Any]:
        return self.db.create_crisis_wake(
            {
                "worldline_id": run_id,
                "actor_id": actor_id,
                "wake_type": CrisisWakeType(wake_type).value,
                "tick": tick,
                "source": self.actor_driver.source,
                "trigger_event_id": trigger_event_id,
            }
        )

    def _previous_repetition_count(self, run_id: str, actor_id: str, fingerprint: str) -> int:
        for event in reversed(self.db.worldline_events(run_id)):
            if event["event_type"] != "ACTOR_WAKE_COMPLETED" or event["seat_id"] != actor_id:
                continue
            if event["payload"].get("decision_fingerprint") == fingerprint:
                return int(event["payload"].get("repetition_count", 1))
            return 0
        return 0

    @staticmethod
    def _event(
        run_id: str,
        tick: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        seat_id: str | None = None,
        provenance: str = "branch_derived",
        causal_parent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": f"event-{uuid.uuid4().hex[:16]}",
            "worldline_id": run_id,
            "tick": tick,
            "event_type": event_type,
            "seat_id": seat_id,
            "payload": payload,
            "provenance": provenance,
            "causal_parent_ids": list(causal_parent_ids or []),
        }

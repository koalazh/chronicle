from __future__ import annotations

import copy
import difflib
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .config import AppConfig
from .crisis import CrisisPack
from .db import ChronicleDB, content_hash, stable_hash
from .decision import (
    DecisionInterpreter,
    FixtureDecisionInterpreter,
    ModelDecisionInterpreter,
)
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
    COMMITMENT_DUE = "COMMITMENT_DUE"
    REFLECTION = "REFLECTION"


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
            followup_days = {"li-zicheng": 2, "wu-sangui": 2, "dorgon": 4}[actor_id]
            world.schedule_followup(
                followup_days,
                "若无新消息，重新检查当前等待是否仍合理",
                idempotency_key=f"{wake['id']}:orient-followup",
            )
            return ActorTurnResult("已形成可修正的初始计划，并安排未来复查。")

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
                world.schedule_followup(
                    2,
                    "比较两方后续行动与书面承诺是否一致",
                    idempotency_key=f"{wake['id']}:compare-followup",
                )
            return ActorTurnResult("已按收到的信修正判断；没有替世界声明对方真实意图。")

        if wake_type == CrisisWakeType.COMMITMENT_DUE.value:
            return ActorTurnResult(f"第 {tick} 日复查后，暂不追加行动。")
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
        session_id = client.create_fresh_session(profile, key, str(wake["id"]))
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
            "若计划包含等待，应再用 schedule_followup 把重新判断的模拟日数登记下来。"
            if wake["wake_type"] == CrisisWakeType.ORIENT.value
            else "只在本次触发确实改变判断时更新计划；没有新行动是合法结果。"
        )
        return [
            {
                "role": "system",
                "content": (
                    "你是 Chronicle 危局中的长期历史主体，不是旁白、史官或游戏主持。"
                    "只依据本次私有视野判断；不要使用后世知识。世界事实只能通过 chronicle-world 工具改变。"
                    "你可以更新自己的计划和少量信念、安排未来复查、通信或请求有限行动。"
                    "工具拒绝不是 Wake 失败：可在同一 Agent Loop 中修正参数或选择不行动。"
                    "调用参数：update_plan(objective, steps, rationale, belief_updates, idempotency_key)；"
                    "schedule_followup(after_days, purpose, idempotency_key)；"
                    "communicate(recipient, content, idempotency_key)；"
                    "act(action, description, target, idempotency_key)，其中 prepare/hold 的 target "
                    "必须是私有视野 resources 中的键或自己的当前位置，move 的 target 必须是走廊地点 id。"
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
                            "act",
                            "update_plan",
                            "schedule_followup",
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
        self.pack = pack or CrisisPack.load(config.crisis_path)
        active = self.db.active_run()
        self.actor_driver = actor_driver or (
            HermesActorDriver(config, self.db)
            if active is not None and active["runtime_mode"] == "live"
            else FixtureActorDriver()
        )
        self.world = WorldService(self.db, self.pack)

    def create(self, mode: RunMode | str, *, runtime_mode: str = "fixture") -> dict[str, Any]:
        mode = RunMode(mode)
        if self.db.active_run() is not None or self.db.active_human_worldline() is not None:
            raise CrisisRunConflict("an active Chronicle Run already exists")
        if runtime_mode not in {"fixture", "live"}:
            raise CrisisRunError("runtime_mode must be fixture or live")

        run_id = f"run-{uuid.uuid4().hex[:16]}"
        controllers = {
            actor.id: (
                "HUMAN"
                if mode == RunMode.TAKEOVER and actor.id == "wu-sangui"
                else "AGENT"
            )
            for actor in self.pack.crisis.actors
        }
        epoch = (
            f"fixture-{stable_hash({'crisis': self.pack.crisis.id})[:12]}"
            if runtime_mode == "fixture"
            else f"hermes-{self.config.provider_hash()}-{uuid.uuid4().hex[:8]}"
        )
        profile_records: dict[str, dict[str, Any]] = {}
        if runtime_mode == "live":
            from .hermes import materialize_crisis_profiles

            agent_actors = [
                {
                    "id": actor.id,
                    "role_charter": actor.role_charter.model_dump(mode="json"),
                    "genesis_hash": stable_hash(self.pack.initial_perspective(actor.id)),
                    "initial_memory_snapshot": {
                        "memory_text": "",
                        "memory_hash": content_hash(""),
                    },
                }
                for actor in self.pack.crisis.actors
                if controllers[actor.id] == "AGENT"
            ]
            try:
                profile_records = materialize_crisis_profiles(
                    self.config,
                    run_id,
                    agent_actors,
                    crisis_id=self.pack.crisis.id,
                    runtime_epoch=epoch,
                )
            except Exception as exc:
                raise CrisisRunError("eager Hermes Profile materialization failed") from exc
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
        }
        events = [
            self._event(
                run_id,
                0,
                "RUN_CREATED",
                {
                    "crisis_id": self.pack.crisis.id,
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

        lifetimes: list[dict[str, Any]] = []
        for actor in self.pack.crisis.actors:
            perspective = self.pack.initial_perspective(actor.id)
            memory_text = ""
            memory_hash = content_hash("")
            if controllers[actor.id] == "AGENT":
                profile_name = (
                    f"fixture://{actor.id}"
                    if runtime_mode == "fixture"
                    else str(profile_records[actor.id]["profile"])
                )
                if runtime_mode == "live":
                    from .hermes import read_profile_memory

                    memory_text, memory_hash = read_profile_memory(self.config, profile_name)
            else:
                profile_name = ""
            lifetimes.append(
                {
                    "id": f"life-{uuid.uuid4().hex[:16]}",
                    "actor_id": actor.id,
                    "controller": controllers[actor.id],
                    "profile_name": profile_name,
                    "profile_metadata": {"source": runtime_mode} if profile_name else {},
                    "genesis_hash": stable_hash(perspective),
                    "memory_text": memory_text,
                    "memory_hash": memory_hash,
                    "knowledge": list(perspective["knowledge"]),
                    "beliefs": dict(actor.initial_beliefs),
                    "authority": list(actor.world_authority),
                    "role_charter": actor.role_charter.model_dump(mode="json"),
                    "plan": [],
                    "commitments": [],
                    "resources": dict(actor.resources),
                    "last_perspective": perspective,
                }
            )
        try:
            run = self.db.create_crisis_run_bundle(
                {
                    "id": run_id,
                    "crisis_id": self.pack.crisis.id,
                    "controller_map": controllers,
                    "simulation_boundary": self.pack.crisis.simulation_boundary.model_dump(mode="json"),
                    "runtime_mode": runtime_mode,
                    "runtime_epoch": epoch,
                },
                events,
                lifetimes,
                projection,
            )
        except Exception:
            if profile_records:
                from .hermes import remove_crisis_profiles

                remove_crisis_profiles(
                    self.config,
                    run_id,
                    [str(item["profile"]) for item in profile_records.values()],
                )
            raise
        for actor_id, controller in controllers.items():
            if controller != "AGENT":
                continue
            profile_name = (
                f"fixture://{actor_id}"
                if runtime_mode == "fixture"
                else str(profile_records[actor_id]["profile"])
            )
            self.db.create_agent_binding(
                {
                    "worldline_id": run_id,
                    "actor_id": actor_id,
                    "profile_name": profile_name,
                    "ownership_marker": (
                        stable_hash(
                            {"run_id": run_id, "actor_id": actor_id, "source": "fixture"}
                        )
                        if runtime_mode == "fixture"
                        else str(profile_records[actor_id]["ownership_marker"])
                    ),
                    "token_hash": (
                        ""
                        if runtime_mode == "fixture"
                        else token_hash(str(profile_records[actor_id]["world_token"]))
                    ),
                }
            )
            self._queue_wake(run_id, actor_id, CrisisWakeType.ORIENT, 0)
        return {"run": run, "lifetimes": self.db.worldline_lifetimes(run_id)}

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

    def human_decision_state(self, run_id: str, tick: int | None = None) -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS":
            raise CrisisRunError("Run not found")
        current_tick = int(run["current_tick"] if tick is None else tick)
        decision_wake = next(
            (
                wake
                for wake in self.db.crisis_wakes(run_id, tick=current_tick)
                if wake["actor_id"] == "wu-sangui"
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
            and event["seat_id"] == "wu-sangui"
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
        controllers = self._controller_map(run_id)
        human_actors = [actor_id for actor_id, controller in controllers.items() if controller == "HUMAN"]
        if human_actors != ["wu-sangui"]:
            raise CrisisRunError("this Run has no Human decision desk")
        tick = int(run["current_tick"])
        if self.human_decision_state(run_id, tick)["state"] != "NONE":
            raise self._human_decision_conflict(run_id, tick)
        if not text.strip():
            snapshot = self.db.worldline_snapshot(run_id)
            if snapshot is None:
                raise CrisisRunError("Run snapshot is missing")
            lifetime = self.db.worldline_lifetime(run_id, "wu-sangui")
            if lifetime is None:
                raise CrisisRunError("Human life state is missing")
            try:
                wake = self.db.create_crisis_wake(
                    {
                        "worldline_id": run_id,
                        "actor_id": "wu-sangui",
                        "wake_type": "DECISION",
                        "tick": tick,
                        "status": "RUNNING",
                        "source": "human",
                        "hermes_session_id": f"human-{uuid.uuid4().hex[:12]}",
                        "frozen_perspective": self._perspective_from(
                            run_id, "wu-sangui", snapshot["projection"]
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
                    {"visibility": ["wu-sangui"]},
                    seat_id="wu-sangui",
                )
                commitments = list(lifetime["commitments"])
                fulfilled_events = self._resolve_human_commitments(
                    run_id,
                    tick,
                    commitments,
                    event["id"],
                )
                self.db.commit_worldline_moment(
                    run_id,
                    [event, *fulfilled_events],
                    current_tick=tick,
                    lifetime_updates=[
                        {
                            "seat": "wu-sangui",
                            "commitments_json": json.dumps(
                                commitments, ensure_ascii=False, sort_keys=True
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
            return {"silence": True, "events": [event, *fulfilled_events], "operations": []}

        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        perspective = self._perspective_from(run_id, "wu-sangui", projection)
        try:
            wake = self.db.create_crisis_wake(
                {
                    "worldline_id": run_id,
                    "actor_id": "wu-sangui",
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
            ModelDecisionInterpreter(self.config)
            if run["runtime_mode"] == "live"
            else FixtureDecisionInterpreter()
        )
        try:
            interpretation = selected.interpret(text.strip(), perspective)
            world = self.world.human_session(wake["id"], "wu-sangui")
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
            )
        except Exception as exc:
            self.db.update_crisis_wake(
                wake["id"], status="FAILED", error={"type": type(exc).__name__}
            )
            raise CrisisRunError("Human decision could not be safely applied") from exc
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
        if tool == "act":
            return world.act(**values)
        if tool == "update_plan":
            return world.update_plan(**values)
        if tool == "schedule_followup":
            return world.schedule_followup(**values)
        raise CrisisRunError(f"unsupported decision operation: {tool}")

    def _commit_human_wake(
        self,
        run_id: str,
        tick: int,
        projection: dict[str, Any],
        wake: dict[str, Any],
        summary: str,
        source: str,
    ) -> list[dict[str, Any]]:
        lifetime = self.db.worldline_lifetime(run_id, "wu-sangui")
        if lifetime is None:
            raise CrisisRunError("Human life state is missing")
        state = {
            "plan": list(lifetime["plan"]),
            "beliefs": dict(lifetime["beliefs"]),
            "commitments": list(lifetime["commitments"]),
        }
        decision_event = self._event(
            run_id,
            tick,
            "HUMAN_DECISION_APPLIED",
            {
                "summary": summary,
                "interpreter_source": source,
                "operation_count": len(self.db.crisis_wake_operations(wake["id"])),
                "visibility": ["wu-sangui"],
            },
            seat_id="wu-sangui",
        )
        events: list[dict[str, Any]] = [decision_event]
        events.extend(
            self._resolve_human_commitments(
                run_id,
                tick,
                state["commitments"],
                decision_event["id"],
            )
        )
        queued_wakes: list[dict[str, Any]] = []
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
                            "visibility": ["wu-sangui"],
                        },
                        seat_id="wu-sangui",
                        causal_parent_ids=[decision_event["id"]],
                    )
                )
                continue
            events.append(
                self._event(
                    run_id,
                    tick,
                    "HUMAN_REQUEST_INTERPRETED",
                    {"tool": operation["tool_name"], "visibility": ["wu-sangui"]},
                    seat_id="wu-sangui",
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
                source="human",
                causal_parent_id=causal_parent_id,
            )
        projection["tick"] = tick
        perspective = self._perspective_from(
            run_id,
            "wu-sangui",
            projection,
            beliefs=state["beliefs"],
            plan=state["plan"],
            commitments=state["commitments"],
        )
        self.db.commit_worldline_moment(
            run_id,
            events,
            current_tick=tick,
            lifetime_updates=[
                {
                    "seat": "wu-sangui",
                    "belief_json": json.dumps(state["beliefs"], ensure_ascii=False, sort_keys=True),
                    "plan_json": json.dumps(state["plan"], ensure_ascii=False, sort_keys=True),
                    "commitments_json": json.dumps(
                        state["commitments"], ensure_ascii=False, sort_keys=True
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
        self.db.update_crisis_wake(
            wake["id"], status="COMPLETED", result={"summary": summary}
        )
        for item in queued_wakes:
            self._queue_wake(**item)
        return events

    def _resolve_human_commitments(
        self,
        run_id: str,
        tick: int,
        commitments: list[dict[str, Any]],
        decision_event_id: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for commitment in commitments:
            if commitment["status"] != "DUE":
                continue
            commitment["status"] = "FULFILLED"
            parents = [decision_event_id]
            if commitment.get("event_id"):
                parents.insert(0, commitment["event_id"])
            events.append(
                self._event(
                    run_id,
                    tick,
                    "COMMITMENT_FULFILLED",
                    {
                        "commitment_id": commitment["id"],
                        "visibility": ["wu-sangui"],
                    },
                    seat_id="wu-sangui",
                    causal_parent_ids=parents,
                )
            )
        return events

    def advance_one(self, run_id: str) -> bool:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
        next_tick = self._next_tick(run_id)
        if next_tick is None:
            return False
        if next_tick >= self.pack.crisis.simulation_boundary.maximum_tick:
            return False
        snapshot = self.db.worldline_snapshot(run_id)
        if snapshot is None:
            raise CrisisRunError("Run snapshot is missing")
        projection = copy.deepcopy(snapshot["projection"])
        if self._movements_due(projection, next_tick):
            self._commit_movements(run_id, next_tick, projection)
            return True
        if self._deliveries_due(projection, next_tick):
            self._commit_deliveries(run_id, next_tick, projection)
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
            commitments = list(lifetime["commitments"])
            for commitment in commitments:
                if commitment["status"] == "PENDING" and int(commitment["due_tick"]) == tick:
                    commitment["status"] = "DUE"
            perspective = self._perspective_from(
                run_id,
                actor_id,
                projection,
                commitments=commitments,
            )
            updates.append(
                {
                    "seat": actor_id,
                    "commitments_json": json.dumps(
                        commitments, ensure_ascii=False, sort_keys=True
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
            int(movement["arrival_tick"])
            for movement in snapshot["projection"].get("movements", [])
            if movement["status"] == "in_transit"
        )
        return min(candidates) if candidates else None

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
            controller = self._controller_map(run_id)[recipient]
            if controller == "AGENT":
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
        for wake in wakes:
            perspective = self._perspective_from(run_id, wake["actor_id"], projection)
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
                    "commitments": list(lifetime["commitments"]),
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
            if wake["wake_type"] == CrisisWakeType.COMMITMENT_DUE.value:
                for commitment in state["commitments"]:
                    if int(commitment["due_tick"]) == tick and commitment["status"] == "PENDING":
                        commitment["status"] = "FULFILLED"
                        events.append(
                            self._event(
                                run_id,
                                tick,
                                "COMMITMENT_FULFILLED",
                                {"wake_id": wake["id"], "commitment_id": commitment["id"]},
                                seat_id=wake["actor_id"],
                                causal_parent_ids=[commitment["event_id"]]
                                if commitment.get("event_id")
                                else [],
                            )
                        )
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
                    causal_parent_id=causal_parent_id,
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
                commitments=state["commitments"],
            )
            lifetime_updates.append(
                {
                    "seat": actor_id,
                    "belief_json": json.dumps(state["beliefs"], ensure_ascii=False, sort_keys=True),
                    "plan_json": json.dumps(state["plan"], ensure_ascii=False, sort_keys=True),
                    "commitments_json": json.dumps(
                        state["commitments"], ensure_ascii=False, sort_keys=True
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
        source: str | None = None,
        causal_parent_id: str = "",
    ) -> str:
        actor_id = wake["actor_id"]
        payload = operation["payload"]
        result = operation["result"]
        tool_name = operation["tool_name"]
        if tool_name == "update_plan":
            previous_objective = state["plan"][0]["objective"] if state["plan"] else ""
            state["plan"] = [
                {
                    "version": result["plan_version"],
                    "objective": payload["objective"],
                    "steps": payload["steps"],
                    "rationale": payload["rationale"],
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
            reflection_tick = tick + 1
            if (
                wake["wake_type"]
                in {CrisisWakeType.MESSAGE.value, CrisisWakeType.OBSERVATION.value}
                and previous_objective
                and previous_objective != payload["objective"]
                and reflection_tick
                < int(self.pack.crisis.simulation_boundary.maximum_tick)
                and not any(
                    item["actor_id"] == actor_id
                    and item["wake_type"] == CrisisWakeType.REFLECTION
                    and item["tick"] == reflection_tick
                    for item in queued_wakes
                )
            ):
                queued_wakes.append(
                    {
                        "run_id": run_id,
                        "actor_id": actor_id,
                        "wake_type": CrisisWakeType.REFLECTION,
                        "tick": reflection_tick,
                        "trigger_event_id": plan_event["id"],
                    }
                )
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
        elif tool_name == "schedule_followup":
            commitment = {
                "id": result["commitment_id"],
                "purpose": payload["purpose"],
                "created_tick": tick,
                "due_tick": result["due_tick"],
                "status": "PENDING",
            }
            state["commitments"].append(commitment)
            event = self._event(
                run_id,
                tick,
                "COMMITMENT_SCHEDULED",
                {"wake_id": wake["id"], "commitment": commitment, "visibility": [actor_id]},
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            commitment["event_id"] = event["id"]
            events.append(event)
            queued_wakes.append(
                {
                    "run_id": run_id,
                    "actor_id": actor_id,
                    "wake_type": CrisisWakeType.COMMITMENT_DUE,
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
        elif tool_name == "act":
            event_type = "ACTOR_ACTION_RECORDED"
            if payload["action"] == "move":
                movement = {
                    "id": result["movement_id"],
                    "actor_id": actor_id,
                    "from": projection["positions"][actor_id],
                    "to": payload["target"],
                    "started_tick": tick,
                    "arrival_tick": result["arrival_tick"],
                    "status": "in_transit",
                }
                projection["movements"].append(movement)
                event_type = "MOVEMENT_STARTED"
            action_event = self._event(
                run_id,
                tick,
                event_type,
                {
                    "wake_id": wake["id"],
                    "request": payload,
                    "result": result,
                    "visibility": [actor_id],
                },
                seat_id=actor_id,
                causal_parent_ids=[causal_parent_id] if causal_parent_id else [],
            )
            if payload["action"] == "move":
                movement["start_event_id"] = action_event["id"]
            events.append(action_event)
            return action_event["id"]
        return plan_event["id"]

    def _perspective_from(
        self,
        run_id: str,
        actor_id: str,
        projection: dict[str, Any],
        *,
        knowledge: list[Any] | None = None,
        beliefs: dict[str, Any] | None = None,
        plan: list[Any] | None = None,
        commitments: list[Any] | None = None,
    ) -> dict[str, Any]:
        lifetime = self.db.worldline_lifetime(run_id, actor_id)
        if lifetime is None:
            raise CrisisRunError("actor life state is missing")
        known = list(lifetime["knowledge"] if knowledge is None else knowledge)
        return {
            "run_id": run_id,
            "actor_id": actor_id,
            "tick": int(projection["tick"]),
            "location": projection["positions"][actor_id],
            "knowledge": known,
            "beliefs": dict(lifetime["beliefs"] if beliefs is None else beliefs),
            "plan": list(lifetime["plan"] if plan is None else plan),
            "commitments": list(
                lifetime["commitments"] if commitments is None else commitments
            ),
            "resources": dict(lifetime["resources"]),
            "authority": list(lifetime["authority"]),
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
        return {
            "id": run_id,
            "mode": "TAKEOVER" if "HUMAN" in controllers.values() else "WATCH",
            "status": run["status"],
            "current_tick": int(run["current_tick"]),
            "maximum_tick": json.loads(run["simulation_boundary_json"])["maximum_tick"],
            "runtime_mode": run["runtime_mode"],
            "human_actor": next(
                (actor_id for actor_id, controller in controllers.items() if controller == "HUMAN"),
                None,
            ),
            "human_decision": self.human_decision_state(run_id, int(run["current_tick"])),
            "created_at": run["created_at"],
            "seal_reason": run["seal_reason"],
        }

    def world_view(self, run_id: str) -> dict[str, Any]:
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
            "boundary": self.pack.crisis.simulation_boundary.model_dump(mode="json"),
        }

    def product_perspective(self, run_id: str, actor_id: str) -> dict[str, Any]:
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
                    {"text": str(item["observation"]), "evidence_status": "observed"}
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
                    }
                )
            elif event["event_type"] == "HUMAN_SILENCE":
                decisions.append(
                    {"tick": int(event["tick"]), "summary": "暂不追加命令，继续观察。"}
                )
        return {
            "actor": {"id": actor.id, "display_name": actor.display_name},
            "tick": perspective["tick"],
            "location": perspective["location"],
            "knowledge": perspective["knowledge"],
            "beliefs": perspective["beliefs"],
            "plan": perspective["plan"],
            "commitments": perspective["commitments"],
            "resources": perspective["resources"],
            "known_situation": known_situation,
            "outgoing_messages": [
                message
                for message in snapshot["projection"].get("messages", [])
                if message["sender"] == actor_id
            ],
            "decisions": decisions,
            "role_charter": actor.role_charter.model_dump(mode="json"),
        }

    def seal(self, run_id: str, reason: str = "user_exit") -> dict[str, Any]:
        run = self.db.worldline(run_id)
        if run is None or run["kind"] != "CRISIS" or run["status"] != "ACTIVE":
            raise CrisisRunError("Run is not active")
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
        )
        self.db.revoke_agent_bindings(run_id)
        return self.run_summary(run_id)

    def replay(self, run_id: str) -> dict[str, Any]:
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
            "COMMITMENT_SCHEDULED": "有人决定稍后再作判断",
            "COMMITMENT_FULFILLED": "一次约定的复查已经发生",
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
        return {"type": wake["wake_type"], "event_id": event["id"]}

    def _controller_map(self, run_id: str) -> dict[str, str]:
        run = self.db.worldline(run_id)
        if run is None:
            raise CrisisRunError("Run not found")
        return json.loads(run["controller_map_json"])

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

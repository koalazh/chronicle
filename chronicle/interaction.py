from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ActionType, ActionValidation, BranchAction, InteractionResult, SeatContextView
from .scenario import ScenarioPack


@dataclass(frozen=True)
class CompiledInput:
    kind: str
    answer: str = ""
    actions: tuple[BranchAction, ...] = ()
    status: ActionValidation | None = None
    unrecognized_segments: tuple[str, ...] = ()


class IntentCompiler:
    """A small Entry-local semantic compiler, not a planner or world simulator."""

    def compile(self, text: str, context: SeatContextView, pack: ScenarioPack) -> CompiledInput:
        content = text.strip()
        if not content:
            return CompiledInput("intent", status=ActionValidation.AMBIGUOUS)
        if self._looks_unsupported(content):
            return CompiledInput("intent", status=ActionValidation.UNSUPPORTED)

        has_question = any(mark in content for mark in ("？", "?")) or any(
            word in content
            for word in (
                "哪里",
                "是否",
                "能否",
                "有没有",
                "知道什么",
                "到哪",
                "有什么",
                "有哪些",
                "哪些消息",
                "收到过哪些",
                "收到哪些",
                "收到了什么",
                "收到什么",
                "消息有哪些",
            )
        )
        if has_question and self._looks_like_pure_inquiry(content):
            return CompiledInput("inquiry", answer=self.answer_inquiry(content, context))
        actions, unrecognized_segments = self._actions_from_text(content)
        if unrecognized_segments:
            return CompiledInput(
                "mixed" if actions else "intent",
                actions=actions,
                status=ActionValidation.AMBIGUOUS,
                unrecognized_segments=unrecognized_segments,
            )
        if not actions and has_question:
            return CompiledInput("inquiry", answer=self.answer_inquiry(content, context))
        if not actions:
            return CompiledInput("intent", status=ActionValidation.AMBIGUOUS)
        if has_question:
            return CompiledInput(
                "mixed", answer=self.answer_inquiry(content, context), actions=actions
            )
        return CompiledInput("intent", actions=actions)

    def answer_inquiry(self, text: str, context: SeatContextView) -> str:
        reached = context.what_reached_you
        if not reached:
            return "目前没有新的已送达消息。你只能依据已经携带的经历和权限行动。"
        if any(word in text for word in ("命令", "订单", "承诺")):
            orders = context.what_you_carry.get("open_orders", [])
            if orders:
                return "目前能确认的未决命令：" + "；".join(
                    str(item.get("payload", "一项未决命令")) for item in orders
                )
            return "目前没有能在这条经历中确认的未决命令。"
        latest = reached[-1]
        payload = str(latest.get("payload", "")).strip()
        return f"你最近收到的消息是：{payload}" if payload else "最近收到了一条消息，但内容不足以形成更具体的判断。"

    @staticmethod
    def _looks_unsupported(text: str) -> bool:
        return any(
            word in text
            for word in (
                "发动大战",
                "决战",
                "模拟战役",
                "改写历史",
                "建立新经济",
                "安排一场大会战",
                "召唤",
                "临时创建",
            )
        )

    @staticmethod
    def _looks_like_pure_inquiry(text: str) -> bool:
        return IntentCompiler._action_from_text(text) is None

    @classmethod
    def _actions_from_text(cls, text: str) -> tuple[tuple[BranchAction, ...], tuple[str, ...]]:
        segments = re.split(r"(?:同时|然后|并且|以及|再)", text)
        candidates = [cls._action_from_text(segment) for segment in segments]
        actions: list[BranchAction] = []
        unrecognized: list[str] = []
        seen: set[tuple[str, str, str, str]] = set()
        for segment, action in zip(segments, candidates, strict=True):
            if action is None:
                if segment.strip():
                    unrecognized.append(segment.strip())
                continue
            key = (action.type.value, action.target, action.recipient, action.payload)
            if key not in seen:
                actions.append(action)
                seen.add(key)
        if not actions:
            action = cls._action_from_text(text)
            if action is not None:
                actions.append(action)
                unrecognized.clear()
        return tuple(actions), tuple(unrecognized)

    @staticmethod
    def _action_from_text(text: str) -> BranchAction | None:
        recipient_markers = ("吴三桂", "东部", "关宁", "山海关")
        if any(word in text for word in ("传信", "传达", "通知", "催", "告知", "发消息", "发信", "写信", "送信", "回信", "转告", "联络", "联系")) or (
            "发给" in text and any(word in text for word in recipient_markers)
        ):
            recipient = "C" if any(word in text for word in recipient_markers) else "B"
            return BranchAction(
                type=ActionType.SEND_MESSAGE,
                recipient=recipient,
                payload=text,
                priority="urgent" if any(word in text for word in ("尽快", "紧急", "立即")) else "normal",
            )
        if any(word in text for word in ("命令", "下令", "下达", "指示", "令")):
            return BranchAction(
                type=ActionType.ISSUE_ORDER,
                target="capital",
                payload=text,
                priority="urgent" if any(word in text for word in ("尽快", "紧急", "立即")) else "normal",
            )
        if any(word in text for word in ("任命", "授权", "委任")):
            return BranchAction(type=ActionType.APPOINT_AUTHORITY, target="southern_command", payload=text)
        if any(word in text for word in ("准备移动", "准备南下", "准备出动", "准备调动", "准备调兵")):
            return BranchAction(type=ActionType.PREPARE_MOVEMENT, target="capital", payload=text)
        if any(word in text for word in ("亲自南下", "送太子", "移动主位", "移驾", "亲自前往")):
            return BranchAction(type=ActionType.MOVE_PRINCIPAL, target="southern_command", payload=text)
        if any(word in text for word in ("调动", "重新部署", "调兵", "部署兵力", "调兵遣将")):
            return BranchAction(type=ActionType.REDEPLOY_FORCE, target="capital", payload=text)
        if any(word in text for word in ("不要公开", "不公开", "暂不公开", "公开")):
            value = "private" if any(word in text for word in ("不要公开", "不公开", "暂不公开")) else "public"
            return BranchAction(type=ActionType.SET_DISCLOSURE, target="southern_proposal", payload=value)
        if any(word in text for word in ("询问", "问问", "查明", "打听", "了解", "探听", "询查", "核实")):
            return BranchAction(type=ActionType.REQUEST_INFORMATION, target="capital", payload=text)
        if any(word in text for word in ("等待", "先等", "暂缓", "等一下", "稍等", "先不动", "观望")):
            return BranchAction(type=ActionType.WAIT, payload=text)
        return None


def interaction_to_model(compiled: CompiledInput) -> InteractionResult:
    return InteractionResult(
        kind=compiled.kind,
        answer=compiled.answer,
        interpreted_actions=list(compiled.actions),
        status=compiled.status,
    )

from __future__ import annotations

import json
from typing import Any, Literal, Protocol

import httpx
from pydantic import Field

from .config import AppConfig
from .models import StrictModel


class DecisionInterpretationError(ValueError):
    """A Human decision could not be safely translated into World requests."""


class DecisionOperation(StrictModel):
    tool: Literal["communicate", "investigate", "operate", "update_plan", "schedule_revisit"]
    arguments: dict[str, Any]


class InterpretedDecision(StrictModel):
    summary: str = Field(max_length=1200)
    operations: list[DecisionOperation] = Field(max_length=8)


class DecisionInterpreter(Protocol):
    source: str

    def interpret(
        self,
        text: str,
        perspective: dict[str, Any],
    ) -> InterpretedDecision: ...


class FixtureDecisionInterpreter:
    """Explicit deterministic test double; never used by a live Run."""

    source = "fixture"

    def interpret(self, text: str, perspective: dict[str, Any]) -> InterpretedDecision:
        operations: list[DecisionOperation] = [
            DecisionOperation(
                tool="update_plan",
                arguments={
                    "objective": text.strip(),
                    "steps": ["先以书面条件试探", "保留关口的有限应急准备"],
                    "rationale": "这是 Human 输入的确定性 fixture 解释，不代表 live 模型结果。",
                },
            )
        ]
        if "关外" in text or "多尔衮" in text:
            operations.append(
                DecisionOperation(
                    tool="communicate",
                    arguments={
                        "recipient": "dorgon",
                        "content": text.strip(),
                    },
                )
            )
        if "两日" in text:
            operations.append(
                DecisionOperation(
                    tool="schedule_revisit",
                    arguments={"after_days": 2, "reason": "两日后重新比较两方回应"},
                )
            )
        if "调查" in text or "查问" in text or "打听" in text:
            investigation = next(
                iter(perspective.get("available_investigations", [])),
                None,
            )
            if investigation:
                operations.append(
                    DecisionOperation(
                        tool="investigate",
                        arguments={
                            "question": text.strip(),
                            "target": investigation["target"]["id"],
                            "method": investigation["method"],
                        },
                    )
                )
        if "整备" in text or "准备兵力" in text:
            prepare = next(
                (
                    item
                    for item in perspective.get("available_operations", [])
                    if item.get("id") == "prepare_force"
                ),
                None,
            )
            prepare_targets = prepare.get("targets", []) if prepare else []
            force_options = prepare_targets[0].get("options", []) if prepare_targets else []
            if force_options:
                operations.append(
                    DecisionOperation(
                        tool="operate",
                        arguments={
                            "operation_definition_id": "prepare_force",
                            "targets": [force_options[0]["id"]],
                            "description": "开始整备可用兵力。",
                        },
                    )
                )
        return InterpretedDecision(summary="已把这项决定解释为有限的危局请求。", operations=operations)


class ModelDecisionInterpreter:
    """Use the configured Provider for semantic, multi-operation interpretation."""

    source = "model"

    def __init__(
        self,
        config: AppConfig,
        *,
        recipient_catalog: tuple[dict[str, str], ...] = (),
    ):
        self.config = config
        self.recipient_catalog = recipient_catalog

    def interpret(self, text: str, perspective: dict[str, Any]) -> InterpretedDecision:
        if not self.config.llm_configured:
            raise DecisionInterpretationError("Provider is not configured")
        recipient_rule = (
            "communicate 的 recipient 必须使用以下 canonical actor ID，不得使用显示名或别名："
            + "；".join(
                f"{item['id']}（{item['display_name']}）" for item in self.recipient_catalog
            )
            + "。"
            if self.recipient_catalog
            else "communicate 的 recipient 必须使用 canonical actor ID，不得使用显示名或别名。"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Chronicle 的 Human Decision Interpreter，不是历史主体，也不决定世界结果。"
                    "把用户一句自然语言决定解释成 0 到 8 个 World Affordance 请求。"
                    "只可使用 communicate、investigate、operate、update_plan、schedule_revisit。"
                    "不得伪造 actor_id/run_id/wake_id，不得加入用户没有表达的不可逆选择。"
                    "返回严格 JSON：{summary:string,operations:[{tool:string,arguments:object}]}。"
                    f"communicate 参数 recipient/content；{recipient_rule}"
                    "investigate 参数 question/target/method；"
                    "target 与 method 必须从 private_perspective.available_investigations 选择；"
                    "operate 参数 operation_definition_id/targets/description；"
                    "operation_definition_id 与 targets 必须从 private_perspective.available_operations 选择；"
                    "update_plan 参数 objective/steps/rationale/belief_updates/reconsider_when；"
                    "schedule_revisit 参数 after_days/reason。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"decision": text, "private_perspective": perspective},
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            if self.config.llm_api_mode == "responses":
                response = httpx.post(
                    f"{self.config.llm_base_url}/responses",
                    headers=self._headers(),
                    json={
                        "model": self.config.llm_model,
                        "input": messages,
                        "store": False,
                    },
                    timeout=self.config.llm_timeout,
                    trust_env=False,
                )
            else:
                response = httpx.post(
                    f"{self.config.llm_base_url}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": self.config.llm_model,
                        "messages": messages,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self.config.llm_timeout,
                    trust_env=False,
                )
            response.raise_for_status()
            text_output = self._response_text(response.json())
            cleaned = text_output.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return InterpretedDecision.model_validate_json(cleaned.strip())
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise DecisionInterpretationError("Provider returned no valid decision operations") from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.llm_api_key}",
            "Content-Type": "application/json",
        }

    def _response_text(self, body: dict[str, Any]) -> str:
        if self.config.llm_api_mode == "responses":
            parts: list[str] = []
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        parts.append(str(content.get("text", "")))
            return "".join(parts)
        choices = body.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        return ""

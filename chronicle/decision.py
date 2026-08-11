from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

import httpx
from pydantic import Field

from .config import AppConfig
from .models import StrictModel


class DecisionInterpretationError(ValueError):
    """A Human decision could not be safely translated into World requests."""


class DecisionOperation(StrictModel):
    tool: Literal[
        "communicate",
        "investigate",
        "manage_offer",
        "operate",
        "update_plan",
        "schedule_revisit",
    ]
    arguments: dict[str, Any]


class InterpretedDecision(StrictModel):
    summary: str = Field(max_length=1200)
    operations: list[DecisionOperation] = Field(max_length=8)


def guard_human_interpretation(text: str, decision: InterpretedDecision) -> InterpretedDecision:
    """Remove model-inferred psychology that the Human did not state."""

    reason_markers = ("因为", "由于", "考虑到", "担心", "为了", "所以")
    belief_markers = (
        "相信",
        "不信",
        "怀疑",
        "判断",
        "认为",
        "不确定",
        "确信",
        "担心",
    )
    explicit_reason = any(marker in text for marker in reason_markers)
    explicit_belief = any(marker in text for marker in belief_markers)
    operations: list[DecisionOperation] = []
    for operation in decision.operations:
        arguments = dict(operation.arguments)
        if operation.tool == "update_plan":
            rationale = str(arguments.get("rationale", "")).strip()
            if not rationale or not explicit_reason or not _shares_phrase(text, rationale):
                arguments["rationale"] = ""
                arguments["rationale_source"] = "unstated"
            else:
                arguments["rationale_source"] = "explicit"
            beliefs = arguments.get("belief_updates", [])
            if not explicit_belief:
                arguments["belief_updates"] = []
                arguments["belief_source"] = "unstated"
            else:
                arguments["belief_updates"] = [
                    item
                    for item in beliefs
                    if isinstance(item, dict)
                    and _shares_phrase(text, str(item.get("assessment", "")))
                ]
                arguments["belief_source"] = "explicit"
        operations.append(DecisionOperation(tool=operation.tool, arguments=arguments))
    return InterpretedDecision(summary=decision.summary, operations=operations)


def _shares_phrase(text: str, candidate: str) -> bool:
    if not text.strip() or not candidate.strip():
        return False
    text_folded = text.casefold()
    candidate_folded = candidate.casefold()
    if candidate_folded in text_folded:
        return True
    terms = re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]{2,}", text_folded)
    return any(term in candidate_folded for term in terms if len(term) >= 2)


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
                    "steps": ["先以书面条件核验", "保留仍可执行的行动"],
                    "rationale": "这是 Human 输入的确定性 fixture 解释，不代表 live 模型结果。",
                },
            )
        ]
        contacts = sorted(
            str(contact.get("id", ""))
            for contact in perspective.get("contactable_actors", [])
            if str(contact.get("id", ""))
        )
        if contacts and any(term in text for term in ("说明", "致信", "通信", "来信")):
            operations.append(
                DecisionOperation(
                    tool="communicate",
                    arguments={"recipient": contacts[0], "content": text.strip()},
                )
            )
        if "两日" in text:
            operations.append(
                DecisionOperation(
                    tool="schedule_revisit",
                    arguments={"after_days": 2, "reason": "两日后重新判断已知条件"},
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
        offer_term = next(iter(perspective.get("available_offer_terms", [])), None)
        if offer_term and any(term in text for term in ("通行", "放行")):
            operations.append(
                DecisionOperation(
                    tool="manage_offer",
                    arguments={
                        "action": "PROPOSE",
                        "recipient": offer_term["recipient"]["id"],
                        "terms": [
                            {
                                "type": offer_term["type"],
                                "subject": offer_term["subject"]["id"],
                                "value": offer_term["value"],
                                "description": offer_term["description"],
                            }
                        ],
                        "message": text.strip(),
                    },
                )
            )
        incoming_offer = next(
            (
                offer
                for offer in perspective.get("active_offers", [])
                if offer.get("recipient") == perspective.get("actor_id")
            ),
            None,
        )
        if incoming_offer and any(term in text for term in ("接受", "同意")):
            operations.append(
                DecisionOperation(
                    tool="manage_offer",
                    arguments={"action": "ACCEPT", "offer_id": incoming_offer["id"]},
                )
            )
        if "整备" in text or "准备" in text:
            operation = next(
                (
                    item
                    for item in perspective.get("available_operations", [])
                    if "整备" in str(item.get("display_name", ""))
                    or "整备" in str(item.get("description", ""))
                ),
                None,
            )
            if operation is not None:
                targets = [
                    target["options"][0]["id"]
                    for target in operation.get("targets", [])
                    if target.get("options")
                ]
                operations.append(
                    DecisionOperation(
                        tool="operate",
                        arguments={
                            "operation_definition_id": operation["id"],
                            "targets": targets,
                            "description": "开始执行当前可用的整备行动。",
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
                    "只可使用 communicate、investigate、manage_offer、operate、update_plan、schedule_revisit。"
                    "不得伪造 actor_id/run_id/wake_id，不得加入用户没有表达的不可逆选择。"
                    "返回严格 JSON：{summary:string,operations:[{tool:string,arguments:object}]}。"
                    f"communicate 参数 recipient/content；{recipient_rule}"
                    "investigate 参数 question/target/method；"
                    "target 与 method 必须从 private_perspective.available_investigations 选择；"
                    "manage_offer 参数 action/offer_id/recipient/terms/message/expires_after_days；"
                    "PROPOSE 或 COUNTER 的 terms 必须从 private_perspective.available_offer_terms 选择；"
                    "ACCEPT、REJECT、WITHDRAW 的 offer_id 必须从 private_perspective.active_offers 选择；"
                    "operate 参数 operation_definition_id/targets/description；"
                    "operation_definition_id 与 targets 必须从 private_perspective.available_operations 选择；"
                    "update_plan 参数 objective/steps/rationale/belief_updates/reconsider_when；"
                    "rationale 只能复述用户明确说出的理由，未明确说明时必须为空；"
                    "belief_updates 只能记录用户明确表达的相信、不信、判断或怀疑，不能从行动反推心理；"
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

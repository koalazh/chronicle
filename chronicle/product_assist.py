from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Literal

import httpx

from .config import AppConfig
from .deliberation import DELIBERATION_WORLD_TOOLS

DraftStage = Literal["FIRST", "REOPEN"]
_RECOMMENDATIONS = {
    "FIRST": frozenset({"CHANGE", "WAIT"}),
    "REOPEN": frozenset({"KEEP", "CHANGE"}),
}
_DRAFT_LIMIT = 1000
_BASIS_LIMIT = 8
_DISALLOWED_DRAFT = re.compile(
    r"(?:worldline-|lifetime-|wake:|entity-|operation-|investigation-|"
    r"\b(?:worldline|lifetime|wake|entity_id|operation_id|tool_id)\b|"
    r"\b(?:arrange|调用|工具|最佳|正确历史|唯一正确)\b)",
    re.IGNORECASE,
)


def _provider_endpoint(config: AppConfig) -> str:
    base_url = config.llm_base_url.rstrip("/")
    suffix = "/responses" if config.llm_api_mode == "responses" else "/chat/completions"
    return f"{base_url}{suffix}" if base_url.endswith("/v1") else f"{base_url}/v1{suffix}"


def _headers(config: AppConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.llm_api_key:
        headers["Authorization"] = f"Bearer {config.llm_api_key}"
    return headers


def _system_prompt(stage: DraftStage) -> str:
    allowed = "CHANGE 或 WAIT" if stage == "FIRST" else "KEEP 或 CHANGE"
    return f"""你只帮助用户为当前这一刻起草一份可修改的判断，不替用户决定，也不调用工具。
只根据用户收到的 bounded context 写一份 judgment-level 草稿。不要补写后世知识，不要宣称最佳、正确历史或唯一答案，不要写工具、系统操作、内部 id 或其他人的秘密计划。
recommendation 只能是 {allowed}。
只返回一个 JSON object，不要 Markdown，不要解释。字段必须是：recommendation（字符串）、draft（字符串）、basis_event_ids（字符串数组）。basis_event_ids 只能从输入中的 visible_evidence.event_id 选择；没有合适依据时返回空数组。"""


def _response_text(body: Any, api_mode: str) -> str:
    if not isinstance(body, dict):
        return ""
    if api_mode == "responses":
        output_text = body.get("output_text")
        if isinstance(output_text, str):
            return output_text
        parts: list[str] = []
        for item in body.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    parts.append(str(content.get("text", "")))
        return "".join(parts)
    choices = body.get("choices", [])
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    return ""


def _parse_json(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        value = json.loads(candidate)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _complete_json(config: AppConfig, messages: list[dict[str, str]]) -> dict[str, Any] | None:
    payload: dict[str, Any]
    if config.llm_api_mode == "responses":
        payload = {"model": config.llm_model, "input": messages, "store": False}
    else:
        payload = {
            "model": config.llm_model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
        }
    if config.llm_reasoning_effort:
        payload["reasoning_effort"] = config.llm_reasoning_effort
    try:
        response = httpx.post(
            _provider_endpoint(config),
            headers=_headers(config),
            json=payload,
            timeout=config.llm_timeout,
            trust_env=False,
        )
        if not 200 <= response.status_code < 300:
            return None
        return _parse_json(_response_text(response.json(), config.llm_api_mode))
    except Exception:
        return None


def validate_draft_suggestion(
    suggestion: Any,
    *,
    stage: DraftStage,
    visible_event_ids: set[str] | frozenset[str],
) -> dict[str, Any] | None:
    if not isinstance(suggestion, dict):
        return None
    recommendation = str(suggestion.get("recommendation", "")).strip().upper()
    if recommendation not in _RECOMMENDATIONS[stage]:
        return None
    draft = str(suggestion.get("draft", "")).strip()
    if not draft or len(draft) > _DRAFT_LIMIT or _DISALLOWED_DRAFT.search(draft):
        return None
    basis_event_ids = suggestion.get("basis_event_ids")
    if not isinstance(basis_event_ids, list) or len(basis_event_ids) > _BASIS_LIMIT:
        return None
    normalized_basis = [str(item).strip() for item in basis_event_ids]
    if (
        any(not item for item in normalized_basis)
        or len(set(normalized_basis)) != len(normalized_basis)
        or not set(normalized_basis).issubset(visible_event_ids)
    ):
        return None
    return {
        "recommendation": recommendation,
        "draft": draft,
        "basis_event_ids": normalized_basis,
    }


def _event_text(value: dict[str, Any]) -> str:
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else value
    for key in ("content", "observation", "description", "summary", "text", "declaration", "reason"):
        candidate = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            nested = _event_text(candidate)
            if nested:
                return nested
    event_type = str(value.get("event_type", "")).strip()
    return "一项进入所知范围的事实。" if not event_type else "一项新的事实进入所知范围。"


def _bounded_items(values: Any, limit: int = 6) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
        elif isinstance(value, dict):
            text = _event_text(value)
            if text:
                result.append(text)
        if len(result) >= limit:
            break
    return result


def bounded_draft_context(context: dict[str, Any], stage: DraftStage) -> tuple[dict[str, Any], frozenset[str]]:
    """Compile only the actor-scoped frozen context allowed for a draft request."""

    visible_events: list[dict[str, str]] = []
    visible_ids: set[str] = set()

    def add_event(value: Any) -> None:
        if not isinstance(value, dict):
            return
        event_id = str(value.get("event_id", "")).strip()
        if not event_id or event_id in visible_ids:
            return
        visible_ids.add(event_id)
        visible_events.append({"event_id": event_id, "fact": _event_text(value)})

    add_event(context.get("trigger"))
    why_now = context.get("why_now") if isinstance(context.get("why_now"), dict) else {}
    for value in why_now.get("facts", []):
        add_event(value)
    for key in ("relevant_evidence", "recent_knowledge"):
        for value in context.get(key, []):
            if isinstance(value, dict):
                add_event(value)

    course = context.get("current_course")
    bounded_course = None
    if isinstance(course, dict):
        bounded_course = {
            "summary": str(course.get("course") or course.get("objective") or "").strip(),
            "steps": _bounded_items(course.get("steps", []), limit=4),
        }
    position = context.get("position") if isinstance(context.get("position"), dict) else {}
    role = context.get("role") if isinstance(context.get("role"), dict) else {}
    bounded = {
        "stage": stage,
        "tick": int(context.get("tick", 0)),
        "position": {"display_name": str(position.get("display_name", "")).strip()},
        "role": {"display_name": str(role.get("display_name", "")).strip()},
        "current_course": bounded_course,
        "visible_evidence": visible_events[:_BASIS_LIMIT],
        "known_changes": _bounded_items(
            (context.get("since_last_deliberation") or {}).get("facts", [])
            if isinstance(context.get("since_last_deliberation"), dict)
            else [],
        ),
        "known_uncertainty": _bounded_items(context.get("known_uncertainty", [])),
    }
    return bounded, frozenset(visible_ids)


def draft_judgment(config: AppConfig, context: dict[str, Any], stage: DraftStage) -> dict[str, Any] | None:
    if stage not in _RECOMMENDATIONS or not config.llm_configured:
        return None
    bounded, visible_event_ids = bounded_draft_context(context, stage)
    messages = [
        {"role": "system", "content": _system_prompt(stage)},
        {"role": "user", "content": json.dumps(bounded, ensure_ascii=False)},
    ]
    suggestion = _complete_json(config, messages)
    return validate_draft_suggestion(
        suggestion,
        stage=stage,
        visible_event_ids=visible_event_ids,
    )


def _execution_context(context: dict[str, Any], course: dict[str, Any]) -> dict[str, Any]:
    role = context.get("role") if isinstance(context.get("role"), dict) else {}
    position = context.get("position") if isinstance(context.get("position"), dict) else {}
    raw_affordances = context.get("affordances") if isinstance(context.get("affordances"), dict) else {}
    affordances = {
        str(key): deepcopy(value[:6])
        for key, value in raw_affordances.items()
        if isinstance(value, list)
    }
    return {
        "tick": int(context.get("tick", 0)),
        "position": {"display_name": str(position.get("display_name", "")).strip()},
        "role": {
            "display_name": str(role.get("display_name", "")).strip(),
            "authority": [str(item) for item in role.get("authority", []) if str(item)],
        },
        "confirmed_course": {
            "summary": str(course.get("summary") or course.get("course") or "").strip(),
            "steps": [str(item).strip() for item in course.get("steps", []) if str(item).strip()][:4],
        },
        "subject_affordances": affordances,
    }


def _execution_system_prompt() -> str:
    return """Human 已经确认了这个人的方向。你不能重新判断、修改 Course 或生成 beliefs、dependencies、rationale、future plan。
只判断当前 frozen perspective 中已有的合法 subject affordances 是否包含一件与 confirmed_course 一致、值得现在实施的动作。没有清楚动作就返回 null。
只返回一个 JSON object，字段只能是 world_action。world_action 只能是 null，或 {tool, arguments}；tool 必须是 communicate、investigate、manage_offer、operate、schedule_revisit 之一。不要调用工具，不要写解释。"""


def _validate_execution_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != {"world_action"}:
        return None
    action = value.get("world_action")
    if action is None:
        return None
    if not isinstance(action, dict) or set(action) != {"tool", "arguments"}:
        return None
    tool = str(action.get("tool", "")).strip()
    arguments = action.get("arguments")
    if tool not in DELIBERATION_WORLD_TOOLS or not isinstance(arguments, dict):
        return None
    return {"tool": tool, "arguments": deepcopy(arguments)}


def execution_action_candidate(
    config: AppConfig, context: dict[str, Any], course: dict[str, Any]
) -> dict[str, Any] | None:
    """Return at most one non-authoritative action candidate without writing state."""

    if not config.llm_configured:
        return None
    bounded = _execution_context(context, course)
    result = _complete_json(
        config,
        [
            {"role": "system", "content": _execution_system_prompt()},
            {"role": "user", "content": json.dumps(bounded, ensure_ascii=False)},
        ],
    )
    return _validate_execution_candidate(result)

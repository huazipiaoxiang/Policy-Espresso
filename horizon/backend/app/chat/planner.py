"""Planner：一次小模型调用做指代消解与查询改写。

设计要点：Planner 是**可失败的增强**——模型不可达、输出不可解析、mock 模式下，
一律退化为「原问题 + 单条查询」的规则计划，保证 /chat 永远有确定行为。
"""
from __future__ import annotations

from typing import Any

from app.ai.provider import LLMProvider
from app.chat.prompts import PLANNER_SCHEMA, PLANNER_SYSTEM, render_history
from app.chat.schemas import INTENTS, MAX_QUERIES, ChatPlan
from app.core.config import get_settings
from app.core.logging import get_logger
from app.chat.tool_registry import QUERY_MAX

log = get_logger("chat.planner")

# 这两种 provider 不参与规划：mock 是查表式的确定性实现，无法从 prompt 反推用户问题。
NON_PLANNING_PROVIDERS = {"mock"}


def rule_plan(question: str) -> ChatPlan:
    """规则回退计划：不做改写，直接用原问题检索。"""
    return ChatPlan(
        standalone_question=question.strip(),
        intent="lookup",
        queries=[question.strip()[:QUERY_MAX]],
        needs_web=False,
        source="rule",
    )


def _clean_queries(value: Any, fallback: str) -> list[str]:
    if not isinstance(value, list):
        return [fallback[:QUERY_MAX]]
    queries: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split())[:QUERY_MAX]
        if text and text not in queries:
            queries.append(text)
        if len(queries) == MAX_QUERIES:
            break
    return queries or [fallback[:QUERY_MAX]]


def build_plan(
    *,
    provider: LLMProvider,
    question: str,
    history: list[dict[str, Any]] | None = None,
    context: str | None = None,
) -> ChatPlan:
    """生成检索计划。任何异常都退化为规则计划，不向上抛。"""
    question = (question or "").strip()
    settings = get_settings()
    provider_name = str(getattr(provider, "name", "unknown"))
    if not question or not settings.chat_planner_enabled or provider_name in NON_PLANNING_PROVIDERS:
        return rule_plan(question)

    user = (
        f"HISTORY:\n{render_history(history)}\n\n"
        f"PAGE_CONTEXT (not evidence):\n{context or ''}\n\n"
        f"QUESTION:\n{question}"
    )
    try:
        result = provider.complete_messages(
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": user}],
            schema=PLANNER_SCHEMA,
            temperature=0.1,
            max_tokens=400,
            model=settings.model_for_task("chat_plan"),
            task="chat_plan",
        )
    except Exception as exc:  # provider 边界：规划失败不影响主流程
        log.warning("chat_plan_failed", provider=provider_name, error_type=type(exc).__name__)
        return rule_plan(question)

    parsed = result.parsed
    if not isinstance(parsed, dict):
        log.warning("chat_plan_unparsable", provider=provider_name)
        return rule_plan(question)

    standalone = " ".join(str(parsed.get("standalone_question") or "").split())[:QUERY_MAX]
    if not standalone:
        return rule_plan(question)
    intent = str(parsed.get("intent") or "lookup")
    if intent not in INTENTS:
        intent = "lookup"
    return ChatPlan(
        standalone_question=standalone,
        intent=intent,
        queries=_clean_queries(parsed.get("queries"), standalone),
        needs_web=bool(parsed.get("needs_web")),
        source="llm",
    )

"""Chat Agent 执行循环：轮次控制、证据预算、去重、早停与作答。

三段式的中段（Executor）与末段（Responder）：
- Executor 每轮输出「调哪个工具 / 用什么查询词」或「finish」，服务端执行只读检索并把观察回灌；
- Responder 基于累积证据作答，引用按分层规则（事实必带 id，解读可不标）。

所有模型调用失败都退化为规则回退，绝不把异常抛到 API 层。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.ai.provider import LLMProvider
from app.chat.prompts import (
    ANSWER_SCHEMA,
    ANSWER_SYSTEM,
    EXECUTOR_SCHEMA,
    EXECUTOR_SYSTEM,
    render_evidence,
    render_history,
    render_observation,
    render_tool_list,
)
from app.chat.schemas import ANSWER_MODES, MAX_FOLLOWUPS, ChatPlan, ChatStep
from app.chat.tool_registry import clamp_limit, clamp_query, describe_tools, run_tool
from app.chat.tools import ChatEvidence, ChatTools
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("chat.agent")

# 与 Planner 同理：mock 是查表实现，不能驱动多轮循环，走确定性检索。
NON_AGENT_PROVIDERS = {"mock"}
FALLBACK_TOOLS = ("search_policies", "search_documents", "search_semantic")


@dataclass
class AgentRun:
    evidence: list[ChatEvidence] = field(default_factory=list)
    steps: list[ChatStep] = field(default_factory=list)
    stop_reason: str = ""


def _fold(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _add_to_pool(pool: list[ChatEvidence], seen: set[str], items: list[ChatEvidence], limit: int) -> int:
    added = 0
    for item in items:
        if item.key in seen or len(pool) >= limit:
            continue
        seen.add(item.key)
        pool.append(item)
        added += 1
    return added


def _fallback_retrieve(
    tools: ChatTools,
    role: object,
    query: str,
    pool: list[ChatEvidence],
    seen: set[str],
    steps: list[ChatStep],
    limit: int,
    *,
    start_round: int,
) -> None:
    """模型完全没产出有效检索时的保底：按固定顺序试几个工具，任一命中即停。"""
    for offset, tool_name in enumerate(FALLBACK_TOOLS):
        evidence, note = run_tool(tools, role, tool_name, {"query": query})
        added = _add_to_pool(pool, seen, evidence, limit)
        steps.append(ChatStep(round=start_round + offset, tool=tool_name, query=query,
                              hits=added, note=note or "fallback"))
        if added:
            return


def run_agent(
    *,
    tools: ChatTools,
    provider: LLMProvider,
    role: object,
    plan: ChatPlan,
    history: list[dict[str, Any]] | None = None,
    context: str | None = None,
) -> AgentRun:
    """执行多轮工具循环，返回累积证据与可观测步骤。"""
    settings = get_settings()
    max_rounds = max(1, int(settings.chat_max_tool_rounds))
    max_invalid = max(1, int(settings.chat_max_invalid_calls))
    evidence_max = max(1, int(settings.chat_evidence_max))
    provider_name = str(getattr(provider, "name", "unknown"))
    query_seed = plan.standalone_question or (plan.queries[0] if plan.queries else "")

    pool: list[ChatEvidence] = []
    seen: set[str] = set()
    steps: list[ChatStep] = []

    if provider_name in NON_AGENT_PROVIDERS:
        _fallback_retrieve(tools, role, query_seed, pool, seen, steps, evidence_max, start_round=1)
        return AgentRun(evidence=pool, steps=steps, stop_reason="deterministic_provider")

    web_hint = "用户问题需要库外最新信息，可考虑 search_web。\n" if plan.needs_web else ""
    opening = (
        f"{render_tool_list(describe_tools(role, db=tools.db))}\n\n"
        f"HISTORY:\n{render_history(history)}\n\n"
        f"PAGE_CONTEXT (not evidence):\n{context or ''}\n\n"
        f"QUESTION:\n{plan.standalone_question}\n\n"
        f"候选检索词（可直接用或改写）：{json.dumps(plan.queries, ensure_ascii=False)}\n"
        f"{web_hint}现在输出第一步决策的 JSON。"
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": opening}]

    called: set[tuple[str, str]] = set()
    invalid = 0
    stop_reason = "rounds_exhausted"
    model_responded = False  # 模型是否给出过可解析决策：finish 属正常收尾，不该再保底检索

    for round_no in range(1, max_rounds + 1):
        if len(pool) >= evidence_max:
            stop_reason = "evidence_budget"
            break
        try:
            result = provider.complete_messages(
                system=EXECUTOR_SYSTEM,
                messages=messages,
                schema=EXECUTOR_SCHEMA,
                temperature=0.0,
                max_tokens=400,
                model=settings.model_for_task("chat_plan"),
                task="chat_plan",
            )
        except Exception as exc:
            log.warning("chat_agent_step_failed", round=round_no, error_type=type(exc).__name__)
            invalid += 1
            if invalid >= max_invalid:
                stop_reason = "provider_error"
                break
            continue

        parsed = result.parsed if isinstance(result.parsed, dict) else None
        if parsed is None:
            invalid += 1
            log.warning("chat_agent_unparsable", round=round_no, provider=provider_name)
            if invalid >= max_invalid:
                stop_reason = "unparsable_output"
                break
            messages.append({"role": "user", "content": "上一轮输出不是合法 JSON。请只输出一个 JSON 对象，不要解释。"})
            continue

        model_responded = True
        action = str(parsed.get("action") or "")
        if action == "finish":
            stop_reason = "model_finish"
            break
        if action != "call_tool":
            invalid += 1
            if invalid >= max_invalid:
                stop_reason = "invalid_action"
                break
            messages.append({"role": "user", "content": "action 只能是 call_tool 或 finish。请重新输出 JSON。"})
            continue

        tool_name = str(parsed.get("tool") or "").strip()
        query = clamp_query(parsed.get("query") or query_seed)
        limit = clamp_limit(parsed.get("limit"))
        call_key = (tool_name, _fold(query))
        if not query or call_key in called:
            invalid += 1
            steps.append(ChatStep(round=round_no, tool=tool_name or "-", query=query,
                                  hits=0, note="重复调用或空查询，已忽略"))
            if invalid >= max_invalid:
                stop_reason = "repeated_calls"
                break
            messages.append({"role": "user", "content": "该工具同一查询已调用过（或查询为空）。请换工具或改写查询词后重试。"})
            continue

        called.add(call_key)
        evidence, note = run_tool(tools, role, tool_name, {"query": query, "limit": limit})
        added = _add_to_pool(pool, seen, evidence, evidence_max)
        steps.append(ChatStep(round=round_no, tool=tool_name, query=query, hits=added, note=note))
        log.info("chat_agent_step", round=round_no, tool=tool_name, hits=added, pool=len(pool),
                 note=note[:80] if note else "")

        messages.append({"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": (
                f"{render_observation(evidence, note)}\n\n"
                f"已累积 {len(pool)} 条证据（上限 {evidence_max}）。"
                "输出下一步 JSON：继续 call_tool 或 finish。"
            ),
        })
        if added == 0:
            invalid += 1
            if invalid >= max_invalid:
                stop_reason = "no_progress"
                break
        else:
            invalid = 0

    if not steps and not model_responded:
        # 模型一次都没给出可解析决策（异常/输出不是 JSON）：保底检索一次，避免空手作答。
        _fallback_retrieve(tools, role, query_seed, pool, seen, steps, evidence_max, start_round=1)
        stop_reason = stop_reason if steps else "fallback_retrieve"
    return AgentRun(evidence=pool, steps=steps, stop_reason=stop_reason)


def respond(
    *,
    provider: LLMProvider,
    question: str,
    evidence: list[ChatEvidence],
    history: list[dict[str, Any]] | None = None,
    context: str | None = None,
) -> dict[str, Any] | None:
    """调用模型作答。返回原始 parsed dict（校验交给 service），失败返回 None。

    证据为空时**仍然调用模型**——放宽后的规则允许它用通用知识作答（answer_mode=general），
    只是不得编造文号/日期/链接。只有确定性 provider（mock）才跳过。
    """
    provider_name = str(getattr(provider, "name", "unknown"))
    if provider_name in NON_AGENT_PROVIDERS:
        return None
    settings = get_settings()
    user = (
        f"HISTORY:\n{render_history(history)}\n\n"
        f"PAGE_CONTEXT (not evidence):\n{context or ''}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"EVIDENCE JSON:\n{render_evidence(evidence)}"
    )
    try:
        result = provider.complete_messages(
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": user}],
            schema=ANSWER_SCHEMA,
            temperature=0.3,
            max_tokens=1500,
            model=settings.model_for_task("chat_answer"),
            task="chat_answer",
        )
    except Exception as exc:
        log.warning("chat_answer_failed", provider=provider_name, error_type=type(exc).__name__)
        return None
    parsed = result.parsed if isinstance(result.parsed, dict) else None
    if parsed is None:
        log.warning("chat_answer_unparsable", provider=provider_name)
        return None
    parsed["_model"] = result.model or provider_name
    return parsed


def normalize_answer(parsed: dict[str, Any], evidence: list[ChatEvidence]) -> dict[str, Any]:
    """把模型输出收敛成安全结构：引用可为空，但不得凭空造 id。"""
    reply = " ".join(str(parsed.get("reply") or "").split())
    answer_mode = str(parsed.get("answer_mode") or "")
    known = {item.key: item for item in evidence}
    selected: list[ChatEvidence] = []
    seen: set[str] = set()
    for key in parsed.get("citation_ids") or []:
        item = known.get(str(key))
        if item is not None and item.key not in seen:
            seen.add(item.key)
            selected.append(item)

    if answer_mode not in ANSWER_MODES:
        # 模型没给合法取值时按证据使用情况推断，避免把 grounded 说成 general
        answer_mode = "grounded" if selected else ("mixed" if evidence else "general")
    followups: list[str] = []
    for item in parsed.get("followups") or []:
        text = " ".join(str(item or "").split())
        if text and text not in followups:
            followups.append(text)
        if len(followups) == MAX_FOLLOWUPS:
            break
    clarifying = " ".join(str(parsed.get("clarifying_question") or "").split())
    return {
        "reply": reply,
        "answer_mode": answer_mode,
        "citations": [item.citation for item in selected],
        "followups": followups,
        "clarifying_question": clarifying,
        "model": str(parsed.get("_model") or ""),
    }

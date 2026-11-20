"""政策流水线 Agent 执行循环（按 Skill 装配工具与提示词）。

两个 Skill（见 skills.py）：
- policy_preprocess：读原文/图谱/客户暴露 → 复核业务线 → 提交预处理结论；
- irrelevant_policy_cleanup：判定对汇丰无影响 → 删除政策与原文。

共同约束：
- 每一步工具调用都过权限校验（除数据外泄外全开）；
- 最终写库/删除只能经工具提交，服务端再次校验（字段收敛 / 确定性门禁）；
- provider 为 mock 或调用失败时退回确定性逻辑，流水线不中断。
"""
from __future__ import annotations

import json
from typing import Any

from app.agent.permissions import describe_permissions
from app.agent.skills import IRRELEVANT_CLEANUP, PREPROCESS, Skill
from app.agent.tools import AgentContext, describe_tools, run_tool
from app.ai.guard import repair_json
from app.ai.provider import LLMProvider, get_provider
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("agent.runner")

NON_AGENT_PROVIDERS = {"mock"}

EXECUTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": ["call_tool", "finish"]},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "plan": {"type": "object"},
        "thought": {"type": "string"},
    },
}

CLEANUP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": ["call_tool", "finish"]},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "decision": {"type": "string", "enum": ["delete", "keep"]},
        "reason": {"type": "string"},
    },
}

SYSTEM_PROMPT = """你是汇丰政策平台的「政策流水线 Agent」，负责政策生成收尾与预处理。

权限：除「数据外泄」外全部开放——
- 可读取库内政策、原文、业务图谱、客户暴露（聚合口径）、计算影响百分比；
- 可补全政策字段、提交预处理结论；
- 可检索公开信息，但检索词只能包含政策标题/主题/发文机构等公开词。

硬性约束：
1. 绝对禁止把客户名单、客户编号、内部评分、审批意见、贷款余额明细等内部数据写入检索词或任何外部请求；
2. 百分比必须来自 compute_percentages 的返回，不得自行编造或修改数字；
3. 业务线代码必须来自 read_business_map；
4. 先用工具核对依据（1–3 轮即可），再 finish 提交结论；不要重复调用同一工具同一参数。

输出：每轮只输出一个 JSON 对象。
- 调工具：{"action":"call_tool","tool":"工具名","args":{...},"thought":"一句话说明"}
- 收尾：{"action":"finish","plan":{"keywords":[],"business_line_codes":[],"customer_segments":[],"summary":"","notes":[]}}
"""

CLEANUP_SYSTEM = """你是汇丰政策平台的「无关政策清理 Agent」。

目标：判断当前政策是否对汇丰银行（hsbc_hk / hsbc_cn）完全没有影响。
- 如果完全没有影响（`check_hsbc_impact` 返回 verdict=none），调用 `delete_irrelevant_policy` 删除政策及原文；
- 只要存在任何潜在影响（相关性/合规/差异条款、覆盖外资行、受影响业务线、使用者已反馈、已发布），必须保留。

硬性约束：
1. 必须以 `check_hsbc_impact` 的确定性结论为准，不得自行猜测或扩大删除范围；
2. 删除不可恢复，reason 用一句话说明「为什么对汇丰没有影响」；
3. 每轮只输出一个 JSON 对象。

输出：
- 调工具：{"action":"call_tool","tool":"check_hsbc_impact","args":{}}
- 收尾：{"action":"finish","decision":"delete|keep","reason":"一句话理由"}
"""


def _render_tools(skill: Skill) -> str:
    return describe_tools(skill.tools)


def _opening(ctx: AgentContext, skill: Skill) -> str:
    policy = ctx.policy
    base = ctx.base_payload
    header = (
        f"SKILL: {skill.name}（{skill.label}）\n{skill.description}\n\n"
        f"可用工具：\n{_render_tools(skill)}\n\n"
        f"POLICY:\n{json.dumps({
            'id': policy.id,
            'title': policy.title,
            'issuing_body': policy.issuing_body,
            'jurisdiction': policy.jurisdiction,
            'themes': policy.themes or [],
            'priority': policy.priority,
            'status': policy.status,
            'applicable_scope': policy.applicable_scope,
            'target_entity_status': policy.target_entity_status,
            'summary': (policy.summary_zh or '')[:400],
        }, ensure_ascii=False, indent=1)}\n"
    )
    if not base:
        return header + "\n请先调用 check_hsbc_impact 获取确定性判定，再决定删除或保留。"
    return (
        header
        + "\nDETERMINISTIC_PREPROCESS（规则通道已算好的基础结果，可作为起点，不必推翻）：\n"
        + json.dumps({
            "keywords": base.get("keywords", [])[:8],
            "affected_business": base.get("affected_business", []),
            "customer_segments": base.get("customer_segments", [])[:6],
            "direction": base.get("direction"),
            "impact_total": base.get("impact_total"),
            "business_basis": (base.get("extras") or {}).get("business_basis", ""),
        }, ensure_ascii=False, indent=1)
        + "\n\n请决定第一步：call_tool 或 finish。"
    )


def _trace(ctx: AgentContext, skill: Skill, *, mode: str, model: str, rounds: int, summary: str) -> dict[str, Any]:
    return {
        "skill": skill.name,
        "mode": mode,
        "model": model,
        "rounds": rounds,
        "tools": ctx.tools_used,
        "steps": [
            {"tool": step.tool, "ok": step.ok, "args": step.args}
            for step in ctx.steps[-12:]
        ],
        "blocked": ctx.blocked,
        "permissions": describe_permissions(),
        "summary": summary,
    }


def fallback_trace(skill: Skill, reason: str = "") -> dict[str, Any]:
    return {
        "skill": skill.name,
        "mode": "rules",
        "model": "offline-rules",
        "rounds": 0,
        "tools": [],
        "steps": [],
        "blocked": [],
        "permissions": describe_permissions(),
        "summary": reason or "未接入生成式模型，按确定性规则完成",
    }


def _parse(result) -> dict | None:  # noqa: ANN001
    parsed = result.parsed if isinstance(result.parsed, dict) else None
    if parsed is None:
        parsed = repair_json(result.text or "")
    return parsed if isinstance(parsed, dict) else None


def run_preprocess_agent(
    ctx: AgentContext,
    *,
    provider: LLMProvider | None = None,
    skill: Skill = PREPROCESS,
) -> dict[str, Any]:
    """执行预处理 Agent，返回 {plan, trace}；任何失败都退回 rules 模式。"""
    settings = get_settings()
    provider = provider or get_provider()
    provider_name = str(getattr(provider, "name", "unknown"))
    if provider_name in NON_AGENT_PROVIDERS:
        return {"plan": None, "trace": fallback_trace(skill)}

    max_rounds = max(1, int(settings.preprocess_agent_max_rounds))
    transcript: list[str] = [_opening(ctx, skill)]
    invalid = 0
    model = provider_name

    for round_no in range(1, max_rounds + 1):
        try:
            result = provider.complete(
                system=SYSTEM_PROMPT,
                user="\n\n".join(transcript),
                schema=EXECUTOR_SCHEMA,
                temperature=0.1,
                max_tokens=900,
                model=settings.model_for_task("preprocess_agent"),
                task="preprocess_agent",
            )
        except Exception as exc:
            log.warning("preprocess_agent_step_failed", round=round_no, error_type=type(exc).__name__)
            invalid += 1
            if invalid >= 2:
                break
            continue

        model = result.model or model
        parsed = _parse(result)
        if parsed is None:
            invalid += 1
            if invalid >= 2:
                break
            transcript.append("上一轮输出不是合法 JSON，请只输出一个 JSON 对象。")
            continue

        action = str(parsed.get("action") or "")
        if action == "finish":
            plan = parsed.get("plan")
            if not isinstance(plan, dict) or not plan:
                transcript.append("finish 必须同时给出 plan 对象（keywords/business_line_codes/customer_segments/summary）。")
                invalid += 1
                if invalid >= 2:
                    break
                continue
            saved = run_tool(ctx, "save_preprocess", {"plan": plan}, allowed=skill.tools)
            if saved.get("error"):
                transcript.append(f"提交失败：{saved['error']}，请修正后重新 finish。")
                invalid += 1
                if invalid >= 2:
                    break
                continue
            plan = ctx.saved_plan or {}
            log.info("preprocess_agent_finished", policy_id=ctx.policy.id, rounds=round_no, tools=ctx.tools_used)
            return {
                "plan": plan,
                "trace": _trace(ctx, skill, mode="agent", model=model, rounds=round_no,
                                summary=str(plan.get("summary") or "")),
            }

        if action != "call_tool":
            invalid += 1
            if invalid >= 2:
                break
            transcript.append("action 只能是 call_tool 或 finish，请重新输出。")
            continue

        tool_name = str(parsed.get("tool") or "").strip()
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        observation = run_tool(ctx, tool_name, args, allowed=skill.tools)
        transcript.append(f"TOOL {tool_name} -> {json.dumps(observation, ensure_ascii=False)[:1800]}")
        transcript.append("请输出下一步 JSON（继续 call_tool 或 finish）。")

    log.info("preprocess_agent_fallback", policy_id=ctx.policy.id, tools=ctx.tools_used)
    return {
        "plan": None,
        "trace": _trace(ctx, skill, mode="rules", model=model,
                        summary="Agent 未产出可用结论，已按确定性规则完成预处理"),
    }


def run_cleanup_agent(
    ctx: AgentContext,
    *,
    provider: LLMProvider | None = None,
    skill: Skill = IRRELEVANT_CLEANUP,
) -> dict[str, Any]:
    """判定并清理无关政策，返回 {deleted, decision, reason, deletion, trace}。"""
    settings = get_settings()

    def _delete(reason: str, trace: dict[str, Any]) -> dict[str, Any]:
        deletion = run_tool(ctx, "delete_irrelevant_policy", {"reason": reason}, allowed=skill.tools)
        if deletion.get("error"):
            return {"deleted": False, "decision": "keep", "reason": deletion["error"], "trace": trace}
        return {"deleted": True, "decision": "delete", "reason": reason,
                "deletion": deletion, "trace": trace}

    provider = provider or get_provider()
    provider_name = str(getattr(provider, "name", "unknown"))
    if provider_name in NON_AGENT_PROVIDERS:
        # 未接入生成式模型：直接按确定性门禁执行
        verdict = run_tool(ctx, "check_hsbc_impact", {}, allowed=skill.tools)
        trace = _trace(ctx, skill, mode="rules", model="offline-rules", rounds=0,
                       summary="按确定性门禁判定" if verdict.get("verdict") == "none" else "存在潜在影响，保留")
        if verdict.get("recommendation") == "delete":
            return _delete("确定性门禁判定对汇丰完全没有影响", trace)
        return {"deleted": False, "decision": "keep",
                "reason": "；".join(verdict.get("keep_reasons") or ["存在潜在影响"]), "trace": trace}

    max_rounds = max(1, int(settings.preprocess_agent_max_rounds))
    transcript: list[str] = [_opening(ctx, skill)]
    invalid = 0
    model = provider_name

    for round_no in range(1, max_rounds + 1):
        try:
            result = provider.complete(
                system=CLEANUP_SYSTEM,
                user="\n\n".join(transcript),
                schema=CLEANUP_SCHEMA,
                temperature=0.0,
                max_tokens=500,
                model=settings.model_for_task("preprocess_agent"),
                task="irrelevant_cleanup",
            )
        except Exception as exc:
            log.warning("cleanup_agent_step_failed", round=round_no, error_type=type(exc).__name__)
            invalid += 1
            if invalid >= 2:
                break
            continue

        model = result.model or model
        parsed = _parse(result)
        if parsed is None:
            invalid += 1
            if invalid >= 2:
                break
            transcript.append("上一轮输出不是合法 JSON，请只输出一个 JSON 对象。")
            continue

        action = str(parsed.get("action") or "")
        if action == "finish":
            decision = str(parsed.get("decision") or "keep")
            reason = " ".join(str(parsed.get("reason") or "").split())[:300]
            trace = _trace(ctx, skill, mode="agent", model=model, rounds=round_no, summary=reason)
            if decision == "delete":
                return _delete(reason or "AI Agent 判定对汇丰无影响", trace)
            return {"deleted": False, "decision": "keep", "reason": reason or "Agent 判定保留", "trace": trace}

        if action != "call_tool":
            invalid += 1
            if invalid >= 2:
                break
            transcript.append("action 只能是 call_tool 或 finish，请重新输出。")
            continue

        tool_name = str(parsed.get("tool") or "").strip()
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        observation = run_tool(ctx, tool_name, args, allowed=skill.tools)
        transcript.append(f"TOOL {tool_name} -> {json.dumps(observation, ensure_ascii=False)[:1500]}")
        if ctx.deleted:
            trace = _trace(ctx, skill, mode="agent", model=model, rounds=round_no,
                           summary=str((ctx.deleted or {}).get("reason") or "已删除"))
            return {"deleted": True, "decision": "delete",
                    "reason": str((ctx.deleted or {}).get("reason") or ""),
                    "deletion": ctx.deleted, "trace": trace}
        transcript.append("请输出下一步 JSON：调用工具核对，或 finish 给出 delete/keep。")

    # 模型没给出可用结论时，回落到确定性门禁（不删除更安全）
    verdict = run_tool(ctx, "check_hsbc_impact", {}, allowed=skill.tools)
    trace = _trace(ctx, skill, mode="rules", model=model, rounds=round_no,
                   summary="Agent 未产出可用结论，按确定性门禁判定")
    if verdict.get("recommendation") == "delete":
        return _delete("Agent 无有效结论，确定性门禁判定对汇丰完全没有影响", trace)
    return {"deleted": False, "decision": "keep",
            "reason": "；".join(verdict.get("keep_reasons") or ["存在潜在影响"]), "trace": trace}

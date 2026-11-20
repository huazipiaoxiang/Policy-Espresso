"""预处理阶段接入政策流水线 Agent。

`refine_preprocess_payload` 在确定性规则结果之上叠加 Agent 结论：
- 关键词：Agent 结果优先，规则结果补位（保证召回不下降）；
- 业务线：Agent 选的代码必须在业务图谱内，百分比随后由平台口径重算；
- 客户类型：只能从业务图谱/客户表已有客群中选择，避免模型发明客群；
- 无论成功与否都写入 extras.agent 轨迹（模式、模型、工具、被拦截的出网请求、权限说明）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.runner import run_preprocess_agent
from app.agent.tools import AgentContext
from app.core.logging import get_logger
from app.db.models import Assessment, Policy
from app.domain.preprocess import percentages_for

log = get_logger("agent.preprocess")

KEYWORD_LIMIT = 12


def _dedup(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _known_segments(codes: list[str]) -> set[str]:
    """业务图谱 + 合成客户表里真实存在的客群，用于收敛模型输出。"""
    known: set[str] = set()
    try:
        from app.domain.business_map import load_business_map

        for line in load_business_map():
            if codes and line.code not in codes:
                continue
            known.update(str(segment) for segment in (line.segments or []) if segment)
    except Exception:
        log.warning("agent_business_map_unavailable")
    try:
        from app.domain.exposure import load_customers

        for customer in load_customers():
            if codes and customer.get("business_line") not in codes:
                continue
            segment = customer.get("segment")
            if segment:
                known.add(str(segment))
    except Exception:
        log.warning("agent_customers_unavailable")
    return known


def refine_preprocess_payload(
    db: Session,
    policy: Policy,
    assessment: Assessment | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """把 Agent 结论合并进预处理 payload；失败时原样返回规则结果。"""
    merged = dict(payload)
    extras = dict(payload.get("extras") or {})
    ctx = AgentContext(db=db, policy=policy, assessment=assessment, base_payload=payload)

    try:
        result = run_preprocess_agent(ctx)
    except Exception as exc:  # Agent 是增强项：任何异常都不能影响预处理落库
        log.warning("preprocess_agent_failed", policy_id=policy.id, error_type=type(exc).__name__)
        result = {"plan": None, "trace": {"mode": "rules", "model": "offline-rules", "rounds": 0,
                                          "tools": [], "steps": [], "blocked": [],
                                          "summary": f"Agent 运行异常（{type(exc).__name__}），已按规则完成预处理"}}

    trace = result.get("trace") or {}
    plan = result.get("plan")
    extras["agent"] = trace
    if plan:
        extras["agent_summary"] = str(plan.get("summary") or "")
        notes = [str(item) for item in plan.get("notes") or [] if item]
        if notes:
            extras["agent_notes"] = notes

        merged["keywords"] = _dedup(list(plan.get("keywords") or []) + list(payload.get("keywords") or []), KEYWORD_LIMIT)

        codes = [str(code) for code in (plan.get("business_line_codes") or []) if code]
        if codes:
            try:
                from app.domain.business_map import load_business_map

                names = {line.code: line.name for line in load_business_map()}
            except Exception:
                names = {}
            valid_codes = [code for code in codes if code in names]
            if valid_codes:
                lines = [{"code": code, "name": names.get(code, "")} for code in valid_codes]
                pct = percentages_for(policy, assessment, lines)
                merged["affected_business"] = lines
                merged.update({
                    "loss_pct": pct["loss_pct"],
                    "profit_pct": pct["profit_pct"],
                    "reputation_pct": pct["reputation_pct"],
                    "opportunity_pct": pct["opportunity_pct"],
                    "impact_total": pct["impact_total"],
                    "direction": pct["direction"],
                })
                extras.update({
                    "affected_amount_cny_yi": pct.get("affected_amount_cny_yi", 0),
                    "affected_customer_count": pct.get("affected_customer_count", 0),
                    "business_basis": "AI Agent 依据政策原文与业务图谱判定业务线",
                    "estimated_dimensions": pct.get("estimated", []),
                })

        known = _known_segments(codes)
        agent_segments = [str(item) for item in (plan.get("customer_segments") or []) if item]
        narrowed = [segment for segment in agent_segments if segment in known] if known else agent_segments
        if narrowed:
            merged["customer_segments"] = narrowed[:8]

        merged["source"] = f"agent:{trace.get('model') or 'llm'}"

    merged["extras"] = extras
    return merged

"""政策流水线 Agent 的工具箱（预处理阶段）。

工具清单与所需能力（除 egress 外全部授予）：
- read_policy / read_document / read_business_map / read_customer_exposure    → read
- compute_percentages                                                       → read（口径计算，模型不得自造数字）
- refresh_policy_fields                                                     → write
- search_public_web                                                         → public_egress（出网清洗）
- save_preprocess                                                           → write（落库前最后一次校验）

工具只接受结构化参数，不执行 SQL；每个工具的异常都在边界内吞掉并回灌观察，
避免单次工具失败打断整条流水线。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent.permissions import (
    DELETE,
    PUBLIC_EGRESS,
    READ,
    WRITE,
    check_tool_permission,
    sanitize_public_query,
)
from app.core.logging import get_logger
from app.db.models import Assessment, Policy

log = get_logger("agent.tools")

DOC_EXCERPT_LIMIT = 2400
KEYWORD_LIMIT = 12
SEGMENT_LIMIT = 8


@dataclass
class AgentStep:
    tool: str
    args: dict[str, Any]
    ok: bool
    note: str = ""


@dataclass
class AgentContext:
    """一次 Agent 运行所需的上下文（库内对象 + 已算好的确定性结果）。"""

    db: Session
    policy: Policy
    assessment: Assessment | None
    base_payload: dict[str, Any]
    steps: list[AgentStep] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    saved_plan: dict[str, Any] | None = None
    deleted: dict[str, Any] | None = None

    @property
    def document(self):  # noqa: ANN201 - 延迟取关系，避免触发额外查询
        return getattr(self.policy, "document", None)

    def public_texts(self) -> list[str]:
        """允许出网的公开文本：政策标题、主题、发文机构、政策类型。"""
        return [
            str(self.policy.title or ""),
            " ".join(str(theme) for theme in (self.policy.themes or [])),
            str(self.policy.issuing_body or ""),
            str(self.policy.policy_type or ""),
        ]


ToolHandler = Callable[[AgentContext, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permissions: frozenset[str]
    handler: ToolHandler


def _clip(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _read_policy(ctx: AgentContext, _args: dict[str, Any]) -> dict[str, Any]:
    policy = ctx.policy
    assessment = ctx.assessment
    return {
        "id": policy.id,
        "title": policy.title,
        "issuing_body": policy.issuing_body,
        "jurisdiction": policy.jurisdiction,
        "policy_type": policy.policy_type,
        "priority": policy.priority,
        "status": policy.status,
        "themes": policy.themes or [],
        "summary": _clip(policy.summary_zh, 600),
        "direction": assessment.direction if assessment else "",
        "score_total": assessment.score_total if assessment else None,
        "transmission_chain": (assessment.transmission_chain if assessment else [])[:6],
    }


def _read_document(ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    document = ctx.document
    if document is None:
        return {"error": "该政策没有关联原文"}
    try:
        offset = max(0, min(int(args.get("offset") or 0), 20000))
    except (TypeError, ValueError):
        offset = 0
    content = document.content_text or ""
    return {
        "url": document.url,
        "fetched_at": document.fetched_at.isoformat() if document.fetched_at else None,
        "length": len(content),
        "offset": offset,
        "excerpt": _clip(content[offset:offset + DOC_EXCERPT_LIMIT], DOC_EXCERPT_LIMIT),
    }


def _read_business_map(_ctx: AgentContext, _args: dict[str, Any]) -> dict[str, Any]:
    from app.domain.business_map import load_business_map

    lines = []
    for line in load_business_map():
        lines.append({
            "code": line.code,
            "name": line.name,
            "segments": list(line.segments or [])[:8],
            "products": list(line.products or [])[:8],
        })
    return {"business_lines": lines}


def _read_customer_exposure(_ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    """客户暴露的**聚合**口径：只给业务线汇总，不返回任何客户级信息。"""
    from app.domain.exposure import load_customers

    codes = {str(code) for code in (args.get("business_line_codes") or []) if code}
    customers = load_customers()
    buckets: dict[str, dict[str, float]] = {}
    for customer in customers:
        line = str(customer.get("business_line") or "未标注")
        if codes and line not in codes:
            continue
        bucket = buckets.setdefault(line, {"customers": 0, "loan_balance_cny_yi": 0.0, "other_bank_loans_cny_yi": 0.0})
        bucket["customers"] += 1
        bucket["loan_balance_cny_yi"] += float(customer.get("loan_balance_cny_yi") or 0)
        bucket["other_bank_loans_cny_yi"] += float(customer.get("other_bank_loans_cny_yi") or 0)
    by_line = [
        {
            "business_line": line,
            "customers": int(values["customers"]),
            "loan_balance_cny_yi": round(values["loan_balance_cny_yi"], 2),
            "other_bank_loans_cny_yi": round(values["other_bank_loans_cny_yi"], 2),
        }
        for line, values in sorted(buckets.items(), key=lambda item: -item[1]["loan_balance_cny_yi"])
    ]
    return {
        "total_customers": sum(item["customers"] for item in by_line),
        "by_business_line": by_line,
        "note": "聚合口径，仅用于判断业务线集中度；不包含客户名单与客户编号",
    }


def _compute_percentages(ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.domain.business_map import load_business_map
    from app.domain.preprocess import percentages_for

    names = {line.code: line.name for line in load_business_map()}
    codes = [str(code) for code in (args.get("business_line_codes") or []) if code]
    codes = [code for code in codes if code in names]
    if not codes:
        return {"error": "business_line_codes 必填，取值必须是业务图谱中的业务线代码"}
    lines = [{"code": code, "name": names.get(code, "")} for code in codes]
    pct = percentages_for(ctx.policy, ctx.assessment, lines)
    return {
        "business_line_codes": codes,
        "loss_pct": pct["loss_pct"],
        "profit_pct": pct["profit_pct"],
        "reputation_pct": pct["reputation_pct"],
        "opportunity_pct": pct["opportunity_pct"],
        "impact_total": pct["impact_total"],
        "affected_amount_cny_yi": pct.get("affected_amount_cny_yi", 0),
        "affected_customer_count": pct.get("affected_customer_count", 0),
        "note": "百分比由平台统一口径计算，模型不得自行改写",
    }


def _refresh_policy_fields(ctx: AgentContext, _args: dict[str, Any]) -> dict[str, Any]:
    """补全政策字段（原文 → 政策生成阶段的收尾）：主题、摘要、辖区、类型。"""
    policy = ctx.policy
    document = ctx.document
    changed: dict[str, Any] = {}

    if not policy.themes:
        try:
            from app.domain.offline_fallback import detect_themes

            themes = detect_themes(policy.title or "", policy.summary_zh or (document.content_text if document else "")[:1200])
            if themes:
                policy.themes = themes
                changed["themes"] = themes
        except Exception:
            log.warning("agent_theme_refresh_failed", policy_id=policy.id)

    if not policy.summary_zh and document is not None and document.content_text:
        policy.summary_zh = _clip(document.content_text, 300)
        changed["summary_zh"] = "由原文首段生成"

    if not policy.jurisdiction:
        source = getattr(document, "source", None)
        if source is not None and getattr(source, "jurisdiction", None):
            policy.jurisdiction = source.jurisdiction
            changed["jurisdiction"] = source.jurisdiction

    if not policy.policy_type:
        policy.policy_type = "监管政策"
        changed["policy_type"] = "监管政策"

    return {"changed": changed or {}, "note": "仅补全空字段，不覆盖已有内容"}


def _search_public_web(ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    """仅携带公开信息的联网检索；查询须通过出网清洗，否则整次调用被拒。"""
    query, reason = sanitize_public_query(
        str(args.get("query") or ""),
        allowed_texts=ctx.public_texts(),
    )
    if query is None:
        ctx.blocked.append({"tool": "search_public_web", "reason": reason})
        log.warning("agent_egress_blocked", policy_id=ctx.policy.id, reason=reason)
        return {"blocked": True, "reason": reason}
    try:
        from app.chat.web_search import WebSearchError, search_web

        items = search_web(query, limit=3)
    except WebSearchError as exc:
        return {"query": query, "error": f"联网检索失败：{exc}"}
    except Exception as exc:  # 联网是增强项，失败不阻断
        return {"query": query, "error": f"联网检索异常：{type(exc).__name__}"}
    return {
        "query": query,
        "items": [
            {"title": _clip(item.title, 80), "summary": _clip(item.text, 160), "url": item.citation.get("url", "")}
            for item in items[:3]
        ],
    }


def _check_hsbc_impact(ctx: AgentContext, _args: dict[str, Any]) -> dict[str, Any]:
    """确定性影响判定：只看证据，不采信模型自述。"""
    from app.agent.cleanup import assess_hsbc_impact

    return assess_hsbc_impact(ctx.db, ctx.policy, ctx.assessment)


def _delete_irrelevant_policy(ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    """删除无关政策与原文。执行前重跑确定性门禁，证据不足直接拒绝。"""
    from app.agent.cleanup import assess_hsbc_impact, delete_policy_and_document

    verdict = assess_hsbc_impact(ctx.db, ctx.policy, ctx.assessment)
    if verdict["verdict"] != "none":
        return {
            "error": "不能删除：政策仍有潜在影响（" + "；".join(verdict["keep_reasons"]) + "）",
            "verdict": verdict,
        }
    reason = _clip(args.get("reason"), 200) or "AI Agent 判定对汇丰无影响，已删除政策与原文"
    info = delete_policy_and_document(ctx.db, ctx.policy, reason=reason)
    ctx.deleted = {**info, "reason": reason}
    return {"deleted": True, **info, "reason": reason}


def _save_preprocess(ctx: AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    plan = args.get("plan")
    if not isinstance(plan, dict):
        return {"error": "plan 必须是对象"}
    ctx.saved_plan = normalize_plan(plan)
    return {"saved": True, "fields": sorted(ctx.saved_plan.keys())}


def normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """收敛模型给出的预处理结论，防止越权写入无关字段。"""
    def _text_list(value: object, limit: int, max_len: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value if isinstance(value, list) else []:
            text = _clip(item, max_len)
            if text and text not in seen:
                seen.add(text)
                out.append(text)
            if len(out) >= limit:
                break
        return out

    def _research_items(value: object, limit: int = 3) -> list[dict[str, str]]:
        """三栏情报条目：只保留 {summary, url}，按 url 去重，url 必须以 http(s) 开头。"""
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            summary = _clip(item.get("summary"), 200)
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not summary:
                continue
            seen.add(url)
            out.append({"summary": summary, "url": url})
            if len(out) >= limit:
                break
        return out

    codes = _text_list(plan.get("business_line_codes"), 6, 24)
    return {
        "keywords": _text_list(plan.get("keywords"), KEYWORD_LIMIT, 24),
        "business_line_codes": [re.sub(r"[^A-Za-z0-9_]", "", code) for code in codes if code],
        "customer_segments": _text_list(plan.get("customer_segments"), SEGMENT_LIMIT, 32),
        "summary": _clip(plan.get("summary"), 400),
        "notes": _text_list(plan.get("notes"), 6, 120),
        "hsbc_reaction": _research_items(plan.get("hsbc_reaction")),
        "similar_policies": _research_items(plan.get("similar_policies")),
        "market_applications": _research_items(plan.get("market_applications")),
    }


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="read_policy",
        description="读取当前政策字段与影响分析结论（标题/发文机构/辖区/主题/摘要/方向/传导链）。",
        permissions=frozenset({READ}),
        handler=_read_policy,
    ),
    ToolSpec(
        name="read_document",
        description="读取政策原文摘录（默认前 2400 字，可用 offset 翻页）。用于核对条款与业务范围。",
        permissions=frozenset({READ}),
        handler=_read_document,
    ),
    ToolSpec(
        name="read_business_map",
        description="读取业务图谱：业务线代码、名称、客群、产品。用于选择正确的业务线代码与客户类型。",
        permissions=frozenset({READ}),
        handler=_read_business_map,
    ),
    ToolSpec(
        name="read_customer_exposure",
        description="读取客户暴露的聚合口径（按业务线：客户数、本行/他行贷款合计）。不含客户名单。",
        permissions=frozenset({READ}),
        handler=_read_customer_exposure,
    ),
    ToolSpec(
        name="compute_percentages",
        description="按平台统一口径计算损失/盈利/信誉/机会四个百分比与综合分；传入 business_line_codes。",
        permissions=frozenset({READ}),
        handler=_compute_percentages,
    ),
    ToolSpec(
        name="refresh_policy_fields",
        description="补全政策空字段（主题/摘要/辖区/类型），只补空不覆盖。用于原文→政策生成阶段的收尾。",
        permissions=frozenset({WRITE}),
        handler=_refresh_policy_fields,
    ),
    ToolSpec(
        name="search_public_web",
        description="联网检索公开信息（政策原文、银行回应、落地案例）。查询只能包含政策公开词，内部数据一律拦截。",
        permissions=frozenset({PUBLIC_EGRESS}),
        handler=_search_public_web,
    ),
    ToolSpec(
        name="check_hsbc_impact",
        description="确定性判定政策对汇丰银行的影响：返回 verdict=none/possible、保留理由与判定信号（相关性/合规/差异维度、适用范围、优先级、综合分、受影响业务线、使用者反馈）。",
        permissions=frozenset({READ}),
        handler=_check_hsbc_impact,
    ),
    ToolSpec(
        name="delete_irrelevant_policy",
        description="删除判定为对汇丰完全没有影响的政策及其原文（不可恢复，仅留审计）。执行前会重跑确定性门禁，证据不足直接拒绝。",
        permissions=frozenset({DELETE}),
        handler=_delete_irrelevant_policy,
    ),
    ToolSpec(
        name="save_preprocess",
        description="提交最终预处理结论（关键词/业务线代码/客户类型/结论）。服务端会再次校验字段范围后落库。",
        permissions=frozenset({WRITE}),
        handler=_save_preprocess,
    ),
)

_TOOL_INDEX = {spec.name: spec for spec in TOOLS}


def available_tools(allowed: tuple[str, ...] | None = None) -> list[ToolSpec]:
    """按权限过滤后的工具清单（egress 工具不会出现）；`allowed` 为 Skill 声明的工具子集。"""
    visible: list[ToolSpec] = []
    for spec in TOOLS:
        if allowed is not None and spec.name not in allowed:
            continue
        try:
            check_tool_permission(spec.name, spec.permissions)
        except Exception:
            continue
        visible.append(spec)
    return visible


def describe_tools(allowed: tuple[str, ...] | None = None) -> str:
    lines = []
    for spec in available_tools(allowed):
        caps = "/".join(sorted(spec.permissions))
        lines.append(f"- {spec.name}（{caps}）：{spec.description}")
    return "\n".join(lines)


def run_tool(
    ctx: AgentContext,
    name: str,
    args: dict[str, Any] | None = None,
    *,
    allowed: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """执行单个工具，返回观察结果；权限或异常都在边界内转成可读错误。"""
    args = args or {}
    spec = _TOOL_INDEX.get(name)
    if spec is None:
        return {"error": f"未知工具 {name}，可用工具：{', '.join(spec.name for spec in available_tools(allowed))}"}
    if allowed is not None and name not in allowed:
        ctx.blocked.append({"tool": name, "reason": "该工具不在当前 Skill 的工具集内"})
        return {"error": f"工具 {name} 不在当前 Skill 的工具集内"}
    try:
        check_tool_permission(spec.name, spec.permissions)
    except Exception as exc:
        ctx.blocked.append({"tool": name, "reason": str(exc)})
        log.warning("agent_tool_denied", tool=name, reason=str(exc))
        return {"error": str(exc)}
    try:
        observation = spec.handler(ctx, args)
    except Exception as exc:  # 工具边界：单工具失败不打断循环
        log.warning("agent_tool_failed", tool=name, error_type=type(exc).__name__)
        return {"error": f"{name} 执行出错（{type(exc).__name__}）"}
    ctx.steps.append(AgentStep(tool=name, args=args, ok="error" not in observation and not observation.get("blocked")))
    if name not in ctx.tools_used:
        ctx.tools_used.append(name)
    return observation

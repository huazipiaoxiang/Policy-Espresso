"""管理员任务：让 Chat 助手在系统内「做事」，而不只是检索。

三个任务型能力（仅 admin 可见，注册在 tool_registry）：

- ``list_cleanup_candidates``：只读扫描，列出通过确定性门禁、可清理的无关政策；
- ``cleanup_policies``：执行删除。四道闸同时成立才动手：
  1) 角色为 admin（注册表层已过滤，这里的校验是纵深防御）；
  2) 工具参数 ``confirm=true``；
  3) **用户本轮消息**含明确确认词（模型无法替用户确认）；
  4) 每条政策重跑确定性门禁，未通过的原地拒绝并说明保留理由。
  单次上限 10 条，逐条提交并写审计（delete_policy / delete_document）。
- ``build_impact_report``：按政策名/文号/ID 生成影响报告（统计口径与政策详情页一致）。

结果统一转成 ``ChatEvidence(kind="task")`` 回灌给模型，模型只负责如实汇报；
它拿到的 policy_ids 只能来自 ``list_cleanup_candidates``，不能凭空生成。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select

from app.agent.cleanup import SCOPE_INCLUDES_HSBC, assess_hsbc_impact, cleanup_policy_if_irrelevant
from app.ai.followup import affected_customer_brief
from app.chat.tools import ChatEvidence, ChatTools
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Policy
from app.domain.policy_impact import (
    affected_customer_stats,
    followup_policy_card,
    followup_report_summary,
)

log = get_logger("chat.tasks")

MAX_CLEANUP_BATCH = 10
MAX_CANDIDATES = 20
SCAN_LIMIT = 500
REPORT_TEXT_LIMIT = 1500

# 用户必须在本轮消息里给出**授权**，模型自述「用户已确认」不算。
# 只收明确的commit类动词：像「有哪些政策可以清理」这类询问不能算确认。
CONFIRM_WORDS = (
    "确认清理", "确认删除", "确认执行", "确认无误", "确认",
    "同意清理", "同意删除", "同意执行", "同意",
    "批准清理", "批准删除", "批准",
    "执行吧", "删吧", "删除吧", "照做", "就删", "开始清理", "开始删除",
)
# 「确认一下有哪些政策可以清理」仍是在问清单，不是授权删除
_NOT_CONFIRM_PHRASES = ("确认一下", "确认下", "确认是否", "确认能不能")


@dataclass
class TaskOutcome:
    """任务执行结果：给模型看的一句话结论 + 结构化明细。"""

    name: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    executed: bool = False  # 是否真的产生了写操作（前端/审计可据此区分 dry-run）

    def to_evidence(self) -> ChatEvidence:
        lines = [self.summary]
        for key, value in self.detail.items():
            if value in (None, "", [], {}):
                continue
            lines.append(f"{key}: {value}")
        text = "\n".join(lines)[:REPORT_TEXT_LIMIT]
        digest = hashlib.sha1(f"{self.name}|{self.summary}".encode()).hexdigest()[:8]
        citation_id = f"task:{self.name}:{digest}"
        return ChatEvidence(
            key=citation_id,
            kind="task",
            title=f"任务结果｜{self.name}",
            text=text,
            citation={"id": citation_id, "type": "task", "title": f"任务结果｜{self.name}"},
            score=100,
        )


def has_confirmation(text: str) -> bool:
    """用户本轮是否明确授权执行删除（询问清单/假设句不算）。"""
    folded = "".join(str(text or "").split())
    if any(phrase in folded for phrase in _NOT_CONFIRM_PHRASES):
        return False
    return any(word in folded for word in CONFIRM_WORDS)


# ---------- 1. 只读扫描：可清理的无关政策 ----------


def _candidate_query():
    """先用廉价字段预筛，再逐条跑确定性门禁（门禁才是最终裁决）。"""
    settings = get_settings()
    return (
        select(Policy)
        .where(
            Policy.status != "published",
            Policy.priority == "P3",
            Policy.score_total <= float(settings.irrelevant_policy_score_max),
            Policy.foreign_bank_differential.is_(False),
            Policy.target_entity_status.in_(("low", "not_mentioned")),
            or_(
                Policy.applicable_scope.is_(None),
                func.lower(Policy.applicable_scope).notin_(tuple(SCOPE_INCLUDES_HSBC)),
            ),
        )
        .limit(SCAN_LIMIT)
    )


def cleanup_candidates(db, limit: int = MAX_CANDIDATES) -> TaskOutcome:
    """列出通过确定性门禁的政策（不删除）。"""
    limit = max(1, min(MAX_CANDIDATES, int(limit or MAX_CANDIDATES)))
    policies = list(db.scalars(_candidate_query()).all())

    candidates: list[dict[str, Any]] = []
    for policy in policies:
        if len(candidates) >= limit:
            break
        verdict = assess_hsbc_impact(db, policy)
        if verdict["verdict"] != "none":
            continue
        candidates.append({
            "policy_id": policy.id,
            "title": policy.title,
            "priority": policy.priority,
            "score_total": float(policy.score_total or 0),
            "jurisdiction": policy.jurisdiction,
        })

    if not candidates:
        return TaskOutcome(
            name="list_cleanup_candidates",
            summary=f"当前没有对汇丰完全没有影响的政策（已扫描 {len(policies)} 条未发布政策）。",
            detail={"scanned": len(policies)},
        )
    return TaskOutcome(
        name="list_cleanup_candidates",
        summary=(
            f"当前有 {len(candidates)} 条政策对汇丰完全没有影响"
            f"（从 {len(policies)} 条未发布政策中筛选：相关性/合规/差异均为 0、无使用者反馈）。"
        ),
        detail={
            "scanned": len(policies),
            "candidates": [
                f"{item['policy_id']}｜{item['title']}（{item['priority']}，{item['score_total']} 分）"
                for item in candidates
            ],
            "policy_ids": [item["policy_id"] for item in candidates],
            "hint": "清理不可恢复，请先向用户列出清单并请求明确确认（用户回复「确认清理」）后再执行。",
        },
    )


# ---------- 2. 执行清理 ----------


def _normalize_ids(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [item for item in raw.replace("，", ",").split(",")]
    if not isinstance(raw, (list, tuple, set)):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


def _refuse(summary: str, *, actor: str, gate: str) -> TaskOutcome:
    """拒绝执行也要留痕：破坏性操作被拦下是安全信号，不只是回复文案。"""
    log.warning("chat_cleanup_refused", actor=actor, gate=gate)
    return TaskOutcome(name="cleanup_policies", summary=summary, ok=False)


def cleanup_policies(tools: ChatTools, args: dict[str, Any]) -> TaskOutcome:
    """删除门禁通过的政策与原文；四道闸缺一不可。"""
    db = tools.db
    if tools.role != "admin":
        return _refuse("当前角色无权执行政策清理（需要管理员）。", actor=tools.actor, gate="role")

    policy_ids = _normalize_ids(args.get("policy_ids") or args.get("ids"))
    if not policy_ids:
        return _refuse(
            "没有给出要清理的 policy_ids；请先调用 list_cleanup_candidates 获取候选。",
            actor=tools.actor, gate="missing_ids",
        )
    if len(policy_ids) > MAX_CLEANUP_BATCH:
        return _refuse(
            f"单次最多清理 {MAX_CLEANUP_BATCH} 条，本次传入 {len(policy_ids)} 条，请分批执行。",
            actor=tools.actor, gate="batch_limit",
        )
    if str(args.get("confirm") or "").lower() not in ("true", "1", "yes"):
        return _refuse(
            "未确认执行：需要 confirm=true。请先把候选清单发给用户，等用户明确确认后再调用。",
            actor=tools.actor, gate="confirm_flag",
        )
    if not has_confirmation(tools.question):
        return _refuse(
            "用户本轮消息没有明确确认，已拒绝执行。"
            "请列出候选政策并请用户回复「确认清理」后再执行。",
            actor=tools.actor, gate="user_confirmation",
        )

    deleted: list[str] = []
    kept: list[str] = []
    missing: list[str] = []
    errors: list[str] = []

    for policy_id in policy_ids:
        policy = db.get(Policy, policy_id)
        if policy is None:
            missing.append(policy_id)
            continue
        title = policy.title
        try:
            result = cleanup_policy_if_irrelevant(
                db, policy, deterministic_only=True, actor=tools.actor,
            )
        except Exception as exc:  # 单条失败不连坐整批
            db.rollback()
            errors.append(f"{policy_id}: {type(exc).__name__}")
            log.warning("chat_cleanup_failed", policy_id=policy_id, error_type=type(exc).__name__)
            continue
        if result.get("deleted"):
            deleted.append(f"{policy_id}｜{title}")
        else:
            kept.append(f"{policy_id}｜{title}：{result.get('reason') or '未通过门禁'}")

    log.info(
        "chat_cleanup_done", actor=tools.actor, requested=len(policy_ids),
        deleted=len(deleted), kept=len(kept), errors=len(errors),
    )
    summary_parts = [f"已删除 {len(deleted)} 条政策及原文"]
    if kept:
        summary_parts.append(f"保留 {len(kept)} 条（未通过门禁）")
    if missing:
        summary_parts.append(f"不存在 {len(missing)} 条")
    if errors:
        summary_parts.append(f"失败 {len(errors)} 条")
    return TaskOutcome(
        name="cleanup_policies",
        summary="；".join(summary_parts) + "。删除已写入审计，不可恢复。",
        detail={
            "deleted": deleted,
            "kept": kept,
            "missing": missing,
            "errors": errors,
        },
        ok=not errors,
        executed=bool(deleted),
    )


# ---------- 3. 生成政策影响报告 ----------


def _resolve_policies(db, query: str, limit: int = 3) -> list[Policy]:
    text = " ".join(str(query or "").split())
    if not text:
        return []
    direct = db.get(Policy, text)
    if direct is not None:
        return [direct]
    pattern = f"%{text}%"
    stmt = (
        select(Policy)
        .where(or_(Policy.title.ilike(pattern), Policy.doc_number.ilike(pattern)))
        .order_by(Policy.published_at.desc().nullslast(), Policy.id)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def _line_text(stats: dict, limit: int = 4) -> str:
    items = stats.get("by_business_line") or []
    return "、".join(
        f"{item.get('business_line') or '未标注'} {item.get('customers', 0)} 户"
        for item in items[:limit]
    ) or "未标注"


def _report_text(policy: Policy, stats: dict, reports: dict, brief: dict) -> str:
    lines = [
        f"政策：{policy.title}",
        f"发文机构：{policy.issuing_body or '未标注'}｜辖区：{policy.jurisdiction or '未标注'}"
        f"｜优先级：{policy.priority or '—'}（{policy.score_total or 0} 分）",
        f"结论：{brief.get('headline') or '—'}",
        f"概述：{brief.get('summary') or '—'}",
        f"受影响客户：{stats.get('total_customers', 0)} 户"
        f"（本行贷款 {stats.get('loan_balance_total_cny_yi', 0)} 亿元，"
        f"他行贷款 {stats.get('other_bank_loans_total_cny_yi', 0)} 亿元）",
        f"业务线分布：{_line_text(stats)}",
        "关注要点：" + "；".join(str(item) for item in (brief.get("focus_points") or [])[:5]),
        "建议动作：" + "；".join(str(item) for item in (brief.get("suggested_actions") or [])[:5]),
        f"使用者反馈：{reports.get('count', 0)} 份影响报告（待跟进 {reports.get('pending', 0)} 份）",
        f"口径：{stats.get('source')}；生成方式：{brief.get('generated_by')}",
    ]
    return "\n".join(lines)[:REPORT_TEXT_LIMIT]


def build_impact_report(db, query: str) -> TaskOutcome:
    """按政策名/文号/ID 生成影响报告；同名多条时要求用户指定。"""
    policies = _resolve_policies(db, query)
    if not policies:
        return TaskOutcome(
            name="build_impact_report",
            summary=f"没有找到与「{query}」匹配的政策，请提供更准确的政策名称或文号。",
            ok=False,
        )
    if len(policies) > 1:
        return TaskOutcome(
            name="build_impact_report",
            summary="匹配到多条政策，请让用户指定其中一条后重新生成。",
            detail={"candidates": [f"{item.id}｜{item.title}" for item in policies]},
            ok=False,
        )

    policy = policies[0]
    stats = affected_customer_stats(db, policy)
    reports = followup_report_summary(db, policy.id)
    brief = affected_customer_brief(followup_policy_card(db, policy), stats, reports)
    log.info("chat_impact_report", policy_id=policy.id, customers=stats.get("total_customers"))
    return TaskOutcome(
        name="build_impact_report",
        summary=f"已生成《{policy.title}》的政策影响报告。",
        detail={
            "policy_id": policy.id,
            "report": _report_text(policy, stats, reports, brief),
            "customers": stats.get("total_customers", 0),
            "generated_by": brief.get("generated_by"),
        },
    )

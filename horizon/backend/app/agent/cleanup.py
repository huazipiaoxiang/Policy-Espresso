"""无关政策清理能力（Agent Skill：irrelevant_policy_cleanup）。

判定「对汇丰银行完全没有影响」是**确定性门禁**，不由模型自由裁量：
- 相关性/合规/差异三个维度必须都为 0（`has_no_direct_impact`）；
- 目标实体状态为 low / not_mentioned，适用范围不含外资行；
- 无受影响业务线、无外资行差异条款、优先级 P3 且综合分低于阈值；
- 政策未发布、没有使用者影响报告/反馈。

满足后由 Agent 调用删除工具；删除工具会重新跑一遍门禁，模型说删但证据不足时会被拒绝。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import (
    Assessment,
    AuditLog,
    ConsumerReport,
    Document,
    DocumentChunk,
    DocumentVersion,
    Feedback,
    Policy,
)
from app.domain.consumer_impact import has_no_direct_impact
from app.domain.policy_admin import delete_policy_records

log = get_logger("agent.cleanup")

ACTOR = "agent.policy-cleanup"
# 适用范围里包含/可能包含外资行的取值：出现即保留（批量预筛也用它）
SCOPE_INCLUDES_HSBC = frozenset({"all", "foreign_included", "qualified_only"})


def assess_hsbc_impact(db: Session, policy: Policy, assessment: Assessment | None = None) -> dict[str, Any]:
    """确定性判定政策对汇丰的影响等级，返回 verdict=none 的可删除结论。"""
    settings = get_settings()
    if assessment is None:
        assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    scores = assessment.scores if assessment else None
    business_lines = ((assessment.affected or {}).get("business_lines") if assessment else None) or []

    report_count = db.scalar(
        select(func.count(ConsumerReport.id)).where(ConsumerReport.policy_id == policy.id)
    ) or 0
    feedback_count = db.scalar(
        select(func.count(Feedback.id)).where(Feedback.policy_id == policy.id)
    ) or 0

    keep_reasons: list[str] = []
    if assessment is None:
        keep_reasons.append("缺少影响分析结论，不做自动删除")
    elif not has_no_direct_impact(scores):
        keep_reasons.append("相关性/合规/差异维度仍大于 0，存在潜在影响")
    if (policy.target_entity_status or "").lower() not in ("low", "not_mentioned"):
        keep_reasons.append(f"目标实体状态为 {policy.target_entity_status or '未知'}")
    if (policy.applicable_scope or "").lower() in SCOPE_INCLUDES_HSBC:
        keep_reasons.append(f"适用范围为 {policy.applicable_scope}，可能覆盖外资行")
    if policy.foreign_bank_differential:
        keep_reasons.append("存在外资行差异条款")
    if business_lines:
        keep_reasons.append(f"存在受影响业务线：{'、'.join(map(str, business_lines))}")
    if (policy.priority or "P3") != "P3":
        keep_reasons.append(f"优先级为 {policy.priority}")
    if float(policy.score_total or 0) > float(settings.irrelevant_policy_score_max):
        keep_reasons.append(f"综合分 {policy.score_total} 高于清理阈值 {settings.irrelevant_policy_score_max}")
    if (policy.status or "") == "published":
        keep_reasons.append("政策已发布，不自动删除")
    if report_count:
        keep_reasons.append(f"已有 {report_count} 份使用者影响报告")
    if feedback_count:
        keep_reasons.append(f"已有 {feedback_count} 条使用者反馈")

    return {
        "verdict": "none" if not keep_reasons else "possible",
        "recommendation": "delete" if not keep_reasons else "keep",
        "keep_reasons": keep_reasons,
        "signals": {
            "no_direct_impact": bool(has_no_direct_impact(scores)),
            "target_entity_status": policy.target_entity_status or "",
            "applicable_scope": policy.applicable_scope or "",
            "foreign_bank_differential": bool(policy.foreign_bank_differential),
            "priority": policy.priority or "",
            "score_total": float(policy.score_total or 0),
            "affected_business_lines": list(map(str, business_lines)),
            "consumer_reports": int(report_count),
            "feedbacks": int(feedback_count),
            "status": policy.status or "",
        },
    }


def delete_policy_and_document(
    db: Session,
    policy: Policy,
    *,
    reason: str,
    actor: str = ACTOR,
) -> dict[str, Any]:
    """删除政策及其原文（政策与原文一对一，原文不再被其他政策引用）。

    只做数据层删除 + 审计，不 commit；文件清理由调用方在 commit 后执行。
    """
    policy_id = policy.id
    document = db.get(Document, policy.document_id)
    document_id = document.id if document else None
    before_policy = {
        "title": policy.title,
        "status": policy.status,
        "priority": policy.priority,
        "document_id": policy.document_id,
    }
    before_document = (
        {"title": document.title, "source_id": document.source_id, "url": document.url, "status": document.status}
        if document else {}
    )
    attachments = [
        att.get("path") for att in (document.attachments or [])
        if isinstance(att, dict) and att.get("path")
    ] if document else []

    delete_policy_records(db, policy)
    if document:
        db.execute(sa_delete(DocumentVersion).where(DocumentVersion.document_id == document.id))
        db.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.execute(sa_delete(Document).where(Document.id == document.id))

    db.add(AuditLog(
        actor=actor, action="delete_policy", object_type="policy", object_id=policy_id,
        before=before_policy, after={"deleted": True, "document_deleted": bool(document)},
        reason=reason,
    ))
    if document:
        db.add(AuditLog(
            actor=actor, action="delete_document", object_type="document", object_id=document_id,
            before=before_document, after={"deleted": True, "policy_deleted": True},
            reason=f"{reason}（关联原文一并删除）",
        ))
    log.info("irrelevant_policy_deleted", policy_id=policy_id, document_id=document_id, reason=reason)
    return {"policy_id": policy_id, "document_id": document_id, "attachments": attachments}


def _remove_attachment_files(paths: list[str]) -> None:
    settings = get_settings()
    storage_root = Path(settings.storage_dir).resolve()
    for rel in paths:
        if not rel:
            continue
        candidate = (storage_root / rel).resolve()
        if candidate.is_relative_to(storage_root) and candidate.is_file():
            candidate.unlink(missing_ok=True)


def cleanup_policy_if_irrelevant(
    db: Session,
    policy: Policy,
    *,
    assessment: Assessment | None = None,
    use_agent: bool | None = None,
    commit: bool = True,
    deterministic_only: bool = False,
    actor: str = ACTOR,
) -> dict[str, Any]:
    """对汇丰完全没有影响时，删除政策与原文；否则保留。

    ``deterministic_only=True``：调用方（如 Chat 管理员任务）已经完成角色与确认校验，
    只按确定性门禁结论执行，不再嵌套一轮 LLM 循环——门禁才是否决权，模型只能拒绝、不能扩大删除。
    """
    settings = get_settings()
    if use_agent is False or not settings.irrelevant_cleanup_enabled:
        return {"deleted": False, "reason": "无关政策清理未启用"}

    verdict = assess_hsbc_impact(db, policy, assessment)
    if verdict["verdict"] != "none":
        return {
            "deleted": False,
            "reason": "政策与汇丰存在潜在关联，保留",
            "verdict": verdict,
        }

    if deterministic_only:
        reason = "确定性门禁判定对汇丰完全没有影响，已删除政策与原文"
        info = delete_policy_and_document(db, policy, reason=reason, actor=actor)
        if commit:
            db.commit()
            _remove_attachment_files(info.get("attachments") or [])
        return {
            "deleted": True,
            "policy_id": info["policy_id"],
            "document_id": info.get("document_id"),
            "reason": reason,
            "verdict": verdict,
        }

    from app.agent.runner import run_cleanup_agent
    from app.agent.skills import IRRELEVANT_CLEANUP
    from app.agent.tools import AgentContext

    ctx = AgentContext(db=db, policy=policy, assessment=assessment, base_payload={})
    result = run_cleanup_agent(ctx, skill=IRRELEVANT_CLEANUP)
    if not result.get("deleted"):
        return {"deleted": False, "reason": result.get("reason") or "Agent 判定保留", "verdict": verdict, "trace": result.get("trace")}

    deleted = result.get("deletion") or {}
    if commit:
        db.commit()
        _remove_attachment_files(deleted.get("attachments") or [])
    return {
        "deleted": True,
        "policy_id": deleted.get("policy_id") or policy.id,
        "document_id": deleted.get("document_id"),
        "reason": result.get("reason") or "AI Agent 判定对汇丰无影响，已删除政策与原文",
        "verdict": verdict,
        "trace": result.get("trace"),
    }

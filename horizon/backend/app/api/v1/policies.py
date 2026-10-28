"""政策列表/详情/分发拦截。完整实现随 Phase 2/3 补齐；分发 409 硬规则已在此生效。"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.api.v1.schemas import Page, PolicyOut
from app.core.errors import ApiError, not_found, not_approved
from app.core.security import get_demo_role, require_api_key, require_roles
from app.db.models import Assessment, AuditLog, Document, Policy, ReviewDecision, ReviewTask, ScopeJudgement
from app.db.session import get_db
from app.domain import state_machine
from app.domain.policy_admin import delete_policy

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_api_key)])


def _policy_filters(
    stmt,
    *,
    q: str | None,
    status: str | None,
    priority: str | None,
    jurisdiction: str | None,
    theme: str | None,
    scope: str | None,
    fetched: str | None,
    role: str,
):
    if q:
        search_pattern = f"%{q}%"
        stmt = stmt.where(
            (Policy.title.ilike(search_pattern)) |
            (Policy.issuing_body.ilike(search_pattern)) |
            (Policy.summary_zh.ilike(search_pattern))
        )
    if role == "consumer":
        stmt = stmt.where(Policy.status == "published")
    if status:
        statuses = [value.strip() for value in status.split(",") if value.strip()]
        stmt = stmt.where(Policy.status.in_(statuses))
    if priority:
        priorities = [value.strip() for value in priority.split(",") if value.strip()]
        stmt = stmt.where(Policy.priority.in_(priorities))
    if jurisdiction:
        stmt = stmt.where(Policy.jurisdiction == jurisdiction)
    if theme:
        # themes 以 JSON 文本存储，中文可能被序列化成 \uXXXX 转义，两种写法都要匹配
        column = cast(Policy.themes, Text)
        escaped = json.dumps(theme, ensure_ascii=True)[1:-1]
        stmt = stmt.where(or_(column.like(f"%{theme}%"), column.like(f"%{escaped}%")))
    if scope:
        stmt = stmt.where(Policy.target_entity_status == scope)
    if fetched == "today":
        today_start = datetime.now(ZoneInfo("Asia/Hong_Kong")).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).astimezone(timezone.utc)
        stmt = stmt.join(Document, Policy.document_id == Document.id).where(Document.fetched_at >= today_start)
    return stmt


def _policy_view(db: Session, policy: Policy) -> dict:
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    review_completed_at = db.scalar(
        select(func.max(ReviewDecision.created_at))
        .join(ReviewTask, ReviewDecision.task_id == ReviewTask.id)
        .where(ReviewTask.policy_id == policy.id, ReviewDecision.action == "approve")
    )
    dispatched_at = db.scalar(
        select(func.max(AuditLog.at)).where(
            AuditLog.object_type == "policy",
            AuditLog.object_id == policy.id,
            AuditLog.action == "dispatch",
        )
    )
    return {
        **PolicyOut.model_validate(policy).model_dump(),
        "impacted_domains": (assessment.affected.get("business_lines", []) if assessment else []),
        "review_completed_at": review_completed_at,
        "dispatched_at": dispatched_at,
    }


@router.get("", response_model=Page[PolicyOut])
def list_policies(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    jurisdiction: str | None = None,
    theme: str | None = None,
    scope: str | None = None,
    fetched: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
):
    filters = {
        "q": q, "status": status, "priority": priority, "jurisdiction": jurisdiction,
        "theme": theme, "scope": scope, "fetched": fetched, "role": role,
    }
    stmt = _policy_filters(select(Policy), **filters).order_by(Policy.published_at.desc().nullslast())
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    count_stmt = _policy_filters(select(func.count(Policy.id)), **filters)
    total = db.execute(count_stmt).scalar() or 0
    return Page(
        items=[_policy_view(db, policy) for policy in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{policy_id}")
def get_policy(policy_id: str, db: Session = Depends(get_db), role: str = Depends(get_demo_role)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if role == "consumer" and policy.status != "published":
        raise not_found("政策", policy_id)
    review_tasks = [] if role == "consumer" else db.scalars(
        select(ReviewTask).where(ReviewTask.policy_id == policy.id).order_by(ReviewTask.created_at)
    ).all()
    return {
        **_policy_view(db, policy),
        "review_tasks": [
            {
                "id": task.id,
                "level": task.level,
                "assignee": task.assignee,
                "status": task.status,
                "sla_due_at": task.sla_due_at,
                "created_at": task.created_at,
                "decisions": [
                    {
                        "actor": decision.actor,
                        "action": decision.action,
                        "reason_code": decision.reason_code,
                        "note": decision.note,
                        "created_at": decision.created_at,
                    }
                    for decision in task.decisions
                ],
            }
            for task in review_tasks
        ],
        "assessments": [
            {
                "id": a.id,
                "scores": a.scores,
                "direction": a.direction,
                "score_total": a.score_total,
                "priority": a.priority,
                "transmission_chain": a.transmission_chain,
                "affected": a.affected,
                "recommended_actions": a.recommended_actions,
                "case_links": a.case_links,
                "confidence": a.confidence,
                "model": a.model,
                "prompt_version": a.prompt_version,
            }
            for a in policy.assessments
        ],
        "evidence": [
            {
                "id": e.id,
                "document_id": e.document_id,
                "span_start": e.span_start,
                "span_end": e.span_end,
                "quote": e.quote,
                "field_name": e.field_name,
            }
            for e in policy.evidence_items
        ],
        "scope_judgements": [
            {
                "entity_id": j.entity_id,
                "result": j.result,
                "rule_hits": j.rule_hits,
                "llm_reason": j.llm_reason,
                "conflict": j.conflict,
            }
            for j in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == policy.id)).all()
        ],
        "document": (
            {
                "id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "lang": doc.lang,
                "published_at": doc.published_at,
                "content_text": doc.content_text,
                "attachments": doc.attachments,
            }
            if (doc := db.get(Document, policy.document_id))
            else None
        ),
        "url": (db.get(Document, policy.document_id).url if db.get(Document, policy.document_id) else ""),
    }


@router.post("/{policy_id}/analyze", status_code=202)
def analyze_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
):
    """触发/重跑 AI 分析（同步执行；MVP 单机可接受，Phase 5 改异步任务）。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    from app.jobs.analyze_job import analyze_document

    doc = db.get(Document, policy.document_id)
    if not doc:
        raise ApiError("DOC_MISSING", "政策关联文档缺失", 500)
    refreshed = analyze_document(db, doc)
    if refreshed is None:
        raise ApiError("ANALYZE_SKIPPED", "该文档不再满足分析条件（非金融政策/无正文）", 422)
    return {"status": "ok", "policy_id": refreshed.id, "priority": refreshed.priority,
            "score_total": refreshed.score_total, "policy_status": refreshed.status}


@router.post("/{policy_id}/dispatch")
def dispatch_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("publisher")),
):
    """人审不可绕过：非 approved 一律 409；approved → published → Notifier 分发。"""
    from app.domain import review as review_domain

    return review_domain.dispatch_policy(db, policy_id, actor=actor)


@router.delete("/{policy_id}")
def remove_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin")),
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    document_id = policy.document_id
    delete_policy(db, policy, actor=actor)
    return {"status": "ok", "policy_id": policy_id, "document_id": document_id, "document_retained": True}


@router.post("/{policy_id}/restore")
def restore_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin", "analyst")),
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if policy.target_entity_status != "low":
        raise ApiError("NOT_LOW", "该政策非低相关性", 422)
    if not state_machine.can_transition(policy.status, "pending_review"):
        raise ApiError(
            "INVALID_TRANSITION", f"政策当前状态为 {policy.status}，不能恢复为待审核", 409,
            {"from": policy.status, "to": "pending_review"},
        )
    from app.domain import review as review_domain

    policy.target_entity_status = "high"
    review_domain.submit_review(
        db, policy_id, level=1, assignee="analyst.default", actor=actor, note="恢复低相关政策",
    )
    return {"status": "ok", "policy_id": policy.id, "target_entity_status": policy.target_entity_status, "policy_status": policy.status}

"""政策列表/详情/分发拦截。完整实现随 Phase 2/3 补齐；分发 409 硬规则已在此生效。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas import Page, PolicyOut
from app.core.errors import ApiError, not_found, not_approved
from app.core.security import require_api_key
from app.db.models import Document, Policy, ScopeJudgement
from app.db.session import get_db
from app.domain import state_machine

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=Page[PolicyOut])
def list_policies(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    priority: str | None = None,
    jurisdiction: str | None = None,
    theme: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Policy).order_by(Policy.published_at.desc().nullslast())
    if status:
        stmt = stmt.where(Policy.status == status)
    if priority:
        stmt = stmt.where(Policy.priority == priority)
    if jurisdiction:
        stmt = stmt.where(Policy.jurisdiction == jurisdiction)
    if theme:
        stmt = stmt.where(Policy.themes.contains(theme))
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.query(Policy).count()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{policy_id}")
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    return {
        **PolicyOut.model_validate(policy).model_dump(),
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
def analyze_policy(policy_id: str, db: Session = Depends(get_db)):
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
def dispatch_policy(policy_id: str, db: Session = Depends(get_db), actor: str = Depends(require_api_key)):
    """人审不可绕过：非 approved 一律 409；approved → published → Notifier 分发。"""
    from app.domain import review as review_domain

    return review_domain.dispatch_policy(db, policy_id, actor=actor)

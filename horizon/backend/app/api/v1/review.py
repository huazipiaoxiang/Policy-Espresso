"""审核台 API（04 §4.2）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.core.security import require_api_key, require_roles
from app.db.models import Assessment, ConsumerReport, Evidence, Policy, ReviewDecision, ReviewTask, ScopeJudgement
from app.db.session import get_db
from app.domain import review as review_domain
from app.domain.consumer_impact import customer_impact_rows, matched_customers

router = APIRouter(tags=["review"], dependencies=[Depends(require_api_key)])


class SubmitBody(BaseModel):
    level: int = 1
    assignee: str = "analyst.default"
    note: str = ""


class DecisionBody(BaseModel):
    action: str  # approve/reject/request_info
    reason_code: str | None = None
    note: str = ""
    field_diffs: dict | None = None


class BatchBody(BaseModel):
    task_ids: list[str]
    action: str  # approve_p3 / mark_duplicate


def _task_view(task: ReviewTask, policy: Policy | None) -> dict:
    return {
        "id": task.id,
        "policy_id": task.policy_id,
        "policy_title": policy.title if policy else "",
        "priority": policy.priority if policy else "",
        "score_total": policy.score_total if policy else 0,
        "level": task.level,
        "assignee": task.assignee,
        "status": task.status,
        "sla_due_at": task.sla_due_at,
        "created_at": task.created_at,
        "target_entity_status": policy.target_entity_status if policy else "",
        "foreign_bank_differential": policy.foreign_bank_differential if policy else False,
    }


@router.get("/review-tasks")
def list_review_tasks(
    status: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(require_roles("processor")),
):
    stmt = select(ReviewTask).order_by(ReviewTask.sla_due_at.asc().nullslast())
    if status:
        stmt = stmt.where(ReviewTask.status == status)
    else:
        stmt = stmt.where(ReviewTask.status.in_(["pending", "claimed"]))
    tasks = db.scalars(stmt).all()
    return {"items": [_task_view(t, db.get(Policy, t.policy_id)) for t in tasks]}


@router.get("/consumer-reports")
def list_consumer_reports(
    status: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(require_roles("processor")),
):
    """政策运营专员查看 consumer 发来的影响报告（结构化解读 + 政策影响到的全部客户）。

    报告本体只覆盖发送者名下客户，运营专员还需要看到该政策影响到的所有客户，
    因此这里按政策业务线在全量合成客户中重新匹配，并把完整名单一并返回。
    """
    stmt = select(ConsumerReport).order_by(ConsumerReport.created_at.desc())
    if status:
        stmt = stmt.where(ConsumerReport.status == status)
    reports = db.scalars(stmt).all()
    items = []
    for r in reports:
        policy = db.get(Policy, r.policy_id)
        assessment = db.scalars(
            select(Assessment).where(Assessment.policy_id == r.policy_id)
        ).first()
        business_lines = (assessment.affected.get("business_lines", []) if assessment else []) or []
        if business_lines:
            rows = customer_impact_rows(
                matched_customers(business_lines),
                assessment.scores if assessment else None,
                direction=assessment.direction if assessment else None,
            )
            scope_note = f"按政策业务线（{'、'.join(business_lines)}）匹配全部客户"
        else:
            # 政策未标注业务线时，退回使用者报告中已识别的客户，避免把全部客户都算作受影响
            rows = (r.report or {}).get("affected_customers", []) or []
            scope_note = "政策未标注业务线，展示使用者报告中的客户"
        items.append({
            "id": r.id,
            "policy_id": r.policy_id,
            "policy_title": policy.title if policy else "",
            "policy_priority": policy.priority if policy else "",
            "actor": r.actor,
            "report": r.report,
            "status": r.status,
            "created_at": r.created_at,
            "affected_customers": rows,
            "affected_customer_count": len(rows),
            "affected_scope_note": scope_note,
        })
    return {"items": items}


@router.post("/consumer-reports/{report_id}/process")
def process_consumer_report(
    report_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor")),
):
    """运营专员跟进使用者影响报告：标记为已跟进，政策随之进入「已跟进的政策」。"""
    report = db.get(ConsumerReport, report_id)
    if not report:
        raise not_found("影响报告", report_id)
    if report.status != "processed":
        report.status = "processed"
        db.commit()
        db.refresh(report)
    return {"id": report.id, "policy_id": report.policy_id, "status": report.status}


@router.get("/review-tasks/{task_id}")
def get_review_task(
    task_id: str,
    db: Session = Depends(get_db),
    role: str = Depends(require_roles("processor")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    policy = db.get(Policy, task.policy_id)
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == task.policy_id)).first()
    evidence_count = db.query(Evidence).filter(Evidence.policy_id == task.policy_id).count()
    scope_conflict = any(
        j.conflict
        for j in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == task.policy_id)).all()
    )
    decisions = db.scalars(
        select(ReviewDecision)
        .join(ReviewTask, ReviewDecision.task_id == ReviewTask.id)
        .where(ReviewTask.policy_id == task.policy_id)
    ).all()
    return {
        "task": _task_view(task, policy),
        "policy": {
            "id": policy.id, "title": policy.title, "summary_zh": policy.summary_zh,
            "priority": policy.priority, "status": policy.status,
            "target_entity_status": policy.target_entity_status,
            "foreign_bank_differential": policy.foreign_bank_differential,
            "applicable_entities_text": policy.applicable_entities_text,
            "effective_at": policy.effective_at,
        },
        "assessment": (
            {
                "scores": assessment.scores, "direction": assessment.direction,
                "score_total": assessment.score_total, "priority": assessment.priority,
                "transmission_chain": assessment.transmission_chain,
                "affected": assessment.affected,
                "recommended_actions": assessment.recommended_actions,
                "case_links": assessment.case_links, "confidence": assessment.confidence,
                "model": assessment.model,
            }
            if assessment else None
        ),
        "evidence_count": evidence_count,
        "scope_conflict": scope_conflict,
        "challenges": review_domain.challenge_assessment(policy, assessment, evidence_count, scope_conflict),
        "previous_decisions": [
            {"actor": d.actor, "action": d.action, "reason_code": d.reason_code,
             "note": d.note, "created_at": d.created_at}
            for d in decisions
        ],
    }


@router.post("/policies/{policy_id}/submit-review")
def submit_review(
    policy_id: str,
    body: SubmitBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("processor", "admin")),
):
    if body.level != 1:
        raise ApiError("FORBIDDEN", "初级审核员只能提交一级审核任务", 403)
    task = review_domain.submit_review(
        db, policy_id, level=1, assignee=actor, actor=actor, note=body.note,
    )
    return {"task_id": task.id, "sla_due_at": task.sla_due_at, "status": task.status}


@router.post("/review-tasks/{task_id}/claim")
def claim_task(
    task_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("processor")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    task = review_domain.claim_task(db, task_id, actor=actor)
    return {"task_id": task.id, "status": task.status, "assignee": task.assignee}


@router.post("/review-tasks/{task_id}/decision")
def decide(
    task_id: str,
    body: DecisionBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("processor")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    return review_domain.decide(
        db, task_id, actor=actor, action=body.action,
        reason_code=body.reason_code, note=body.note, field_diffs=body.field_diffs,
    )


@router.post("/review-tasks/batch")
def batch_decide(
    body: BatchBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("processor")),
):
    return review_domain.batch_decide(db, body.task_ids, actor=actor, action=body.action)

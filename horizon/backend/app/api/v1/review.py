"""审核台 API（04 §4.2）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.core.security import require_api_key, require_roles
from app.db.models import Assessment, Evidence, Policy, ReviewDecision, ReviewTask, ScopeJudgement
from app.db.session import get_db
from app.domain import review as review_domain

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
    role: str = Depends(require_roles("analyst", "approver", "publisher")),
):
    stmt = select(ReviewTask).order_by(ReviewTask.sla_due_at.asc().nullslast())
    if status:
        stmt = stmt.where(ReviewTask.status == status)
    else:
        stmt = stmt.where(ReviewTask.status.in_(["pending", "claimed"]))
    if role == "analyst":
        stmt = stmt.where(ReviewTask.level == 1)
    elif role == "approver":
        stmt = stmt.where(ReviewTask.level == 2)
    tasks = db.scalars(stmt).all()
    return {"items": [_task_view(t, db.get(Policy, t.policy_id)) for t in tasks]}


@router.get("/review-tasks/{task_id}")
def get_review_task(
    task_id: str,
    db: Session = Depends(get_db),
    role: str = Depends(require_roles("analyst", "approver", "publisher")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    if (role == "analyst" and task.level != 1) or (role == "approver" and task.level != 2):
        raise ApiError("FORBIDDEN", "当前角色不能查看该级别的审核任务", 403)
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
    role: str = Depends(require_roles("analyst")),
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
    role: str = Depends(require_roles("analyst", "approver")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    if (role == "analyst" and task.level != 1) or (role == "approver" and task.level != 2):
        raise ApiError("FORBIDDEN", "当前角色不能领取该级别的审核任务", 403)
    task = review_domain.claim_task(db, task_id, actor=actor)
    return {"task_id": task.id, "status": task.status, "assignee": task.assignee}


@router.post("/review-tasks/{task_id}/decision")
def decide(
    task_id: str,
    body: DecisionBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("analyst", "approver")),
):
    task = db.get(ReviewTask, task_id)
    if not task:
        raise not_found("审核任务", task_id)
    if (role == "analyst" and task.level != 1) or (role == "approver" and task.level != 2):
        raise ApiError("FORBIDDEN", "当前角色不能处理该级别的审核任务", 403)
    return review_domain.decide(
        db, task_id, actor=actor, action=body.action,
        reason_code=body.reason_code, note=body.note, field_diffs=body.field_diffs,
    )


@router.post("/review-tasks/batch")
def batch_decide(
    body: BatchBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    role: str = Depends(require_roles("analyst")),
):
    return review_domain.batch_decide(db, body.task_ids, actor=actor, action=body.action)

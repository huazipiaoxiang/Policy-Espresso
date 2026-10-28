from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert, Assessment, AuditLog, Dispatch, Evidence, Policy, PolicyCaseLink,
    ReviewDecision, ReviewTask, ScopeJudgement,
)


def delete_policy_records(db: Session, policy: Policy) -> None:
    policy_id = policy.id
    assessment_ids = list(db.scalars(select(Assessment.id).where(Assessment.policy_id == policy_id)))
    alert_ids = list(db.scalars(select(Alert.id).where(Alert.assessment_id.in_(assessment_ids)))) if assessment_ids else []
    task_ids = list(db.scalars(select(ReviewTask.id).where(ReviewTask.policy_id == policy_id)))

    if alert_ids:
        db.query(Dispatch).filter(Dispatch.alert_id.in_(alert_ids)).delete(synchronize_session=False)
        db.query(Alert).filter(Alert.id.in_(alert_ids)).delete(synchronize_session=False)
    db.query(Evidence).filter(Evidence.policy_id == policy_id).delete(synchronize_session=False)
    if task_ids:
        db.query(ReviewDecision).filter(ReviewDecision.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(ReviewTask).filter(ReviewTask.id.in_(task_ids)).delete(synchronize_session=False)
    db.query(ScopeJudgement).filter(ScopeJudgement.policy_id == policy_id).delete(synchronize_session=False)
    db.query(PolicyCaseLink).filter(PolicyCaseLink.policy_id == policy_id).delete(synchronize_session=False)
    if assessment_ids:
        db.query(Assessment).filter(Assessment.id.in_(assessment_ids)).delete(synchronize_session=False)
    db.delete(policy)


def delete_policy(db: Session, policy: Policy, *, actor: str) -> None:
    before = {
        "title": policy.title,
        "status": policy.status,
        "document_id": policy.document_id,
    }
    delete_policy_records(db, policy)
    db.add(AuditLog(
        actor=actor, action="delete_policy", object_type="policy", object_id=policy.id,
        before=before, after={"deleted": True, "document_retained": True},
        reason="管理员删除政策，保留原始文档",
    ))
    db.commit()

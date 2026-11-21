from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert, Assessment, AuditLog, ConsumerReport, Dispatch, DocumentChunk, Evidence, Feedback,
    Policy, PolicyCaseLink, PolicyPreprocess, ReviewDecision, ReviewTask, ScopeJudgement,
)


def delete_policy_records(db: Session, policy: Policy) -> None:
    """删除政策及其关联记录（保留原文）。

    用 SQLAlchemy Core 的 ``delete()`` 显式按外键依赖顺序删除，并用 Core 语句删除
    policy 本身——绕过 ORM 级联。否则 ``db.delete(policy)`` 会触发 relationship 级联，
    在 PostgreSQL 上对已删除的子行再发「解除关联 UPDATE」或二次 DELETE，可能抛 500。
    """
    policy_id = policy.id
    assessment_ids = list(db.scalars(select(Assessment.id).where(Assessment.policy_id == policy_id)))
    alert_ids = list(db.scalars(select(Alert.id).where(Alert.assessment_id.in_(assessment_ids)))) if assessment_ids else []
    task_ids = list(db.scalars(select(ReviewTask.id).where(ReviewTask.policy_id == policy_id)))

    if alert_ids:
        db.execute(sa_delete(Dispatch).where(Dispatch.alert_id.in_(alert_ids)))
        db.execute(sa_delete(Alert).where(Alert.id.in_(alert_ids)))
    db.execute(sa_delete(Evidence).where(Evidence.policy_id == policy_id))
    if task_ids:
        db.execute(sa_delete(ReviewDecision).where(ReviewDecision.task_id.in_(task_ids)))
        db.execute(sa_delete(ReviewTask).where(ReviewTask.id.in_(task_ids)))
    db.execute(sa_delete(ScopeJudgement).where(ScopeJudgement.policy_id == policy_id))
    db.execute(sa_delete(PolicyCaseLink).where(PolicyCaseLink.policy_id == policy_id))
    # 反馈、使用者影响报告与向量切片也引用 policy_id（外键），一并清理，否则删除 Policy 时外键约束报错
    db.execute(sa_delete(Feedback).where(Feedback.policy_id == policy_id))
    db.execute(sa_delete(ConsumerReport).where(ConsumerReport.policy_id == policy_id))
    db.execute(sa_delete(DocumentChunk).where(DocumentChunk.policy_id == policy_id))
    db.execute(sa_delete(PolicyPreprocess).where(PolicyPreprocess.policy_id == policy_id))
    if assessment_ids:
        db.execute(sa_delete(Assessment).where(Assessment.id.in_(assessment_ids)))
    # 直接以 Core 语句删除 policy，避免 ORM 级联副作用
    db.execute(sa_delete(Policy).where(Policy.id == policy_id))


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

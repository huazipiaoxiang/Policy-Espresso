"""审核工作流（02 §5.4 / 01 Phase 3）。

- 提交审核：强制字段校验（证据 ≥1、置信度、影响范围、建议动作、摘要）
- 领取：防并发双审（pending → claimed）
- 决策：approve / reject（必填原因码）/ request_info
- 双签：P0/P1 需两级（分析师 + 合规/业务主管）；P2/P3 单签
- 分发：仅 approved → published 后可分发（409 硬规则）
- 所有动作写 audit_log；驳回后不得直接发布
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models import (
    Alert, Assessment, AuditLog, Dispatch, Evidence, Policy, ReviewDecision, ReviewTask,
)
from app.domain import state_machine

log = get_logger("domain.review")

SLA_HOURS = {"P0": 4, "P1": 24, "P2": 72, "P3": 72}


def required_fields_missing(policy: Policy, assessment: Assessment | None, evidence_count: int) -> list[str]:
    """提交审核前的强制字段校验（02 §5.4）。"""
    missing: list[str] = []
    if evidence_count < 1:
        missing.append("evidence")
    if not policy.confidence or policy.confidence <= 0:
        missing.append("confidence")
    if assessment is None:
        missing.append("assessment")
    else:
        if not assessment.affected.get("business_lines"):
            missing.append("affected")
        if not assessment.recommended_actions:
            missing.append("recommended_actions")
    if not policy.summary_zh:
        missing.append("summary_zh")
    return missing


def submit_review(db: Session, policy_id: str, *, level: int, assignee: str, actor: str, note: str = "") -> ReviewTask:
    """提交审核（校验必填 → pending_review → 建任务）。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise ApiError("NOT_FOUND", "政策不存在", 404, {"id": policy_id})
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first()
    evidence_count = db.query(Evidence).filter(Evidence.policy_id == policy_id).count()
    missing = required_fields_missing(policy, assessment, evidence_count)
    if missing:
        raise ApiError("MISSING_REQUIRED", "缺少以下必填项，无法提交审核", 422, {"missing": missing})

    before = policy.status
    policy.status = state_machine.transition(before, "pending_review")
    task = ReviewTask(
        policy_id=policy_id, level=level, assignee=assignee,
        sla_due_at=datetime.now(timezone.utc) + timedelta(hours=SLA_HOURS.get(policy.priority, 72)),
        status="pending",
    )
    db.add(task)
    db.add(AuditLog(actor=actor, action="submit_review", object_type="policy", object_id=policy_id,
                    before={"status": before}, after={"status": policy.status, "level": level}, reason=note))
    db.commit()
    db.refresh(task)
    return task


def claim_task(db: Session, task_id: str, actor: str) -> ReviewTask:
    """领取任务（防并发双审：仅 pending 可领）。"""
    task = db.get(ReviewTask, task_id)
    if not task:
        raise ApiError("NOT_FOUND", "审核任务不存在", 404, {"id": task_id})
    if task.status != "pending":
        raise ApiError("TASK_NOT_CLAIMABLE", f"任务状态为 {task.status}，不可领取", 409, {"task_id": task_id})
    before = task.status
    task.status = "claimed"
    task.assignee = actor
    policy = db.get(Policy, task.policy_id)
    if policy and policy.status == "pending_review":
        policy_before = policy.status
        policy.status = state_machine.transition(policy.status, "in_review")
        db.add(AuditLog(actor=actor, action="claim_task", object_type="policy", object_id=policy.id,
                        before={"status": policy_before}, after={"status": policy.status}))
    db.add(AuditLog(actor=actor, action="claim_task", object_type="review_task", object_id=task_id,
                    before={"status": before}, after={"status": task.status}))
    db.commit()
    db.refresh(task)
    return task


def decide(
    db: Session,
    task_id: str,
    *,
    actor: str,
    action: str,
    reason_code: str | None = None,
    note: str = "",
    field_diffs: dict | None = None,
) -> dict:
    """审核决策。approve：双签规则下生成下一级任务或直接 approved；reject：必填原因码；request_info：needs_info。"""
    task = db.get(ReviewTask, task_id)
    if not task:
        raise ApiError("NOT_FOUND", "审核任务不存在", 404, {"id": task_id})
    if action not in ("approve", "reject", "request_info"):
        raise ApiError("BAD_ACTION", "action 须为 approve/reject/request_info", 422)
    if action == "reject" and (not reason_code or reason_code not in state_machine.REJECT_REASON_CODES):
        raise ApiError("REASON_REQUIRED", "驳回必须选择原因码", 422,
                       {"allowed": sorted(state_machine.REJECT_REASON_CODES)})

    policy = db.get(Policy, task.policy_id)
    if not policy:
        raise ApiError("NOT_FOUND", "政策不存在", 404, {"id": task.policy_id})
    before_status = policy.status
    # 未领取即决策（批量场景）：先自动进入 in_review，保证状态机合法
    if before_status == "pending_review":
        before_status = state_machine.transition(before_status, "in_review")
        policy.status = before_status

    if action == "approve":
        task.status = "approved"
        levels_required = state_machine.required_review_levels(policy.priority)
        approved_count = (
            db.query(ReviewDecision)
            .join(ReviewTask, ReviewDecision.task_id == ReviewTask.id)
            .filter(ReviewTask.policy_id == policy.id, ReviewDecision.action == "approve")
            .count()
            + 1
        )
        if approved_count < levels_required:
            # 双签未完成：生成下一级任务，policy 留在 in_review
            next_task = ReviewTask(
                policy_id=policy.id, level=task.level + 1, assignee="reviewer.l2",
                sla_due_at=datetime.now(timezone.utc) + timedelta(hours=SLA_HOURS.get(policy.priority, 72)),
                status="pending",
            )
            db.add(next_task)
            new_status = before_status  # 仍在审
        else:
            new_status = state_machine.transition(before_status, "approved")
            policy.status = new_status
    elif action == "reject":
        task.status = "rejected"
        new_status = state_machine.transition(before_status, "rejected")
        policy.status = new_status
    else:  # request_info
        task.status = "needs_info"
        new_status = state_machine.transition(before_status, "needs_info")
        policy.status = new_status

    db.add(ReviewDecision(
        task_id=task_id, actor=actor, action=action, reason_code=reason_code,
        note=note, field_diffs=field_diffs or {},
    ))
    db.add(AuditLog(
        actor=actor, action=f"review_{action}", object_type="policy", object_id=policy.id,
        before={"status": before_status, "task_status": "pending/claimed"},
        after={"status": new_status, "task_status": task.status},
        reason=reason_code or note, ip="",
    ))
    db.commit()
    return {"task_id": task_id, "action": action, "policy_status": new_status,
            "reason_code": reason_code, "actor": actor}


def batch_decide(db: Session, task_ids: list[str], *, actor: str, action: str, reason_code: str | None = None) -> dict:
    """批量操作：仅允许批量"通过 P3"与批量"标记重复"（08 §3.3）。"""
    if action not in ("approve_p3", "mark_duplicate"):
        raise ApiError("BATCH_NOT_ALLOWED", "批量仅支持 approve_p3 / mark_duplicate", 422)
    ok, skipped = [], []
    for task_id in task_ids:
        task = db.get(ReviewTask, task_id)
        if not task:
            skipped.append({"task_id": task_id, "reason": "不存在"})
            continue
        policy = db.get(Policy, task.policy_id)
        if action == "approve_p3" and policy.priority != "P3":
            skipped.append({"task_id": task_id, "reason": f"优先级 {policy.priority} 不允许批量通过"})
            continue
        try:
            decide(db, task_id, actor=actor,
                   action="approve" if action == "approve_p3" else "reject",
                   reason_code=None if action == "approve_p3" else "duplicate")
            ok.append(task_id)
        except ApiError as e:
            skipped.append({"task_id": task_id, "reason": e.message})
    return {"ok": ok, "skipped": skipped}


def dispatch_policy(db: Session, policy_id: str, actor: str) -> dict:
    """分发：非 approved → 409；approved → published（留痕）→ 建 Alert + Dispatch。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise ApiError("NOT_FOUND", "政策不存在", 404, {"id": policy_id})
    if policy.status != "approved":
        raise ApiError("NOT_APPROVED", "内容未通过人工审核，禁止分发", 409,
                       {"policy_id": policy_id, "current_status": policy.status})

    before = policy.status
    policy.status = state_machine.transition(before, "published")
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first()
    alert = Alert(
        assessment_id=assessment.id if assessment else None,
        title=f"政策预警 · {policy.title}",
        body_md=f"# {policy.title}\n\n{policy.summary_zh}\n\n（完整评估见政策详情页）",
        channel_scope={"default": "inapp"},
        status="approved",
    )
    db.add(alert)
    db.flush()
    results = []
    for notifier in get_notifiers():
        result = notifier.send(alert)
        db.add(Dispatch(alert_id=alert.id, channel=notifier.name, target=result.get("target", "default"),
                        sent_at=datetime.now(timezone.utc), result=result))
        results.append({"channel": notifier.name, **result})
    db.add(AuditLog(actor=actor, action="dispatch", object_type="policy", object_id=policy_id,
                    before={"status": before}, after={"status": policy.status, "alert_id": alert.id},
                    reason="人工审核通过后分发"))
    db.commit()
    return {"policy_id": policy_id, "alert_id": alert.id, "status": policy.status, "channels": results}


def challenge_assessment(policy: Policy, assessment: Assessment | None, evidence_count: int,
                         scope_conflict: bool) -> list[dict]:
    """审核台"AI 质疑"面板（08 §3.3）：规则版红队质疑，防橡皮图章。

    P7 的 LLM 版为可选项；此处用确定性规则给出最可能出错的 3 处。
    """
    issues: list[dict] = []
    if scope_conflict:
        issues.append({"risk": "high", "issue": "规则通道与 LLM 对适用范围判定不一致，需人工复核原文",
                       "suggestion": "以原文适用主体段落为准，修正判定或记入 ambiguity"})
    if assessment:
        null_dims = [d for d, v in assessment.scores.items() if (v or {}).get("score") is None]
        if null_dims:
            issues.append({"risk": "mid", "issue": f"{len(null_dims)} 个评分维度无证据支撑：{', '.join(null_dims)}",
                           "suggestion": "补充证据或将这些维度结论降级"})
        if policy.effective_at and policy.effective_at < datetime.now(timezone.utc) and assessment.priority in ("P0", "P1"):
            issues.append({"risk": "mid", "issue": "生效日已过但仍为高优先级，urgency 评分可能虚高",
                           "suggestion": "核对 urgency 与时间窗，动作改为'评估合规现状'"})
    if evidence_count == 0:
        issues.append({"risk": "high", "issue": "该政策卡没有任何可定位证据", "suggestion": "无证据不出结论，建议打回补充"})
    if not issues:
        issues.append({"risk": "low", "issue": "未发现显著问题", "suggestion": "仍建议抽查适用主体原文一句"})
    return issues[:3]


def get_notifiers():
    from app.notifications import get_notifiers as factory

    return factory()

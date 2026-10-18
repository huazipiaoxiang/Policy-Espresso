"""Phase 3 验收：审核流（双签/驳回/分发 409/审计链）+ Notifier 降级。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import Alert, Assessment, AuditLog, Document, Evidence, Policy, ReviewTask, Source
from app.db.session import SessionLocal

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gd_subsidy_policy.html"


def _make_policy(key: str = "default"):
    """灌入用例 1 样本并跑分析，返回 (policy_id, task_id)。"""
    from app.ingest.normalize import normalize_html
    from app.jobs.analyze_job import analyze_document
    from app.jobs.seed_job import seed_cases, seed_sources

    url = f"https://demo.local/p3-{key}"
    with SessionLocal() as db:
        seed_sources(db)
        seed_cases(db)
        src = db.query(Source).filter(Source.code == "gd_gov").first()
        html = FIXTURE.read_text(encoding="utf-8")
        norm = normalize_html(html, url, fallback_title="关于做好中小微企业贷款贴息工作的通知")
        doc = Document(
            source_id=src.id, url=url, canonical_url=url, title=norm.title,
            lang=norm.lang, published_at=norm.published_at, content_text=norm.content_text,
            content_hash=f"p3-{key}", status="new",
        )
        db.add(doc)
        db.commit()
        policy = analyze_document(db, db.get(Document, doc.id))
        task = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == policy.id)).first()
        return policy.id, task.id


def test_double_sign_dispatch_and_audit_chain(client):
    """P0 双签：一级通过→生成二级任务→二级通过才可分发；审计链完整。"""
    policy_id, task_id = _make_policy("double-sign")

    # 领取（防并发双审）
    r = client.post(f"/api/v1/review-tasks/{task_id}/claim")
    assert r.status_code == 200 and r.json()["status"] == "claimed"
    assert client.post(f"/api/v1/review-tasks/{task_id}/claim").status_code == 409  # 不可重复领取

    # 一级通过（P0 双签未完成 → 留 in_review + 二级任务）
    r = client.post(f"/api/v1/review-tasks/{task_id}/decision", json={"action": "approve"})
    assert r.status_code == 200 and r.json()["policy_status"] == "in_review"

    with SessionLocal() as db:
        assert db.get(Policy, policy_id).status == "in_review"
        l2 = db.scalars(
            select(ReviewTask).where(ReviewTask.policy_id == policy_id, ReviewTask.level == 2)
        ).first()
        assert l2 is not None, "双签必须生成二级任务"

    # 未完成双签 → 分发 409
    r = client.post(f"/api/v1/policies/{policy_id}/dispatch")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_APPROVED"

    # 二级通过 → approved
    client.post(f"/api/v1/review-tasks/{l2.id}/claim")
    r = client.post(f"/api/v1/review-tasks/{l2.id}/decision", json={"action": "approve"})
    assert r.json()["policy_status"] == "approved"

    # 分发 → published + Alert + Dispatch(inapp 降级)
    r = client.post(f"/api/v1/policies/{policy_id}/dispatch")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published"
    assert any(c["channel"] == "inapp" for c in body["channels"]), "未配置 webhook 时降级站内"

    with SessionLocal() as db:
        assert db.get(Policy, policy_id).status == "published"
        assert any(a.status == "approved" for a in db.scalars(select(Alert)).all())
        actions = [
            a.action for a in db.scalars(
                select(AuditLog).where(AuditLog.object_id == policy_id).order_by(AuditLog.at.asc())
            ).all()
        ]
        for expected in ("submit_review", "claim_task", "review_approve", "dispatch"):
            assert expected in actions, f"审计链缺少 {expected}: {actions}"


def test_reject_requires_reason_and_blocks_dispatch(client):
    """驳回必填原因码；驳回后不可直接分发。"""
    from app.domain import state_machine

    policy_id, task_id = _make_policy("reject")
    client.post(f"/api/v1/review-tasks/{task_id}/claim")

    r = client.post(f"/api/v1/review-tasks/{task_id}/decision", json={"action": "reject"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REASON_REQUIRED"

    r = client.post(
        f"/api/v1/review-tasks/{task_id}/decision",
        json={"action": "reject", "reason_code": "insufficient_evidence", "note": "证据不足"},
    )
    assert r.status_code == 200 and r.json()["policy_status"] == "rejected"

    assert client.post(f"/api/v1/policies/{policy_id}/dispatch").status_code == 409

    with SessionLocal() as db:
        assert db.get(Policy, policy_id).status == "rejected"
        assert state_machine.can_transition("rejected", "draft")  # 重开路径存在（需原因）


def test_submit_review_requires_mandatory_fields(client):
    """强制字段缺失 → 422 MISSING_REQUIRED。"""
    policy_id, _ = _make_policy("missing-fields")
    with SessionLocal() as db:
        db.query(Evidence).filter(Evidence.policy_id == policy_id).delete()
        db.commit()

    r = client.post(f"/api/v1/policies/{policy_id}/submit-review", json={"level": 1})
    assert r.status_code == 422
    assert "evidence" in r.json()["error"]["detail"]["missing"]


def test_batch_mark_duplicate(client):
    """批量标记重复 → rejected(duplicate)。"""
    policy_id, task_id = _make_policy("batch-dup")
    r = client.post("/api/v1/review-tasks/batch", json={"task_ids": [task_id], "action": "mark_duplicate"})
    assert r.status_code == 200 and task_id in r.json()["ok"]

    with SessionLocal() as db:
        assert db.get(Policy, policy_id).status == "rejected"


def test_batch_rejects_non_p3_approve(client):
    """批量通过仅允许 P3。"""
    _, task_id = _make_policy("batch-p0")
    r = client.post("/api/v1/review-tasks/batch", json={"task_ids": [task_id], "action": "approve_p3"})
    assert r.status_code == 200
    assert r.json()["ok"] == [] and r.json()["skipped"]


def test_challenge_panel_flags_scope_conflict(client):
    """AI 质疑面板：双通道冲突必须高亮。"""
    from app.domain.review import challenge_assessment

    policy_id, _ = _make_policy("challenge")
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first()
        issues = challenge_assessment(policy, assessment, 3, scope_conflict=True)
        assert any(i["risk"] == "high" and "不一致" in i["issue"] for i in issues)


def test_audit_export_csv(client):
    """审计导出 CSV 可下载。"""
    policy_id, _ = _make_policy("export")
    r = client.get(f"/api/v1/admin/audit/export?object_id={policy_id}")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "submit_review" in r.text

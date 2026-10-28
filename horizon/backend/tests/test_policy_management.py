from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import (
    Alert, Assessment, AuditLog, Dispatch, Document, Evidence, Policy,
    ReviewDecision, ReviewTask, ScopeJudgement, Source,
)
from app.db.session import SessionLocal


def _policy_fixture(key: str) -> tuple[str, str, str]:
    with SessionLocal() as db:
        source = Source(
            code=f"source-{key}", name="测试来源", jurisdiction="HK", tier=1,
            adapter="manual", url=f"https://example.test/{key}",
        )
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id, url=f"https://example.test/{key}/doc",
            canonical_url=f"https://example.test/{key}/doc", title="测试政策",
            content_text="政策原文" * 30, content_hash=f"hash-{key}",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id, title="测试政策", status="approved", priority="P3",
            confidence=0.9, summary_zh="测试摘要",
        )
        db.add(policy)
        db.flush()
        assessment = Assessment(policy_id=policy.id, affected={"business_lines": ["RBWM"]})
        db.add(assessment)
        db.flush()
        alert = Alert(assessment_id=assessment.id, title="预警")
        db.add(alert)
        db.flush()
        db.add(Dispatch(alert_id=alert.id, channel="inapp"))
        task = ReviewTask(policy_id=policy.id, level=1, status="approved")
        db.add(task)
        db.flush()
        db.add(ReviewDecision(task_id=task.id, actor="demo.analyst", action="approve"))
        db.add(Evidence(
            policy_id=policy.id, document_id=doc.id, span_start=0, span_end=4, quote="政策原文",
        ))
        db.add(ScopeJudgement(policy_id=policy.id, entity_id="hsbc_hk", result="high"))
        db.commit()
        return policy.id, doc.id, alert.id


def test_policy_list_supports_high_priority_and_domains(client):
    policy_id, _, _ = _policy_fixture("list")
    response = client.get("/api/v1/policies", params={"priority": "P0,P1"})
    assert response.status_code == 200
    assert response.json()["total"] == 0

    response = client.get("/api/v1/policies", params={"q": "测试政策"})
    item = next(item for item in response.json()["items"] if item["id"] == policy_id)
    assert item["impacted_domains"] == ["RBWM"]


def test_policy_list_theme_filter_matches_chinese_names(client):
    """主题以 JSON 存储、中文会被转义成 \\uXXXX，按主题筛选必须命中而不是静默返回空列表。"""
    policy_id, _, _ = _policy_fixture("theme-filter")
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        policy.themes = ["人民币国际化", "跨境支付"]
        db.commit()

    for theme in ("人民币国际化", "跨境支付"):
        response = client.get("/api/v1/policies", params={"theme": theme})
        assert response.json()["total"] == 1, theme
        assert [item["id"] for item in response.json()["items"]] == [policy_id], theme

    assert client.get("/api/v1/policies", params={"theme": "绿色与转型金融"}).json()["total"] == 0


def test_delete_requires_admin_and_cleans_related_records(client):
    policy_id, document_id, alert_id = _policy_fixture("delete")
    assert client.delete(f"/api/v1/policies/{policy_id}").status_code == 403

    response = client.delete(
        f"/api/v1/policies/{policy_id}", headers={"X-Demo-Role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["document_retained"] is True

    with SessionLocal() as db:
        assert db.get(Policy, policy_id) is None
        assert db.get(Document, document_id) is not None
        assert db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first() is None
        assert db.scalars(select(ReviewTask).where(ReviewTask.policy_id == policy_id)).first() is None
        assert db.scalars(select(Evidence).where(Evidence.policy_id == policy_id)).first() is None
        assert db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == policy_id)).first() is None
        assert db.get(Alert, alert_id) is None
        assert db.scalars(select(Dispatch).where(Dispatch.alert_id == alert_id)).first() is None
        audit = db.scalars(select(AuditLog).where(
            AuditLog.object_id == policy_id, AuditLog.action == "delete_policy",
        )).first()
        assert audit is not None


def test_upload_requires_admin_and_reuses_analysis(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    monkeypatch.setattr("app.api.v1.documents.extract_upload", lambda path, suffix: "金融政策正文" * 30)

    def fake_analyze(db, doc):
        policy = Policy(document_id=doc.id, title=doc.title, status="ai_checked")
        db.add(policy)
        doc.status = "processed"
        db.commit()
        return policy

    monkeypatch.setattr("app.jobs.analyze_job.analyze_document", fake_analyze)
    files = {"file": ("policy.docx", b"unique-docx-content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    assert client.post("/api/v1/documents/upload", files=files).status_code == 403

    response = client.post(
        "/api/v1/documents/upload", files=files,
        data={"title": "上传政策", "jurisdiction": "HK"},
        headers={"X-Demo-Role": "admin"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "processed"
    assert body["policy_id"]
    assert body["processing_error"] == ""
    assert (tmp_path / "uploads" / f"{body['id']}.docx").exists()

    duplicate = client.post(
        "/api/v1/documents/upload", files=files,
        data={"jurisdiction": "HK"}, headers={"X-Demo-Role": "admin"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["detail"]["document_id"] == body["id"]


def test_upload_jurisdiction_marks_policy(client, monkeypatch, tmp_path):
    """手动上传没有数据源辖区，市场必须由上传人指定，否则政策库按市场筛选时看不到这条政策。"""
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    monkeypatch.setattr("app.api.v1.documents.extract_upload", lambda path, suffix: "金融政策正文" * 30)

    def fake_analyze(db, doc):
        policy = Policy(document_id=doc.id, title=doc.title, status="ai_checked")
        db.add(policy)
        doc.status = "processed"
        db.commit()
        return policy

    monkeypatch.setattr("app.jobs.analyze_job.analyze_document", fake_analyze)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("market.docx", b"unique-market-content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"title": "带市场的上传政策", "jurisdiction": "cn"},
        headers={"X-Demo-Role": "admin"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["jurisdiction"] == "CN"
    with SessionLocal() as db:
        assert db.get(Policy, body["policy_id"]).jurisdiction == "CN"

    missing = client.post(
        "/api/v1/documents/upload",
        files={"file": ("no-market.docx", b"no-market-content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers={"X-Demo-Role": "admin"},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "MISSING_JURISDICTION"

    invalid = client.post(
        "/api/v1/documents/upload",
        files={"file": ("bad-market.docx", b"bad-market-content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"jurisdiction": "US"}, headers={"X-Demo-Role": "admin"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_JURISDICTION"


def test_upload_records_publish_date(client, monkeypatch, tmp_path):
    """上传人填写的发布日期要落进原文记录，分析后才能带出政策日期，否则列表只能按收录时间排。"""
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    monkeypatch.setattr("app.api.v1.documents.extract_upload", lambda path, suffix: "金融政策正文" * 30)

    def fake_analyze(db, doc):
        policy = Policy(document_id=doc.id, title=doc.title, published_at=doc.published_at, status="ai_checked")
        db.add(policy)
        doc.status = "processed"
        db.commit()
        return policy

    monkeypatch.setattr("app.jobs.analyze_job.analyze_document", fake_analyze)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("dated.docx", b"dated-upload-content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"title": "带日期的上传政策", "jurisdiction": "HK", "published_at": "2026-03-05"},
        headers={"X-Demo-Role": "admin"},
    )
    assert response.status_code == 201
    body = response.json()
    expected = datetime(2026, 3, 5, tzinfo=timezone.utc)
    with SessionLocal() as db:
        assert db.get(Document, body["id"]).published_at == expected
        assert db.get(Policy, body["policy_id"]).published_at == expected


def test_upload_parse_failure_keeps_file_without_blank_policy(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))

    def fail_parse(path, suffix):
        from app.ingest.uploads import UploadParseError
        raise UploadParseError("测试解析失败")

    monkeypatch.setattr("app.api.v1.documents.extract_upload", fail_parse)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"broken-pdf-content", "application/pdf")},
        data={"jurisdiction": "HK"},
        headers={"X-Demo-Role": "admin"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["policy_id"] is None
    assert "测试解析失败" in body["processing_error"]
    assert (tmp_path / "uploads" / f"{body['id']}.pdf").exists()


def test_invalid_demo_role_is_rejected(client):
    response = client.get("/api/v1/policies", headers={"X-Demo-Role": "not-a-role"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_restore_uses_review_workflow_and_rejects_illegal_transition(client):
    policy_id, _, _ = _policy_fixture("restore")
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        policy.target_entity_status = "low"
        db.commit()

    rejected = client.post(f"/api/v1/policies/{policy_id}/restore", headers={"X-Demo-Role": "admin"})
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INVALID_TRANSITION"

    with SessionLocal() as db:
        db.get(Policy, policy_id).status = "draft"
        assessment = db.scalar(select(Assessment).where(Assessment.policy_id == policy_id))
        assessment.recommended_actions = [{"owner": "RBWM", "action": "复核政策影响"}]
        db.commit()
    restored = client.post(f"/api/v1/policies/{policy_id}/restore", headers={"X-Demo-Role": "admin"})
    assert restored.status_code == 200
    assert restored.json()["policy_status"] == "pending_review"
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        assert policy.target_entity_status == "high"
        assert db.scalars(select(ReviewTask).where(
            ReviewTask.policy_id == policy_id, ReviewTask.status == "pending", ReviewTask.level == 1,
        )).one()
        assert db.scalars(select(AuditLog).where(
            AuditLog.object_id == policy_id, AuditLog.action == "submit_review",
        )).one()


def test_five_role_data_scope_and_operation_permissions(client):
    published_id, _, _ = _policy_fixture("role-published")
    draft_id, _, _ = _policy_fixture("role-draft")
    with SessionLocal() as db:
        db.get(Policy, published_id).status = "published"
        db.get(Policy, draft_id).status = "pending_review"
        level_one = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == draft_id)).one()
        level_one.status = "pending"
        db.add(ReviewTask(policy_id=draft_id, level=2, status="pending"))
        db.commit()
        level_two_id = next(task.id for task in db.scalars(select(ReviewTask).where(ReviewTask.policy_id == draft_id)) if task.level == 2)

    consumer = {"X-Demo-Role": "consumer"}
    assert client.get("/api/v1/policies", headers=consumer).json()["total"] == 1
    assert client.get("/api/v1/policies?status=pending_review", headers=consumer).json()["total"] == 0
    published = client.get(f"/api/v1/policies/{published_id}", headers=consumer)
    assert published.status_code == 200 and published.json()["review_tasks"] == []
    assert client.get(f"/api/v1/policies/{draft_id}", headers=consumer).status_code == 404
    for path in ("/sources", "/documents", "/review-tasks", "/jobs/status", "/settings", "/admin/audit", "/alerts"):
        assert client.get(f"/api/v1{path}", headers=consumer).status_code == 403, path
    assert client.post(f"/api/v1/policies/{published_id}/dispatch", headers=consumer).status_code == 403

    analyst = {"X-Demo-Role": "analyst"}
    approver = {"X-Demo-Role": "approver"}
    publisher = {"X-Demo-Role": "publisher"}
    admin = {"X-Demo-Role": "admin"}
    assert {item["level"] for item in client.get("/api/v1/review-tasks", headers=analyst).json()["items"]} == {1}
    assert {item["level"] for item in client.get("/api/v1/review-tasks", headers=approver).json()["items"]} == {2}
    assert client.get("/api/v1/review-tasks", headers=publisher).status_code == 200
    assert client.post(f"/api/v1/review-tasks/{level_two_id}/claim", headers=analyst).status_code == 403
    assert client.post(f"/api/v1/review-tasks/{level_two_id}/claim", headers=publisher).status_code == 403
    assert client.get("/api/v1/sources", headers=analyst).status_code == 403
    assert client.delete(f"/api/v1/policies/{published_id}", headers=publisher).status_code == 403
    assert client.get("/api/v1/sources", headers=admin).status_code == 200
    assert client.get("/api/v1/settings", headers=admin).status_code == 200
    assert client.get("/api/v1/jobs/status", headers=admin).status_code == 200

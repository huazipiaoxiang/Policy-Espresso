"""无关政策清理 Skill：确定性门禁、删除政策与原文、审计留痕、API 触发与权限。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.agent.cleanup import assess_hsbc_impact, cleanup_policy_if_irrelevant
from app.db.models import Assessment, AuditLog, Document, Policy, Source, new_id
from app.db.session import SessionLocal


def _make_policy(*, relevant: bool = False, published: bool = False) -> dict[str, str]:
    """造一条政策：默认对汇丰完全无影响（可清理）。"""
    with SessionLocal() as db:
        source = Source(
            code=new_id("t_cleanup"), name="t", jurisdiction="HK",
            adapter="manual", url=f"https://t/{new_id('s')}",
        )
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url=f"https://t/{new_id('u')}",
            canonical_url=f"https://t/{new_id('c')}",
            title="境外再保险监管指引",
            content_hash=new_id("h"),
            content_text="对境外再保险机构的资本充足与信息披露作出规定，适用于再保险机构。",
            attachments=[{"name": "a.txt", "path": f"uploads/{new_id('a')}.txt"}],
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title="境外再保险监管指引",
            status="published" if published else "analyzed",
            priority="P3",
            jurisdiction="SG",
            themes=["再保险"],
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={"relevance": 3, "compliance": 2, "differential": 1} if relevant else {},
            direction="neutral",
            score_total=45 if relevant else 4,
            priority="P2" if relevant else "P3",
            affected={"business_lines": ["CIB"] if relevant else []},
            recommended_actions=[],
            confidence=0.6,
            model="offline-rules",
        ))
        db.commit()
        return {"policy_id": policy.id, "document_id": doc.id}


def test_gate_marks_irrelevant_policy_as_deletable(client):
    ids = _make_policy()
    with SessionLocal() as db:
        verdict = assess_hsbc_impact(db, db.get(Policy, ids["policy_id"]))
    assert verdict["verdict"] == "none"
    assert verdict["recommendation"] == "delete"
    assert verdict["keep_reasons"] == []


def test_gate_keeps_policy_with_impact_signals(client):
    ids = _make_policy(relevant=True)
    with SessionLocal() as db:
        verdict = assess_hsbc_impact(db, db.get(Policy, ids["policy_id"]))
    assert verdict["verdict"] == "possible"
    assert verdict["recommendation"] == "keep"
    assert any("业务线" in reason for reason in verdict["keep_reasons"])


def test_gate_keeps_published_policy(client):
    ids = _make_policy(published=True)
    with SessionLocal() as db:
        verdict = assess_hsbc_impact(db, db.get(Policy, ids["policy_id"]))
    assert verdict["verdict"] == "possible"
    assert any("已发布" in reason for reason in verdict["keep_reasons"])


def test_cleanup_deletes_policy_and_document_with_audit(client):
    ids = _make_policy()
    with SessionLocal() as db:
        result = cleanup_policy_if_irrelevant(db, db.get(Policy, ids["policy_id"]))
    assert result["deleted"] is True

    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is None
        assert db.get(Document, ids["document_id"]) is None
        actions = set(db.scalars(
            select(AuditLog.action).where(
                AuditLog.object_id.in_([ids["policy_id"], ids["document_id"]])
            )
        ))
    assert {"delete_policy", "delete_document"} <= actions


def test_cleanup_keeps_relevant_policy(client):
    ids = _make_policy(relevant=True)
    with SessionLocal() as db:
        policy = db.get(Policy, ids["policy_id"])
        result = cleanup_policy_if_irrelevant(db, policy)
        assert result["deleted"] is False
        assert "保留" in result["reason"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_endpoint_dry_run_does_not_delete(client):
    ids = _make_policy()
    response = client.post(
        f"/api/v1/policies/{ids['policy_id']}/agent/cleanup",
        params={"dry_run": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["verdict"] == "none"
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_job_dry_run_only_lists_candidates(client):
    from app.jobs.cleanup_job import cleanup_all

    ids = _make_policy()
    with SessionLocal() as db:
        stats = cleanup_all(db, dry_run=True)
        assert ids["policy_id"] in stats["dry_run_candidates"]
        assert stats["deleted"] == 0
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_endpoint_deletes_irrelevant_policy(client):
    ids = _make_policy()
    response = client.post(f"/api/v1/policies/{ids['policy_id']}/agent/cleanup")
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is None


def test_cleanup_endpoint_requires_processor_or_admin(client):
    ids = _make_policy()
    response = client.post(
        f"/api/v1/policies/{ids['policy_id']}/agent/cleanup",
        headers={"X-Demo-Role": "consumer"},
    )
    assert response.status_code == 403
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_agent_permissions_lists_cleanup_skill(client):
    response = client.get("/api/v1/preprocess/agent/permissions")
    assert response.status_code == 200
    body = response.json()
    assert body["irrelevant_cleanup_enabled"] is True
    names = {skill["name"] for skill in body["skills"]}
    assert "irrelevant_policy_cleanup" in names

"""免审核直发：已分析政策可直接发布；仍在审核中的状态仍被拦截。"""
from datetime import datetime, timezone

import pytest

from app.db.models import Assessment, Document, Policy, Source
from app.db.session import SessionLocal


def _make_policy(status: str) -> str:
    with SessionLocal() as db:
        source = Source(code="t_dispatch", name="t", jurisdiction="HK", adapter="manual", url="https://t")
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url=f"https://t/{status}",
            canonical_url=f"https://t/{status}",
            title=f"发布测试-{status}",
            content_hash=f"h_{status}",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title=f"发布测试-{status}",
            status=status,
            priority="P3",
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={},
            direction="neutral",
            score_total=20.0,
            priority="P3",
            affected={"business_lines": ["CIB"], "segments": []},
        ))
        db.commit()
        return policy.id


@pytest.mark.parametrize("status", ["ai_checked", "approved"])
def test_publish_without_review_for_publishable_status(client, status):
    policy_id = _make_policy(status)

    response = client.post(
        f"/api/v1/policies/{policy_id}/dispatch", headers={"X-Demo-Role": "processor"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"


def test_admin_can_publish(client):
    policy_id = _make_policy("ai_checked")

    response = client.post(
        f"/api/v1/policies/{policy_id}/dispatch", headers={"X-Demo-Role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"


@pytest.mark.parametrize("status", ["in_review", "pending_review", "draft"])
def test_review_in_progress_still_blocked(client, status):
    policy_id = _make_policy(status)

    response = client.post(
        f"/api/v1/policies/{policy_id}/dispatch", headers={"X-Demo-Role": "processor"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"


def test_consumer_cannot_publish(client):
    policy_id = _make_policy("ai_checked")

    response = client.post(
        f"/api/v1/policies/{policy_id}/dispatch", headers={"X-Demo-Role": "consumer"}
    )
    assert response.status_code == 403

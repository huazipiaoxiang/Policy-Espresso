"""政策跟进 Agent：受影响客户概况与跟踪邮件必须始终可生成。

未接入真实模型（provider=mock）时退回数据驱动归纳，接口不得返回 5xx，
避免前端出现「加载失败」。
"""
from datetime import datetime, timezone

from app.db.models import Assessment, Document, Policy, Source
from app.db.session import SessionLocal


def _make_policy() -> str:
    with SessionLocal() as db:
        source = Source(code="t_followup", name="t", jurisdiction="HK", adapter="manual", url="https://t")
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url="https://t/followup",
            canonical_url="https://t/followup",
            title="贴息政策",
            content_hash="h_followup",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title="贴息政策",
            status="published",
            priority="P2",
            published_at=datetime.now(timezone.utc),
            themes=["贷款与贴息"],
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={},
            direction="negative",
            score_total=60,
            priority="P2",
            transmission_chain=["贴息政策落地", "→ 客户融资成本下降"],
            affected={"business_lines": ["CIB"], "segments": []},
            recommended_actions=["复核 CIB 客户授信安排"],
            confidence=0.6,
            model="offline-rules",
        ))
        db.commit()
        return policy.id


def test_affected_customers_analysis_returns_brief_for_processor(client):
    policy_id = _make_policy()

    resp = client.post(
        f"/api/v1/policies/{policy_id}/affected-customers/analysis",
        headers={"X-Demo-Role": "processor"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["total_customers"] > 0
    assert body["brief"]["headline"]
    assert body["brief"]["suggested_actions"]
    assert body["brief"]["generated_by"] in {"ai_agent", "rules"}


def test_tracking_email_generated_for_processor(client):
    policy_id = _make_policy()

    resp = client.post(
        f"/api/v1/policies/{policy_id}/tracking-email",
        headers={"X-Demo-Role": "processor"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"].startswith("【政策跟踪报告】")
    # 邮件必须带上受影响客户概况的实时数据，而不是一句"去页面查看"
    assert "受影响客户概况" in body["body"]
    assert "户客户受影响" in body["body"]
    assert "业务线分布" in body["body"]
    assert "单户敞口前列" in body["body"]


def test_followup_agent_endpoints_forbidden_for_consumer(client):
    policy_id = _make_policy()

    resp = client.post(
        f"/api/v1/policies/{policy_id}/tracking-email",
        headers={"X-Demo-Role": "consumer"},
    )

    assert resp.status_code == 403

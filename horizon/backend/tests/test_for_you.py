"""「为你推荐」：没有客户画像也必须有推荐，分数取预处理表格百分比并降序。"""
from datetime import datetime, timedelta, timezone

from app.db.models import Document, Policy, PolicyPreprocess, Source
from app.db.session import SessionLocal

CONSUMER = {"X-Demo-Role": "consumer"}


def _make_policy(
    *,
    title: str,
    loss: float,
    opportunity: float,
    reputation: float,
    impact_total: float,
    days_ago: int = 0,
    status: str = "published",
) -> str:
    """造一条政策 + 其预处理记录；days_ago 控制"入库时间"（PolicyPreprocess.created_at）。"""
    with SessionLocal() as db:
        source = db.query(Source).filter(Source.code == "t_foryou").first()
        if source is None:
            source = Source(code="t_foryou", name="t", jurisdiction="HK", adapter="manual", url="https://t")
            db.add(source)
            db.flush()
        doc = Document(
            source_id=source.id,
            url=f"https://t/{title}",
            canonical_url=f"https://t/{title}",
            title=title,
            content_hash=f"h_{title}",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title=title,
            status=status,
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(PolicyPreprocess(
            policy_id=policy.id,
            loss_pct=loss,
            opportunity_pct=opportunity,
            reputation_pct=reputation,
            profit_pct=0.0,
            impact_total=impact_total,
            direction="negative",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        ))
        db.commit()
        return policy.id


def test_for_you_without_customers_is_not_empty_and_sorted_by_three_dimensions(client):
    _make_policy(title="低分政策", loss=10, opportunity=5, reputation=5, impact_total=6.7)
    _make_policy(title="高分政策", loss=80, opportunity=60, reputation=70, impact_total=70.0)
    _make_policy(title="中分政策", loss=40, opportunity=30, reputation=20, impact_total=30.0)

    resp = client.get("/api/v1/policies/for-you?username=demo_user", headers=CONSUMER)
    assert resp.status_code == 200
    body = resp.json()

    # 普通用户（无客户）走规则 B，直接用预处理表格百分比
    assert body["match_mode"] == "fallback"
    assert body["scores_source"] == "preprocess_percent"
    assert body["matched_customer_count"] == 0
    assert body["window"] == "week"
    assert body["total"] == 3
    assert [item["title"] for item in body["items"]] == ["高分政策", "中分政策", "低分政策"]

    dims = body["items"][0]["impact_dimensions"]
    assert dims["business_loss"] == 80
    assert dims["business_opportunity"] == 60
    assert dims["reputation_risk"] == 70


def test_for_you_falls_back_to_recent_when_week_has_no_new_policy(client):
    _make_policy(
        title="上月入库政策",
        loss=50, opportunity=20, reputation=10, impact_total=26.7,
        days_ago=30,
    )

    resp = client.get("/api/v1/policies/for-you?username=demo_user", headers=CONSUMER)
    body = resp.json()

    assert body["window"] == "all"  # 本周无新入库 → 回退最近入库，列表不为空
    assert body["total"] == 1
    assert body["items"][0]["title"] == "上月入库政策"


def test_for_you_excludes_unpublished_policy(client):
    _make_policy(
        title="未发布政策",
        loss=90, opportunity=90, reputation=90, impact_total=90.0,
        status="in_review",
    )

    resp = client.get("/api/v1/policies/for-you?username=demo_user", headers=CONSUMER)
    body = resp.json()

    assert body["total"] == 0

"""外部检索结果（汇丰/他行/市场应用）只保留「简述 + 原文链接」两项。"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.db.models import Document, Policy, PolicyPreprocess, Source
from app.db.session import SessionLocal
from app.domain.preprocess import _rank_by_relevance, normalize_research_items


def test_normalize_research_items_keeps_only_summary_and_url():
    legacy = [
        {"title": "汇丰回应贴息政策", "url": "https://a", "snippet": "汇丰表示将跟进落实。", "source": "web"},
        {"title": "另一条", "url": "https://a", "snippet": "重复链接应被去掉", "source": "web"},
        {"title": "只剩标题", "url": "https://b", "source": "web"},
        {"title": "无链接", "url": "", "snippet": "应被丢弃"},
    ]
    assert normalize_research_items(legacy) == [
        {"summary": "汇丰表示将跟进落实。", "url": "https://a"},
        {"summary": "只剩标题", "url": "https://b"},
    ]
    assert normalize_research_items(None) == []


def test_rank_by_relevance_outputs_summary_and_url_only():
    found = [
        SimpleNamespace(
            title="汇丰回应贷款贴息政策落地",
            text="汇丰表示配合政策实施，优化办理流程。",
            citation={"url": "https://news.example/a"},
        )
    ]
    ranked = _rank_by_relevance(found, ["贴息"], ("汇丰",), min_hits=1)
    assert ranked == [{"summary": "汇丰表示配合政策实施，优化办理流程。", "url": "https://news.example/a"}]


def _make_policy_with_legacy_links() -> str:
    with SessionLocal() as db:
        source = Source(code="t_links", name="t", jurisdiction="HK", adapter="manual", url="https://t")
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url="https://t/links",
            canonical_url="https://t/links",
            title="贴息政策",
            content_hash="h_links",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title="贴息政策",
            status="published",
            published_at=datetime.now(timezone.utc),
            themes=["贷款与贴息"],
        )
        db.add(policy)
        db.flush()
        db.add(PolicyPreprocess(
            policy_id=policy.id,
            direction="negative",
            hsbc_response=[],
            peer_bank_response=[
                {"title": "他行跟进贴息", "url": "https://x/a", "snippet": "某银行发布贴息实施细则。", "source": "web"}
            ],
            market_applications=[
                {"title": "首笔贴息贷款落地", "url": "https://x/b", "snippet": "某地首笔贴息贷款发放。", "source": "web"}
            ],
        ))
        db.commit()
        return policy.id


def test_preprocess_api_returns_only_summary_and_url(client):
    policy_id = _make_policy_with_legacy_links()

    resp = client.get(f"/api/v1/preprocess/{policy_id}", headers={"X-Demo-Role": "processor"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["peer_bank_response"] == [{"summary": "某银行发布贴息实施细则。", "url": "https://x/a"}]
    assert body["market_applications"] == [{"summary": "某地首笔贴息贷款发放。", "url": "https://x/b"}]


def test_consumer_view_returns_research_summary_and_url(client):
    policy_id = _make_policy_with_legacy_links()

    resp = client.get(f"/api/v1/policies/{policy_id}/consumer-view", headers={"X-Demo-Role": "consumer"})
    assert resp.status_code == 200
    research = resp.json()["research"]
    assert research["hsbc_response"] == []
    assert research["peer_bank_response"] == [{"summary": "某银行发布贴息实施细则。", "url": "https://x/a"}]
    assert research["market_applications"] == [{"summary": "某地首笔贴息贷款发放。", "url": "https://x/b"}]


def test_consumer_view_hides_customers_for_user_without_any(client):
    """没有客户的政策使用者：不返回受影响客户，也不返回「对所管理用户的影响概述」。"""
    policy_id = _make_policy_with_legacy_links()

    for query in ("", "?username=demo_user"):
        resp = client.get(
            f"/api/v1/policies/{policy_id}/consumer-view{query}", headers={"X-Demo-Role": "consumer"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["affected_customers"] == []
        assert body["impact_overview"] == ""
        assert body["match_basis"]["total_matched"] == 0


def test_consumer_view_shows_only_managed_customers_for_rm(client):
    policy_id = _make_policy_with_legacy_links()

    resp = client.get(
        f"/api/v1/policies/{policy_id}/consumer-view?username=rmdemo01",
        headers={"X-Demo-Role": "consumer"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["affected_customers"]) > 0
    # AI 分析已拆到独立接口，主接口不再阻塞返回影响概述
    assert body["impact_overview"] == ""
    assert body["match_basis"]["total_matched"] == len(body["affected_customers"])

    ai_resp = client.get(
        f"/api/v1/policies/{policy_id}/consumer-ai?username=rmdemo01",
        headers={"X-Demo-Role": "consumer"},
    )
    assert ai_resp.status_code == 200
    ai_body = ai_resp.json()
    assert "所管理客户" in ai_body["impact_overview"]
    assert ai_body["followup_advice"]


def test_topic_columns_return_summary_and_url_only(client, monkeypatch):
    """三栏解读（汇丰/业界/市场）与预处理口径一致：只返回简述 + 原文链接。"""
    from app.chat import web_search

    policy_id = _make_policy_with_legacy_links()
    monkeypatch.setattr(
        web_search,
        "search_web",
        lambda query, limit=3: [
            SimpleNamespace(title="业界解读标题", text="银行表示将跟进贴息政策。", citation={"url": "https://w/1"}),
            SimpleNamespace(title="市场案例标题", text="首笔贴息贷款完成发放。", citation={"url": "https://w/2"}),
        ],
    )

    resp = client.get(
        f"/api/v1/policies/{policy_id}/topic/贴息", headers={"X-Demo-Role": "consumer"}
    )
    assert resp.status_code == 200
    columns = resp.json()["columns"]
    expected_web = [
        {"summary": "银行表示将跟进贴息政策。", "url": "https://w/1"},
        {"summary": "首笔贴息贷款完成发放。", "url": "https://w/2"},
    ]
    assert columns["industry"] == expected_web
    assert columns["market"] == expected_web
    for key in ("hsbc", "industry", "market"):
        for link in columns[key]:
            assert set(link) == {"summary", "url"}

"""业务图谱：政策去重计数、下钻列表和市场过滤。"""
from datetime import datetime, timezone

import pytest

from app.db.models import Document, Policy, Source
from app.db.session import SessionLocal
from app.domain.business_map import BusinessLine


@pytest.fixture(scope="module", autouse=True)
def _release_sqlite_file_handles():
    yield
    # Windows 不能在连接池仍持有句柄时删除 session 级测试数据库。
    from app.db.session import engine
    engine.dispose()


def _add_policy(
    document_id: str,
    title: str,
    themes: list[str],
    jurisdiction: str = "HK",
    *,
    status: str = "draft",
    priority: str = "P3",
    summary_zh: str = "",
    issuing_body: str = "",
    scope: str = "high",
) -> None:
    source_id = f"src_{document_id}"
    with SessionLocal() as db:
        db.add(Source(id=source_id, code=source_id, name="测试来源", jurisdiction=jurisdiction,
                      adapter="manual", url=f"https://example.test/{document_id}"))
        db.add(Document(id=document_id, source_id=source_id, url=f"https://example.test/{document_id}",
                        canonical_url=f"https://example.test/{document_id}", title=title,
                        published_at=datetime.now(timezone.utc), content_text=title,
                        content_hash=f"hash_{document_id}"))
        db.add(Policy(id=f"policy_{document_id}", document_id=document_id, title=title,
                      published_at=datetime.now(timezone.utc), themes=themes,
                      jurisdiction=jurisdiction, score_total=7.0, status=status,
                      priority=priority, summary_zh=summary_zh, issuing_body=issuing_body,
                      target_entity_status=scope))
        db.commit()


def test_business_map_returns_distinct_domain_and_cell_policy_lists(client):
    _add_policy("doc_map_a", "跨境支付政策", ["主题甲", "主题乙"], "HK")
    _add_policy("doc_map_b", "贷款政策", ["主题甲"], "HK")
    _add_policy("doc_map_c", "另一市场政策", ["主题甲"], "CN")
    lines = [
        BusinessLine(code="LINE_A", name="业务线甲", themes_sensitivity={"主题甲": 4, "主题乙": 3}),
        BusinessLine(code="LINE_B", name="业务线乙", themes_sensitivity={"主题甲": 3}),
    ]
    # 使用独立主题，避免其他验收测试的数据影响计数。
    from app.api.v1 import business_map as business_map_api
    original_loader = business_map_api.load_business_map
    business_map_api.load_business_map = lambda: lines
    try:
        response = client.get("/api/v1/business-map")
        assert response.status_code == 200
        body = response.json()
    finally:
        business_map_api.load_business_map = original_loader

    line_a = body["matrix"]["LINE_A"]
    line_b = body["matrix"]["LINE_B"]
    assert line_a["policy_count"] == 3
    assert {p["id"] for p in line_a["policies"]} == {"policy_doc_map_a", "policy_doc_map_b", "policy_doc_map_c"}
    assert line_a["cells"]["主题甲"]["policy_count"] == 3
    assert {p["id"] for p in line_a["cells"]["主题甲"]["policies"]} == {
        "policy_doc_map_a", "policy_doc_map_b", "policy_doc_map_c",
    }
    assert line_a["cells"]["主题乙"]["policy_count"] == 1
    assert [p["id"] for p in line_a["cells"]["主题乙"]["policies"]] == ["policy_doc_map_a"]
    assert line_b["policy_count"] == 3
    assert body["top_themes"]["主题甲"] == 3  # 不跨业务线重复计数

    for row in body["matrix"].values():
        assert row["policy_count"] == len({p["id"] for p in row["policies"]})
        for cell in row["cells"].values():
            assert cell["policy_count"] == len({p["id"] for p in cell["policies"]})


def test_business_map_market_filter_and_empty_results(client):
    _add_policy("doc_map_empty", "香港支付政策", ["主题甲"], "HK")
    business_map_api = __import__("app.api.v1.business_map", fromlist=["business_map"])
    original_loader = business_map_api.load_business_map
    # 使用仅含主题甲的业务线，空市场必须返回零计数和空下钻列表。
    business_map_api.load_business_map = lambda: [
        BusinessLine(code="LINE_EMPTY", name="空业务线", themes_sensitivity={"主题甲": 3})
    ]
    try:
        response = client.get("/api/v1/business-map?jurisdiction=ZZ")
        assert response.status_code == 200
        body = response.json()
    finally:
        business_map_api.load_business_map = original_loader

    assert body["matrix"]["LINE_EMPTY"]["policy_count"] == 0
    assert body["matrix"]["LINE_EMPTY"]["policies"] == []
    assert body["matrix"]["LINE_EMPTY"]["cells"]["主题甲"]["policy_count"] == 0
    assert body["matrix"]["LINE_EMPTY"]["cells"]["主题甲"]["policies"] == []
    assert body["top_themes"]["主题甲"] == 0


def _use_single_line(monkeypatch, theme: str) -> None:
    from app.api.v1 import business_map as business_map_api

    monkeypatch.setattr(business_map_api, "load_business_map", lambda: [
        BusinessLine(code="MAP_TEST", name="图谱测试业务线", themes_sensitivity={theme: 4})
    ])


def test_business_map_uses_policy_list_filters(client, monkeypatch):
    theme = "图谱过滤主题"
    _use_single_line(monkeypatch, theme)
    _add_policy(
        "doc_map_filters", "实时过滤政策", [theme], "HK", status="published",
        priority="P0", summary_zh="独特摘要关键词", issuing_body="测试监管局", scope="high",
    )
    _add_policy("doc_map_filters_other", "其他政策", [theme], "CN", priority="P1")

    response = client.get(
        "/api/v1/business-map",
        params={"q": "独特摘要关键词", "status": "published", "priority": "P0",
                "jurisdiction": "HK", "theme": theme, "scope": "high"},
    )
    assert response.status_code == 200
    row = response.json()["matrix"]["MAP_TEST"]
    assert row["policy_count"] == 1
    assert [policy["id"] for policy in row["policies"]] == ["policy_doc_map_filters"]
    assert row["cells"][theme]["policy_count"] == 1

    response = client.get("/api/v1/business-map", params={"q": "没有匹配结果", "theme": theme})
    assert response.status_code == 200
    assert response.json()["matrix"]["MAP_TEST"]["policies"] == []
    assert response.json()["top_themes"][theme] == 0


def test_business_map_consumer_only_receives_published_policies(client, monkeypatch):
    theme = "图谱消费者主题"
    _use_single_line(monkeypatch, theme)
    _add_policy("doc_map_consumer_draft", "未发布政策", [theme], status="pending_review")
    _add_policy("doc_map_consumer_published", "已发布政策", [theme], status="published")

    # 即使消费者显式请求其他状态，也不能扩大可见范围。
    response = client.get(
        "/api/v1/business-map?status=pending_review",
        headers={"X-Demo-Role": "consumer"},
    )
    assert response.status_code == 200
    row = response.json()["matrix"]["MAP_TEST"]
    assert row["policy_count"] == 1
    assert [policy["id"] for policy in row["policies"]] == ["policy_doc_map_consumer_published"]
    assert all(policy["status"] == "published" for policy in row["cells"][theme]["policies"])

    analyst_response = client.get("/api/v1/business-map", headers={"X-Demo-Role": "analyst"})
    assert analyst_response.json()["matrix"]["MAP_TEST"]["policy_count"] == 2


def test_business_map_counts_policy_without_publish_date(client, monkeypatch):
    """上传件常解析不出发布日期；只按发布日期过滤会让这条已发布政策在矩阵里彻底消失。"""
    theme = "图谱无日期主题"
    _use_single_line(monkeypatch, theme)
    with SessionLocal() as db:
        db.add(Source(id="src_map_nodate", code="src_map_nodate", name="测试来源", jurisdiction="HK",
                      adapter="manual", url="https://example.test/map_nodate"))
        db.add(Document(id="doc_map_nodate", source_id="src_map_nodate", url="https://example.test/map_nodate",
                        canonical_url="https://example.test/map_nodate", title="无日期政策",
                        content_text="无日期政策", content_hash="hash_doc_map_nodate"))
        db.add(Policy(id="policy_doc_map_nodate", document_id="doc_map_nodate", title="无日期政策",
                      published_at=None, themes=[theme], jurisdiction="HK", score_total=5.0,
                      status="published", priority="P3"))
        db.commit()

    row = client.get("/api/v1/business-map", headers={"X-Demo-Role": "consumer"}).json()["matrix"]["MAP_TEST"]
    assert [policy["id"] for policy in row["policies"]] == ["policy_doc_map_nodate"]
    cell = row["cells"][theme]
    assert cell["policy_count"] == 1
    assert cell["policies"][0]["published_at"] is None
    assert cell["policies"][0]["status"] == "published"


def test_business_map_refetch_reflects_review_reanalysis_and_delete(client, monkeypatch):
    theme = "图谱刷新主题"
    other_theme = "图谱无关主题"
    _use_single_line(monkeypatch, theme)
    _add_policy("doc_map_refresh", "刷新政策", [other_theme], status="pending_review")
    url = "/api/v1/business-map"
    consumer_headers = {"X-Demo-Role": "consumer"}

    assert client.get(url, headers=consumer_headers).json()["matrix"]["MAP_TEST"]["policy_count"] == 0

    with SessionLocal() as db:
        policy = db.get(Policy, "policy_doc_map_refresh")
        policy.status = "published"  # 审核并发布后，下一次请求立即可见。
        policy.themes = [theme]  # 重分析后的主题变更也直接影响矩阵。
        db.commit()
    row = client.get(url, headers=consumer_headers).json()["matrix"]["MAP_TEST"]
    assert row["policy_count"] == 1
    assert row["cells"][theme]["policy_count"] == 1

    with SessionLocal() as db:
        policy = db.get(Policy, "policy_doc_map_refresh")
        policy.themes = [other_theme]
        db.commit()
    row = client.get(url, headers=consumer_headers).json()["matrix"]["MAP_TEST"]
    assert row["policy_count"] == 0
    assert row["cells"][theme]["policies"] == []

    with SessionLocal() as db:
        policy = db.get(Policy, "policy_doc_map_refresh")
        policy.themes = [theme]
        db.commit()
    assert client.get(url, headers=consumer_headers).json()["matrix"]["MAP_TEST"]["policy_count"] == 1
    with SessionLocal() as db:
        db.delete(db.get(Policy, "policy_doc_map_refresh"))
        db.commit()
    row = client.get(url, headers=consumer_headers).json()["matrix"]["MAP_TEST"]
    assert row["policy_count"] == 0
    assert row["policies"] == []

"""政策库「影响 Domain」：入库写满，缺失时按主题/关键词兜底推断。"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.db.models import Assessment, Document, Policy, Source
from app.db.session import SessionLocal
from app.domain.preprocess import infer_business_lines


def test_infer_business_lines_from_themes():
    policy = SimpleNamespace(themes=["贷款与贴息"], title="", summary_zh="")
    lines = infer_business_lines(policy)
    assert lines
    assert "CIB" in lines or "GTB" in lines


def test_infer_business_lines_from_title_keywords():
    policy = SimpleNamespace(themes=[], title="跨境贸易结算便利化通知", summary_zh="")
    assert infer_business_lines(policy)


def test_infer_business_lines_defaults_to_cib():
    policy = SimpleNamespace(themes=[], title="某项行政通知", summary_zh="")
    assert infer_business_lines(policy) == ["CIB"]


def _policy_fixture(*, title: str, themes: list[str], business_lines: list[str]) -> str:
    with SessionLocal() as db:
        source = db.query(Source).filter(Source.code == "t_domains").first()
        if source is None:
            source = Source(code="t_domains", name="t", jurisdiction="HK", adapter="manual", url="https://t")
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
            themes=themes,
            status="ai_checked",
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={dim: {"score": None, "reason": "", "evidence_ids": []} for dim in [
                "relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance",
            ]},
            direction="negative",
            score_total=20.0,
            priority="P3",
            affected={"business_lines": business_lines, "segments": [], "exposure_range": None},
        ))
        db.commit()
        return policy.id


def test_policy_list_fills_missing_impacted_domains(client):
    _policy_fixture(title="跨境支付便利化通知", themes=[], business_lines=[])

    response = client.get("/api/v1/policies", params={"q": "跨境支付便利化"}, headers={"X-Demo-Role": "admin"})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["impacted_domains"], "影响 Domain 不应为空"
    assert all(isinstance(code, str) and code for code in item["impacted_domains"])


def test_policy_list_prefers_analyzed_business_lines(client):
    _policy_fixture(title="零售业务通知", themes=["贷款与贴息"], business_lines=["WPB"])

    response = client.get("/api/v1/policies", params={"q": "零售业务"}, headers={"X-Demo-Role": "admin"})
    item = response.json()["items"][0]
    assert item["impacted_domains"] == ["WPB"]

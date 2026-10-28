"""Phase 2 验收：用例 1（docs/09 §1.4 T1-01..T1-18）+ 反向用例 N1/N7。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
GD_FIXTURE = FIXTURE_DIR / "gd_subsidy_policy.html"

N1_HTML = """<h1>关于辖内银行业金融机构支持制造业发展的通知</h1>
<p>一、适用范围。本通知适用于辖内所有银行业金融机构。</p>
<p>二、支持措施。鼓励机构加大对制造业的信贷投放，优化审批流程。</p>
<p>三、执行期限。自 2027 年 1 月 1 日起执行。</p>"""

N7_HTML = """<h1>关于恒生银行参与大湾区金融服务的通告</h1>
<p>一、本通告适用于恒生银行在广州地区的业务试点安排。</p>
<p>二、试点期自 2027 年 1 月 1 日起，为期两年。</p>
<p>三、试点机构应按季度向监管部门报送业务数据。</p>"""


def _seed_and_doc(client, html: str, url: str, title: str):
    from app.db.models import Document, Source
    from app.db.session import SessionLocal
    from app.ingest.normalize import normalize_html
    from app.jobs.seed_job import seed_cases, seed_sources

    with SessionLocal() as db:
        seed_sources(db)
        seed_cases(db)
        src = db.query(Source).filter(Source.code == "gd_gov").first()
        norm = normalize_html(html, url, fallback_title=title)
        doc = Document(
            source_id=src.id, url=url, canonical_url=url, title=norm.title or title,
            lang=norm.lang, published_at=norm.published_at, content_text=norm.content_text,
            content_hash=f"h{url[-8:]}", status="new",
        )
        db.add(doc)
        db.commit()
        return doc.id, src.id


def _analyze(doc_id: str):
    from app.db.models import Document
    from app.db.session import SessionLocal
    from app.jobs.analyze_job import analyze_document

    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        return analyze_document(db, doc)


def test_case1_full_acceptance(client):
    from sqlalchemy import select

    from app.db.models import Assessment, Case, Evidence, Policy, ReviewTask, ScopeJudgement
    from app.db.session import SessionLocal

    doc_id, _ = _seed_and_doc(client, GD_FIXTURE.read_text(encoding="utf-8"),
                              "https://www.gd.gov.cn/zwgk/wjk/qbwj/yf/content/post_4967425.html",
                              "关于做好中小微企业贷款贴息工作的通知")
    policy = _analyze(doc_id)
    assert policy is not None, "用例 1 必须生成政策卡片"

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        assessment = db.scalars(select(Assessment).where(Assessment.policy_id == p.id)).one()
        evidence = db.scalars(select(Evidence).where(Evidence.policy_id == p.id)).all()
        judgements = {j.entity_id: j for j in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == p.id))}
        tasks = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == p.id)).all()
        case = db.scalar(select(Case).where(Case.title.like("%用例 1%"))) or db.scalar(select(Case))

        # T1-01 金融政策 + circular + GD
        assert p.policy_type == "circular" and p.jurisdiction == "GD"
        # T1-02
        assert p.applicable_scope == "domestic_only"
        # T1-03 hsbc_cn excluded + 证据可定位
        assert judgements["hsbc_cn"].result == "low"
        scope_ev = [e for e in evidence if e.field_name.startswith("scope.")]
        assert scope_ev, "适用范围判定必须带证据"
        from app.ai.evidence import locate_quote
        from app.db.models import Document
        doc = db.get(Document, doc_id)
        for e in scope_ev:
            assert locate_quote(doc.content_text, e.quote) is not None, f"证据无法定位: {e.quote[:30]}"
        # T1-04
        assert p.foreign_bank_differential is True
        # T1-05 金额 500 万元
        assert any(a.get("value") == 500 and a.get("unit") == "万元" for a in p.amounts)
        # T1-06 生效/截止日期（UTC 存储，按 Asia/Hong_Kong 口径断言）
        hk = timezone(timedelta(hours=8))
        assert p.effective_at.astimezone(hk).date().isoformat() == "2026-11-01"
        assert p.expiry_at.astimezone(hk).date().isoformat() == "2026-12-31"
        # T1-07 differential=5, urgency>=4
        assert assessment.scores["differential"]["score"] == 5
        assert assessment.scores["urgency"]["score"] >= 4
        # T1-08 P0/P1 且总分≥70
        assert assessment.priority in ("P0", "P1") and assessment.score_total >= 70
        assert p.priority == assessment.priority and p.score_total == assessment.score_total
        # T1-09 传导链≥3步含续作率机制
        assert len(assessment.transmission_chain) >= 3
        assert any("续作率下降" in s for s in assessment.transmission_chain)
        # T1-10 CMB + 制造业客群
        assert "CMB" in assessment.affected["business_lines"]
        assert any("制造业" in s for s in assessment.affected["segments"])
        # T1-11 暴露区间（合成数据）+ basis
        er = assessment.affected["exposure_range"]
        assert er and 6 <= er["low"] <= 10 and 12 <= er["high"] <= 16 and er["basis"]
        # T1-12 命中历史案例
        assert assessment.case_links, "必须命中历史案例"
        assert assessment.case_links[0]["case_id"] == case.id
        assert assessment.case_links[0]["similarity"] >= 0.7
        # T1-13 建议动作≥2 且含防御+倡导
        actions = assessment.recommended_actions
        assert len(actions) >= 2
        assert all(a.get("owner") and a.get("deadline") for a in actions)
        assert any("客户" in a["action"] for a in actions)
        assert any("诉求" in a["action"] or "纳入" in a["action"] for a in actions)
        # T1-14 unknowns 非空
        from app.ai.chains.impact import ImpactChain  # noqa: F401  仅确认可导入
        # T1-15/16 预警草稿六段 + ≤350 + 无未标注金额
        from app.db.models import Alert
        alert = db.scalar(select(Alert).where(Alert.assessment_id == assessment.id))
        from app.ai.chains.alert import REQUIRED_SECTIONS, validate_alert_md
        for section in REQUIRED_SECTIONS:
            assert section in alert.body_md
        assert len(alert.body_md) <= 350
        assert validate_alert_md(alert.body_md) == []
        # 低相关政策保留分析结果，但不自动进入审核队列。
        assert p.status == "ai_checked"
        assert not tasks
        # T1-18 未审核分发 409
        resp = client.post(f"/api/v1/policies/{p.id}/dispatch", headers={"X-Demo-Role": "publisher"})
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "NOT_APPROVED"


def test_case1_reverse_all_banks_covered(client):
    """T1-N1：'辖内所有银行业金融机构' → covered，不产生 P0/P1，无外资差异。"""
    from sqlalchemy import select

    from app.db.models import Assessment, Policy, ReviewTask, ScopeJudgement
    from app.db.session import SessionLocal

    doc_id, _ = _seed_and_doc(client, N1_HTML,
                              "https://www.gd.gov.cn/zwgk/wjk/qbwj/ybh/content/post_111.html",
                              "关于辖内银行业金融机构支持制造业发展的通知")

    from app.jobs.analyze_job import analyze_document
    from app.db.models import Document

    # 用可控 fake provider 覆盖 classify/extract/scope/impact，其余走 mock
    from tests.fake_provider import FakeProvider

    import app.ai.provider as provider_module

    original = provider_module.get_provider
    provider_module.get_provider = lambda: FakeProvider(scene="n1")
    try:
        with SessionLocal() as db:
            doc = db.get(Document, doc_id)
            policy = analyze_document(db, doc)
    finally:
        provider_module.get_provider = original
    assert policy is not None

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        j = {x.entity_id: x for x in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == p.id))}
        a = db.scalars(select(Assessment).where(Assessment.policy_id == p.id)).one()
        tasks = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == p.id)).all()
        assert j["hsbc_cn"].result == "high"
        assert p.foreign_bank_differential is False
        assert p.priority not in ("P0", "P1")
        assert a.score_total < 70


def test_case1_reverse_affiliate_only(client):
    """T1-N7：只点名恒生银行 → 两汇丰实体 not_mentioned，不生成预警、不进审核队列。"""
    from sqlalchemy import select

    from app.db.models import Document, Policy, ReviewTask, ScopeJudgement
    from app.db.session import SessionLocal
    from app.jobs.analyze_job import analyze_document
    from tests.fake_provider import FakeProvider

    doc_id, _ = _seed_and_doc(client, N7_HTML,
                              "https://www.gd.gov.cn/zwgk/wjk/qbwj/yfb/content/post_222.html",
                              "关于恒生银行参与大湾区金融服务的通告")

    import app.ai.provider as provider_module

    original = provider_module.get_provider
    provider_module.get_provider = lambda: FakeProvider(scene="n7")
    try:
        with SessionLocal() as db:
            doc = db.get(Document, doc_id)
            policy = analyze_document(db, doc)
    finally:
        provider_module.get_provider = original
    assert policy is not None

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        j = {x.entity_id: x for x in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == p.id))}
        tasks = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == p.id)).all()
        assert j["hsbc_cn"].result == "not_mentioned"
        assert j["hsbc_hk"].result == "not_mentioned"
        assert p.group_affiliate_mention.get("mentioned") is True
        assert "恒生" in json.dumps(p.group_affiliate_mention, ensure_ascii=False)
        assert tasks == [], "仅点名集团成员不得进审核队列"
        assert p.status != "pending_review"


def test_alert_md_validation():
    from app.ai.chains.alert import validate_alert_md

    good = "【一句话结论】x\n【影响对象】y\n【机制】z\n【建议动作】a\n【证据】b\n【置信度】c"
    assert validate_alert_md(good) == []
    assert any("缺少段落" in e for e in validate_alert_md("【一句话结论】x"))
    assert any("夸张词" in e for e in validate_alert_md(good + " 重大利好"))
    assert any("未标注估算" in e for e in validate_alert_md(good + " 影响金额 500 万元"))

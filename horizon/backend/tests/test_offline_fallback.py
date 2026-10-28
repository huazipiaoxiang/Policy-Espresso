"""离线规则兜底：未接入真实 LLM 时，政策内容必须来自原文而不是 mock 样例应答。"""
from __future__ import annotations

from pathlib import Path

import pytest

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"

HKMA_LIKE = """<h1>香港金融管理局 - 金管局公布「ART」框架推动银行业负责任应用人工智能</h1>
<p>2026年10月15日</p>
<p>香港金融管理局今日公布「ART」框架，支持银行业负责任地应用人工智能（A.I.），以建立一个可问责、具韧性和可信赖的 A.I. 生态系统。</p>
<p>框架涵盖管治、风险管理、模型开发与验证、数据管理及第三方安排等范畴，认可机构应在 2026 年 12 月 31 日前完成自我评估。</p>"""

GENERIC_BANK = """<h1>关于辖内银行业金融机构支持制造业发展的通知</h1>
<p>一、适用范围。本通知适用于辖内所有银行业金融机构，包括外资法人银行。</p>
<p>二、支持措施。鼓励机构加大对制造业的信贷投放，优化贷款审批流程并按季度报送进展。</p>
<p>三、执行期限。自 2027 年 1 月 1 日起执行。</p>"""


@pytest.fixture()
def offline_on(monkeypatch):
    """开启离线规则兜底：provider 仍为 mock，但政策内容一律从原文派生。"""
    from app.core import config as config_module

    real = config_module.get_settings()
    monkeypatch.setattr(config_module, "get_settings",
                        lambda: real.model_copy(update={"llm_offline_rules": True}))


def _seed_and_analyze(client, url: str, title: str, html: str):
    from sqlalchemy import select

    from app.db.models import Document, Source
    from app.db.session import SessionLocal
    from app.ingest.normalize import normalize_html
    from app.jobs.seed_job import seed_cases, seed_sources
    from app.jobs.analyze_job import analyze_document

    with SessionLocal() as db:
        seed_sources(db)
        seed_cases(db)
        src = db.scalars(select(Source).where(Source.code == "hkma_press")).one()
        norm = normalize_html(html, url, fallback_title=title)
        doc = Document(
            source_id=src.id, url=url, canonical_url=url, title=title,
            lang=norm.lang, published_at=norm.published_at, content_text=norm.content_text,
            content_hash=f"offline-{url[-10:]}", status="new",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id

    with SessionLocal() as db:
        return analyze_document(db, db.scalars(select(Document).where(Document.id == doc_id)).one())


def test_offline_extract_derives_content_from_document(client, offline_on):
    """mock 样例里的《中小微企业贷款贴息通知》不得覆盖抓取到的金管局原文。"""
    policy = _seed_and_analyze(
        client, "https://www.hkma.gov.hk/chi/offline/art-frame/",
        "香港金融管理局 - 金管局公布「ART」框架推动银行业负责任应用人工智能", HKMA_LIKE,
    )
    assert policy is not None

    from app.db.models import Policy
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        assert "ART" in p.title
        assert p.title != "关于做好中小微企业贷款贴息工作的通知"
        assert "人工智能" in p.summary_zh
        assert "贴息" not in p.summary_zh
        assert p.issuing_body == "香港金融管理局"
        assert p.jurisdiction == "HK"
        assert "金融科技与虚拟资产" in p.themes
        # 样例中的金额/期限/义务不得出现在离线结论里
        assert p.amounts == [] and p.deadlines == [] and p.obligations == []
        assert p.doc_number is None
        assert p.status in ("ai_checked", "pending_review")
        assert p.prompt_version.startswith("offline-rules")


def test_offline_rule_derived_scores_still_queue_for_human_review(client, offline_on):
    """规则派生评分（未经模型判断）也要进审核队列，不能因低分被静默跳过。"""
    policy = _seed_and_analyze(
        client, "https://www.hkma.gov.hk/chi/offline/manufacturing/",
        "关于辖内银行业金融机构支持制造业发展的通知", GENERIC_BANK,
    )

    from sqlalchemy import select

    from app.db.models import Policy, ReviewTask
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        tasks = db.scalars(select(ReviewTask).where(ReviewTask.policy_id == p.id)).all()
        # 原文明确包含外资法人银行 → 规则通道 high，派生评分 > 0；P3 也要进队列
        assert p.score_total > 0
        assert p.priority == "P3"
        assert p.status == "pending_review", p.summary_zh
        assert len(tasks) == 1 and tasks[0].level == 1
        # 详情页“分析可靠程度”取 Policy.confidence，离线模式应回写影响分析置信度
        assert p.confidence > 0, "policy.confidence 未从 assessment 回写"


def test_offline_impact_derives_only_rule_backed_dimensions(offline_on):
    """8 维评分卡：规则通道可支撑的维度给分，无证据维度置 None 并说明缺什么。"""
    from datetime import datetime, timedelta, timezone

    from app.domain.offline_fallback import offline_impact

    soon = datetime.now(timezone.utc) + timedelta(days=20)
    result = offline_impact(
        ["贷款与贴息", "资本与流动性要求"],
        relevance_by_entity={"hsbc_hk": "low", "hsbc_cn": "high"},
        policy_type="circular",
        effective_at=soon,
        foreign_bank_differential=True,
        differential_quotes=["中资商业银行"],
        exposure={"low": 7.0, "high": 14.0, "currency": "CNY", "unit": "亿",
                  "basis": "合成数据集口径：测试", "confidence": 0.5},
    )
    scores = result["scores"]
    assert scores["relevance"]["score"] == 5
    assert "汇丰（中国） 高相关" in scores["relevance"]["reason"]
    assert scores["exposure"]["score"] == 2
    assert "合成数据集口径" in scores["exposure"]["reason"]
    assert scores["urgency"]["score"] == 5  # 距生效不足 30 天
    assert scores["certainty"]["score"] == 3  # 已颁布未生效
    assert scores["differential"]["score"] == 5
    assert "中资商业银行" in scores["differential"]["reason"]
    assert scores["compliance"]["score"] == 4
    assert scores["actionability"]["score"] is None
    assert result["direction"] == "negative"
    assert len(result["transmission_chain"]) >= 3
    assert result["affected"]["exposure_range"]["high"] == 14.0
    owners = {a["owner"] for a in result["recommended_actions"]}
    assert {"analyst.default", "reviewer.l2", "business.cmb"} <= owners
    assert any("缺" in u or "未" in u for u in result["unknowns"])


def test_offline_impact_keeps_missing_evidence_null(offline_on):
    """无规则支撑的维度必须保持 None，不得凑分。"""
    from app.domain.offline_fallback import offline_impact

    result = offline_impact(
        ["金融科技与虚拟资产"],
        relevance_by_entity={"hsbc_hk": "not_mentioned", "hsbc_cn": "not_mentioned"},
        policy_type="other",
    )
    scores = result["scores"]
    assert scores["relevance"]["score"] == 0
    assert scores["exposure"]["score"] is None
    assert "缺少客户暴露数据" in scores["exposure"]["reason"]
    assert scores["urgency"]["score"] is None
    assert "未给出生效" in scores["urgency"]["reason"]
    assert scores["actionability"]["score"] is None
    assert scores["differential"]["score"] == 0
    assert scores["compliance"]["score"] == 0
    assert result["direction"] == "neutral"
    assert result["recommended_actions"], "至少保留一条复核动作"
    assert result["affected"]["exposure_range"] is None


def test_fixture_mode_unchanged_when_offline_rules_off(client):
    """开关关闭时保持原行为：mock 走样例应答，既有管线测试的确定性不受影响。"""
    policy = _seed_and_analyze(
        client, "https://www.hkma.gov.hk/chi/offline/fixture-mode/",
        "香港金融管理局 - 金管局公布「ART」框架推动银行业负责任应用人工智能", HKMA_LIKE,
    )

    from app.db.models import Policy
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        p = db.get(Policy, policy.id)
        assert p.title == "关于做好中小微企业贷款贴息工作的通知"
        assert any(a.get("value") == 500 for a in p.amounts)


def test_theme_keywords_match_controlled_vocabulary():
    """主题关键词表的键必须与 seed/themes.yaml 受控词表一致。"""
    import yaml

    from app.domain.offline_fallback import THEME_KEYWORDS

    themes = yaml.safe_load((SEED_DIR / "themes.yaml").read_text(encoding="utf-8"))["themes"]
    assert set(THEME_KEYWORDS) == set(themes), (
        f"缺失：{sorted(set(themes) - set(THEME_KEYWORDS))}；多余：{sorted(set(THEME_KEYWORDS) - set(themes))}"
    )

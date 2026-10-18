"""ingest 模块离线单测：去重 / 变更检测 / gate-1 / 归一化 / 管线幂等。"""
from datetime import datetime, timezone

from app.ingest import change_detect, dedupe, gate1
from app.ingest.adapters import ItemRef, RawDoc
from app.ingest.normalize import detect_lang, extract_attachments, normalize_html

SAMPLE_HTML = """
<html><head><title>广东省制造业贷款贴息实施办法</title></head>
<body><article><h1>广东省制造业贷款贴息实施办法</h1>
<p>本办法自2026年11月1日起施行。</p>
<p>适用对象为在广东省内注册的中资商业银行、城市商业银行。</p>
<p>对符合条件的制造业企业贷款给予最高2%贴息，单户年度最高500万元。</p>
<a href="/files/impl.pdf">实施细则附件</a>
</article></body></html>
"""


def test_canonicalize_url():
    assert dedupe.canonicalize_url("http://www.example.com/a/?utm_source=x&b=1#frag") == "https://example.com/a?b=1"
    # ISD TuniS 代理还原
    assert dedupe.canonicalize_url(
        "https://sc.isd.gov.hk/TuniS//www.info.gov.hk/gia/general/202610/16/P2026101600356.htm"
    ) == "https://info.gov.hk/gia/general/202610/16/P2026101600356.htm"


def test_simhash_near_duplicate():
    """真实政策文本长度下：细微修订 → 近重复；无关文本 → 非近重复。

    注：simhash 对极短文本（<50 字）单字改动敏感，去重决策以 content_hash 精确比对为主。
    """
    base = "本办法适用于境内法人银行，自2026年11月1日起施行。对符合条件的制造业企业贷款给予最高2%贴息，单户年度最高500万元。" * 5
    a = dedupe.simhash64(base)
    b = dedupe.simhash64(base.replace("2%贴息", "3%贴息"))  # 细微修订
    c = dedupe.simhash64("香港金融管理局宣布调整基本利率，即时生效。" * 5)
    assert dedupe.is_near_duplicate(a, b)
    assert not dedupe.is_near_duplicate(a, c)
    # 完全相同文本必为近重复（跨源转载场景）
    assert dedupe.is_near_duplicate(a, dedupe.simhash64(base))


def test_change_detect_ratio():
    old = "第一段。\n第二段。\n第三段。\n第四段。"
    minor = "第一段。\n第二段改了。\n第三段。\n第四段。"
    major = "全新一。\n全新二。\n全新三。\n全新四。"
    r_minor = change_detect.compute_diff(old, minor)
    r_major = change_detect.compute_diff(old, major)
    assert r_minor.changed and r_minor.minor_edit and r_minor.changed_ratio <= 0.3
    assert r_major.changed and not r_major.minor_edit and r_major.changed_ratio > 0.3
    assert not change_detect.compute_diff(old, old).changed


def test_gate1():
    assert gate1.gate1_pass("贷款贴息办法", "")[0]
    assert gate1.gate1_pass("HKMA adjusts base rate", "")[0]
    ok, _ = gate1.gate1_pass("社区文化活动预告", "本周末举办亲子手工市集。")
    assert not ok


def test_detect_lang():
    assert detect_lang("The Hong Kong Monetary Authority announced today") == "en"
    assert detect_lang("香港金融管理局今日宣佈") == "zh-Hant"
    assert detect_lang("广东省人民政府印发通知") == "zh-Hans"


def test_normalize_and_attachments():
    norm = normalize_html(SAMPLE_HTML, "https://www.gd.gov.cn/zwgk/wjk/qbwj/yf/content/post_1.html")
    assert "贴息" in norm.content_text
    assert norm.lang == "zh-Hans"
    assert norm.published_at is not None and norm.published_at.tzinfo == timezone.utc
    assert norm.attachments and norm.attachments[0]["url"].endswith("impl.pdf")


class _FakeAdapter:
    """离线管线测试用：内存中发现与抓取。"""

    def __init__(self, docs: dict[str, str]):
        self.docs = docs

    def discover(self, since):
        return [ItemRef(url=u, title="t") for u in self.docs]

    def fetch(self, ref):
        return RawDoc(url=ref.url, html=self.docs[ref.url].encode(), headers={})


def test_pipeline_idempotent(client, monkeypatch):
    """同一批内容连跑两次：第二次 0 新增、0 重复（canonical URL 精确去重）。"""
    from app.db.models import Source
    from app.db.session import SessionLocal
    from app.ingest import pipeline
    from app.ingest.adapters import register

    docs = {f"https://ex.com/p{i}": SAMPLE_HTML for i in range(3)}

    @register("fake")
    class Fake(_FakeAdapter):
        def __init__(self, source):
            super().__init__(docs)

    with SessionLocal() as db:
        src = Source(code="fake_src", name="fake", jurisdiction="GD", adapter="fake", url="https://ex.com")
        db.add(src)
        db.commit()

        s1 = pipeline.crawl_source(db, src)
        assert s1["created"] == 3 and s1["failed"] == 0
        # 同一 30 分钟窗口外的第二轮：内容未变 → unchanged（在回溯窗口内会重抓比对）
        s2 = pipeline.crawl_source(db, src)
        assert s2["created"] == 0 and s2["duplicate"] == 0

        from app.db.models import Document

        assert db.query(Document).filter(Document.source_id == src.id).count() == 3


def test_pipeline_change_detection(client, monkeypatch):
    """正文变化 → 生成 document_version，小改动标 minor_edit。"""
    from app.db.models import Document, DocumentVersion, Source
    from app.db.session import SessionLocal
    from app.ingest import pipeline
    from app.ingest.adapters import register

    url = "https://ex.com/policy"
    docs = {url: SAMPLE_HTML}

    @register("fake2")
    class Fake(_FakeAdapter):
        def __init__(self, source):
            super().__init__(docs)

    with SessionLocal() as db:
        src = Source(code="fake_src2", name="fake2", jurisdiction="GD", adapter="fake2", url="https://ex.com")
        db.add(src)
        db.commit()
        pipeline.crawl_source(db, src)

        docs[url] = SAMPLE_HTML.replace("最高2%贴息", "最高3%贴息")  # 小修订
        s2 = pipeline.crawl_source(db, src)
        assert s2["updated"] == 1

        doc = db.scalar(__import__("sqlalchemy").select(Document).where(Document.source_id == src.id))
        versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).all()
        assert len(versions) == 1
        assert versions[0].minor_edit is True
        assert versions[0].changed_ratio > 0

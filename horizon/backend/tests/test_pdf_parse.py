"""PDF 附件解析离线单测（06 §5.6 / §8）：文本层抽取、扫描件判定、sha256 去重、失败降级。"""
import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from app.ingest import http
from app.ingest import pdf_parse

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def _make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("STSong-Light", 12)
    y = 780
    for line in lines:
        c.drawString(72, y, line)
        y -= 24
    c.save()
    return buf.getvalue()


_LONG_TEXT_PDF = _make_pdf([f"第{i}条 为支持制造业高质量发展，对符合条件的贷款给予贴息支持。" for i in range(1, 8)])
_SCANNED_PDF = _make_pdf(["扫描件"])  # 文本层极短 → 判定扫描件


@pytest.fixture()
def _tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parse, "_attachments_root", lambda: tmp_path)
    return tmp_path


def test_parse_pdf_with_text_layer(_tmp_storage):
    result = pdf_parse.parse_pdf_bytes(_LONG_TEXT_PDF)
    assert result.status == "parsed"
    assert result.char_count >= pdf_parse.TEXT_LAYER_MIN_CHARS
    assert result.parsed_text_path and "贴息" in open(result.parsed_text_path, encoding="utf-8").read()
    assert len(result.sha256) == 64


def test_parse_pdf_scanned(_tmp_storage):
    result = pdf_parse.parse_pdf_bytes(_SCANNED_PDF)
    assert result.status == "scanned"
    assert result.char_count < pdf_parse.TEXT_LAYER_MIN_CHARS
    assert "需人工阅读" in (result.error or "")


def test_attachment_sha256_dedup(_tmp_storage):
    """同内容 PDF 第二次解析命中缓存，不重复抽文本。"""
    r1 = pdf_parse.parse_pdf_bytes(_LONG_TEXT_PDF)
    r2 = pdf_parse.parse_pdf_bytes(_LONG_TEXT_PDF)
    assert r1.sha256 == r2.sha256 and r2.status == "parsed"
    assert r1.parsed_text_path == r2.parsed_text_path


def test_parse_pdf_corrupt_raises(_tmp_storage):
    """结构损坏的 PDF 抛异常，由 enrich/parse_attachment 层降级为 failed。"""
    with pytest.raises(Exception):
        pdf_parse.parse_pdf_bytes(b"not a pdf at all")


def test_parse_attachment_corrupt_pdf_failed(_tmp_storage, monkeypatch):
    monkeypatch.setattr(pdf_parse.http, "fetch",
                        lambda url, **kw: http.FetchResponse(url=url, status=200, headers={},
                                                             content=b"not a pdf", latency_ms=1))
    result = pdf_parse.parse_attachment("https://ex.com/bad.pdf")
    assert result.status == "failed" and result.error





def test_parse_attachment_fetch_failure(_tmp_storage, monkeypatch):
    def _boom(url, **kw):
        raise http.FetchError(f"HTTP 404 {url}", retryable=False, status=404)

    monkeypatch.setattr(pdf_parse.http, "fetch", _boom)
    result = pdf_parse.parse_attachment("https://ex.com/a.pdf")
    assert result.status == "failed" and "404" in (result.error or "")


def test_enrich_attachments(_tmp_storage, monkeypatch):
    monkeypatch.setattr(pdf_parse.http, "fetch",
                        lambda url, **kw: http.FetchResponse(url=url, status=200, headers={},
                                                             content=_LONG_TEXT_PDF, latency_ms=1))
    atts = [
        {"name": "a.pdf", "url": "https://ex.com/a.pdf"},
        {"name": "b.docx", "url": "https://ex.com/b.docx"},
        {"name": "c.pdf", "url": "https://ex.com/c.pdf"},
        {"name": "d.pdf", "url": "https://ex.com/d.pdf"},
    ]
    out = pdf_parse.enrich_attachments(atts, max_count=2)
    assert out[0]["status"] == "parsed" and out[0]["sha256"]
    assert out[1]["status"] == "unsupported"  # Office 文档待 MinerU/Docling
    assert out[2]["status"] == "parsed" and out[2]["sha256"] == out[0]["sha256"]  # 同内容去重
    assert out[3]["status"] == "skipped"  # 超出每文档上限

"""文档正文导出为 PDF（复用 reportlab 内置 CID 中文字体，无需外部字体文件）。

简体用 STSong-Light，繁体（zh-Hant/zh-HK/zh-TW）用 MSung-Light。
"""
from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))

CJK_FONT_BY_LANG = {"zh-hant": "MSung-Light", "zh-hk": "MSung-Light", "zh-tw": "MSung-Light"}


def _paragraphs(content_text: str) -> list[str]:
    blocks: list[str] = []
    for block in content_text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        text = block.strip()
        if text:
            blocks.append(text)
    return blocks


def build_document_pdf(
    *,
    title: str,
    doc_id: str,
    source_name: str,
    jurisdiction: str,
    published_at: str | None,
    lang: str,
    content_text: str,
) -> bytes:
    font = CJK_FONT_BY_LANG.get((lang or "").lower(), "STSong-Light")
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=(title or doc_id)[:200],
    )
    title_style = ParagraphStyle("title", fontName=font, fontSize=15, leading=21, spaceAfter=8)
    meta_style = ParagraphStyle("meta", fontName=font, fontSize=9, leading=14,
                                textColor="#555555", spaceAfter=4)
    body_style = ParagraphStyle("body", fontName=font, fontSize=10.5, leading=17, spaceAfter=8)

    meta_bits = [f"文档编号：{doc_id}"]
    if source_name:
        meta_bits.append(f"来源：{source_name}")
    if jurisdiction:
        meta_bits.append(f"市场：{jurisdiction}")
    if published_at:
        meta_bits.append(f"发布日期：{published_at}")
    meta_html = " &middot; ".join(escape(bit) for bit in meta_bits)

    story = [Paragraph(escape(title), title_style), Paragraph(meta_html, meta_style), Spacer(1, 6)]
    for block in _paragraphs(content_text):
        story.append(Paragraph(escape(block).replace("\n", "<br/>"), body_style))

    doc.build(story)
    return buffer.getvalue()

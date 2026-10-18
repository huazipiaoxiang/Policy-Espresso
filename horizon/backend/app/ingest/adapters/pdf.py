"""PDF 适配器：年度/专项源（施政报告、预算案）由人工提交 URL 触发。

discover 不做自动发现；fetch 取回 PDF 并抽取文本，包装为 HTML 供 normalize 统一处理。
"""
from __future__ import annotations

from datetime import datetime
from html import escape

from app.ingest import http
from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest.pdf_parse import extract_pdf_text


@register("pdf")
class PdfAdapter:
    def __init__(self, source):  # noqa: ANN001
        self.source = source

    def discover(self, since: datetime | None) -> list[ItemRef]:  # noqa: ARG002
        return []  # 年度/专项源（施政报告、预算案）走 manual 触发

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url, timeout=60.0)
        text = extract_pdf_text(resp.content)
        paragraphs = "".join(f"<p>{escape(p)}</p>" for p in text.split("\n") if p.strip())
        html = f"<html><head><title>{escape(ref.title)}</title></head><body><article>{paragraphs}</article></body></html>"
        return RawDoc(url=ref.url, html=html.encode("utf-8"), headers=resp.headers,
                      published_at_guess=ref.published_at_guess)

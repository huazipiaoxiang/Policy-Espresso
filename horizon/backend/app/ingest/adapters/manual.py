"""人工上传适配器：内部渠道获得的 URL/PDF 由研究员手工登记（04 API: POST /documents）。"""
from __future__ import annotations

from datetime import datetime

from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest import http


@register("manual")
class ManualAdapter:
    def __init__(self, source):  # noqa: ANN001
        self.source = source

    def discover(self, since: datetime | None) -> list[ItemRef]:  # noqa: ARG002
        return []  # 不主动发现，由人工提交触发 fetch

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url)
        return RawDoc(url=ref.url, html=resp.content, headers=resp.headers, published_at_guess=ref.published_at_guess)

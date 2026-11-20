"""人工上传适配器：内部渠道获得的 URL/PDF 由研究员手工登记（04 API: POST /documents）。

source.config 可选：
  monitor: true —— 每日抓取时把 source.url 自身作为待抓条目 fetch，通过内容 hash 检测变化
              （用于单一公开网页需持续跟踪更新的场景，如五年规划门户页）。
"""
from __future__ import annotations

from datetime import datetime

from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest import http


@register("manual")
class ManualAdapter:
    def __init__(self, source):  # noqa: ANN001
        self.source = source

    def discover(self, since: datetime | None) -> list[ItemRef]:  # noqa: ARG002
        cfg = self.source.config or {}
        if cfg.get("monitor") and self.source.url:
            # 单页变化检测：返回该 URL 自身，每日抓取会 fetch 后按 content hash 检测变化
            return [ItemRef(url=self.source.url, title=self.source.name)]
        return []  # 不主动发现，由人工提交触发 fetch

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url)
        return RawDoc(url=ref.url, html=resp.content, headers=resp.headers, published_at_guess=ref.published_at_guess)

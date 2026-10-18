"""Sitemap 适配器：拉 sitemap.xml → 比对已知 URL → 只抓新增（06 §5.2 第二优先级）。"""
from __future__ import annotations

import re
from datetime import datetime

from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest import http
from app.ingest.normalize import parse_date

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_LASTMOD_RE = re.compile(r"<lastmod>\s*([^<]+?)\s*</lastmod>")


@register("sitemap")
class SitemapAdapter:
    """source.url 为 sitemap.xml 地址；config.url_include_regex 过滤感兴趣路径。"""

    def __init__(self, source):  # noqa: ANN001
        self.source = source
        include = (source.config or {}).get("url_include_regex")
        self.include_re = re.compile(include) if include else None

    def discover(self, since: datetime | None) -> list[ItemRef]:
        resp = http.fetch(self.source.url)
        xml = resp.content.decode("utf-8", errors="replace")
        urls = _LOC_RE.findall(xml)
        lastmods = _LASTMOD_RE.findall(xml)
        refs: list[ItemRef] = []
        for i, url in enumerate(urls):
            if self.include_re and not self.include_re.search(url):
                continue
            published = parse_date(lastmods[i]) if i < len(lastmods) else None
            if since and published and published < since:
                continue
            refs.append(ItemRef(url=url, title="", published_at_guess=published))
        return refs

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url)
        return RawDoc(url=ref.url, html=resp.content, headers=resp.headers, published_at_guess=ref.published_at_guess)

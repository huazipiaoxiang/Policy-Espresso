"""列表页适配器：翻页 diff（取前 N 页，抽取匹配 item_url_regex 的 <a> 链接）。

source.config 约定：
  item_url_regex: 条目链接正则（必填）
  max_pages: 翻页数，默认 1（06 建议前 3 页）
  pagination_pattern: 如 "index_{n}.html"，{n} 从 2 开始（可选）
  link_absolute: 链接是否已是绝对地址（可选，默认自动 urljoin）
"""
from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin

from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest import http
from app.ingest.normalize import parse_date

_ANCHOR_RE_TEMPLATE = r'<a\b[^>]*href=["\']({href})["\'][^>]*>(.*?)</a>'
_TAG_RE = re.compile(r"<[^>]+>")


@register("listing")
class ListingAdapter:
    def __init__(self, source):  # noqa: ANN001
        self.source = source
        cfg = source.config or {}
        pattern = cfg.get("item_url_regex")
        if not pattern:
            raise ValueError(f"{source.code}: listing 适配器缺少 config.item_url_regex")
        self.item_re = re.compile(pattern)
        self.anchor_re = re.compile(
            _ANCHOR_RE_TEMPLATE.format(href=f"([^\"']*{pattern}[^\"']*)"), re.IGNORECASE | re.DOTALL
        )
        self.max_pages = int(cfg.get("max_pages", 1))
        self.pagination_pattern = cfg.get("pagination_pattern")

    def _page_urls(self) -> list[str]:
        urls = [self.source.url]
        if self.pagination_pattern:
            base = self.source.url.rstrip("/")
            for n in range(2, self.max_pages + 1):
                urls.append(f"{base}/{self.pagination_pattern.format(n=n)}")
        return urls

    def discover(self, since: datetime | None) -> list[ItemRef]:  # noqa: ARG002 列表页按链接指纹去重，不按时间
        seen: set[str] = set()
        refs: list[ItemRef] = []
        for page_url in self._page_urls():
            try:
                resp = http.fetch(page_url)
            except http.FetchError:
                if page_url == self.source.url:
                    raise
                continue  # 翻页失败不阻塞首页结果
            html = resp.content.decode("utf-8", errors="replace")
            for m in self.anchor_re.finditer(html):
                url = urljoin(page_url, unescape(m.group(1)))
                if url in seen:
                    continue
                seen.add(url)
                title = _TAG_RE.sub("", m.group(2)).strip()
                refs.append(ItemRef(url=url, title=title, published_at_guess=parse_date(url)))
        return refs

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url)
        return RawDoc(url=ref.url, html=resp.content, headers=resp.headers, published_at_guess=ref.published_at_guess)

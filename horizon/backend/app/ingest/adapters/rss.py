"""RSS 适配器（首选，最稳）。feedparser 解析，按 published + entry id 增量。"""
from __future__ import annotations

from datetime import datetime, timezone

import feedparser

from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest import http


@register("rss")
class RssAdapter:
    """source.url 即 RSS XML 地址；config.rss_url_en 等备用频道可选。"""

    def __init__(self, source):  # noqa: ANN001
        self.source = source

    def discover(self, since: datetime | None) -> list[ItemRef]:
        resp = http.fetch(self.source.url)
        feed = feedparser.parse(resp.content)
        refs: list[ItemRef] = []
        for entry in feed.entries:
            link = getattr(entry, "link", "") or ""
            if not link:
                continue
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(entry, attr, None)
                if t:
                    published = datetime(*t[:6], tzinfo=timezone.utc)
                    break
            if since and published and published < since:
                continue
            refs.append(ItemRef(
                url=link,
                title=(getattr(entry, "title", "") or "").strip(),
                published_at_guess=published,
                external_id=getattr(entry, "id", "") or link,
            ))
        return refs

    def fetch(self, ref: ItemRef) -> RawDoc:
        resp = http.fetch(ref.url)
        return RawDoc(url=ref.url, html=resp.content, headers=resp.headers, published_at_guess=ref.published_at_guess)

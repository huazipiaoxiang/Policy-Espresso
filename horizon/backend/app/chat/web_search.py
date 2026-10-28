from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.chat.tools import ChatEvidence


class WebSearchError(RuntimeError):
    pass


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, str]] = []
        self._title_depth = 0
        self._snippet_depth = 0
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._title_depth = 1
            self._title = []
            self._url = _result_url(attributes.get("href") or "")
        elif self._title_depth:
            self._title_depth += 1
        if "result__snippet" in classes:
            self._snippet_depth = 1
            self._snippet = []
        elif self._snippet_depth:
            self._snippet_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._title_depth:
            self._title_depth -= 1
            if not self._title_depth:
                title = " ".join("".join(self._title).split())
                if title and self._url:
                    self.items.append({"title": title, "url": self._url, "snippet": ""})
        if self._snippet_depth:
            self._snippet_depth -= 1
            if not self._snippet_depth and self.items:
                self.items[-1]["snippet"] = " ".join("".join(self._snippet).split())[:1200]

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self._title.append(data)
        if self._snippet_depth:
            self._snippet.append(data)


def _result_url(href: str) -> str:
    parsed = urlparse(href)
    if parsed.path.startswith("/l/"):
        href = unquote(parse_qs(parsed.query).get("uddg", [""])[0])
        parsed = urlparse(href)
    return href if parsed.scheme in ("http", "https") and parsed.netloc else ""


def search_web(question: str, *, limit: int = 5) -> list[ChatEvidence]:
    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": question.strip()[:300]},
            headers={"User-Agent": "HORIZON-PolicyMonitor/0.1"},
            timeout=12,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise WebSearchError(f"实时网页检索失败：{type(exc).__name__}") from exc

    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    return [
        ChatEvidence(
            key=f"web:{index + 1}",
            kind="web_source",
            title=item["title"],
            text=item["snippet"] or "网页搜索仅返回标题，未返回可核查摘要。",
            citation={
                "id": f"web:{index + 1}", "type": "web_source",
                "title": item["title"], "url": item["url"],
            },
        )
        for index, item in enumerate(parser.items[:limit])
        if item["snippet"]
    ]

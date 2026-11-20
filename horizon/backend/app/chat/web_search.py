"""实时网页检索（多引擎）。

**出网数据边界**：只允许发送公开信息 —— 政策标题、政策主题、发文机构等
本身已公开发布的内容；严禁携带客户数据、内部评分、内部批注等非公开数据。
调用方（政策预处理、Chat 检索）必须自行保证 query 里不含敏感字段。

引擎顺序：Bing（国内可达）→ DuckDuckGo（兜底）。任一引擎无结果或失败时自动降级。
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.chat.tools import ChatEvidence

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = httpx.Timeout(8.0, connect=5.0)

# Bing 结果页结构：<li class="b_algo"><h2><a href="...">标题</a></h2>…<p>摘要</p></li>
_BING_BLOCK = re.compile(r'<li class="b_algo".*?</li>', re.S)
_BING_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BING_SNIPPET = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_TAG = re.compile(r"<[^>]+>")


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


def _plain(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _search_api(query: str, limit: int) -> list[dict[str, str]] | None:
    """可选的专业检索 API（Tavily / Serper / 博查等）。

    未配置 `SEARCH_API_URL` / `SEARCH_API_KEY` 时返回 None，由免费引擎兜底。
    请求体为通用格式 `{query, max_results}`；Tavily 额外带 `api_key` 字段。
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.search_api_url or not settings.search_api_key:
        return None
    payload: dict[str, object] = {"query": query, "max_results": limit}
    if "tavily.com" in settings.search_api_url:
        payload["api_key"] = settings.search_api_key
    response = httpx.post(
        settings.search_api_url,
        json=payload,
        headers={"Authorization": f"Bearer {settings.search_api_key}"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    results = body.get("results") or body.get("items") or body.get("data") or []
    return [
        {
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "snippet": str(item.get("content") or item.get("snippet") or ""),
        }
        for item in results
        if str(item.get("url") or "").startswith("http")
    ]


_SO_BLOCK = re.compile(r'<li class="res-list.*?</li>', re.S)
_SO_HEAD = re.compile(r'<h3[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SO_DESC = re.compile(r'class="res-desc"[^>]*>(.*?)</p>', re.S)
_SO_REDIRECT = re.compile(r'window\.location\.replace\("([^"]+)"\)')

_SO_HOSTS = ("so.com", "360.cn", "sogou.com")


def _search_so(query: str, limit: int) -> list[dict[str, str]]:
    """360 搜索：中文政策/新闻类查询的结果质量明显好于通用引擎。"""
    response = httpx.get(
        "https://www.so.com/s",
        params={"q": query},
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    items: list[dict[str, str]] = []
    for block in _SO_BLOCK.findall(response.text):
        head = _SO_HEAD.search(block)
        if not head:
            continue
        url = html.unescape(head.group(1))
        if url.startswith("//"):
            url = "https:" + url
        if not urlparse(url).netloc:
            continue
        snippet = _SO_DESC.search(block)
        items.append({
            "title": _plain(head.group(2)),
            "url": url,
            "snippet": _plain(snippet.group(1))[:1200] if snippet else "",
        })
        if len(items) >= limit:
            break
    return items


def _resolve_so_link(url: str) -> str:
    """360 的结果是 `/link?m=…` 中间页，从跳转脚本里取真实 URL（失败则保留原链接）。"""
    if not any(host in urlparse(url).netloc for host in _SO_HOSTS):
        return url
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": _UA, "Referer": "https://www.so.com/"},
            timeout=httpx.Timeout(6.0, connect=4.0),
            follow_redirects=True,
        )
        match = _SO_REDIRECT.search(response.text)
        if match:
            return html.unescape(match.group(1))
    except httpx.HTTPError:
        pass
    return url


def _search_bing(query: str, limit: int) -> list[dict[str, str]]:
    response = httpx.get(
        "https://cn.bing.com/search",
        params={"q": query, "setlang": "zh-CN", "count": max(limit * 2, 10)},
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    items: list[dict[str, str]] = []
    for block in _BING_BLOCK.findall(response.text):
        link = _BING_LINK.search(block)
        if not link:
            continue
        url = html.unescape(link.group(1))
        if not urlparse(url).netloc:
            continue
        snippet = _BING_SNIPPET.search(block)
        items.append({
            "title": _plain(link.group(2)),
            "url": url,
            "snippet": _plain(snippet.group(1))[:1200] if snippet else "",
        })
        if len(items) >= limit:
            break
    return items


def _search_duckduckgo(query: str, limit: int) -> list[dict[str, str]]:
    response = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": _UA},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    return parser.items[:limit]


_LOW_VALUE_TITLES = ("百度百科", "维基百科", "维基百科，自由的百科全书", "知乎", "百度知道")
_LOW_VALUE_HOSTS = ("baike.baidu.com", "zh.wikipedia.org", "zhihu.com")


def _useful(item: dict[str, str]) -> bool:
    """过滤无信息量的结果：无摘要、站点首页、百科/问答类页面。"""
    parsed = urlparse(item["url"])
    if not item.get("snippet"):
        return False
    if parsed.path in ("", "/"):
        return False
    if any(bad in item["title"] for bad in _LOW_VALUE_TITLES):
        return False
    return not any(bad in parsed.netloc for bad in _LOW_VALUE_HOSTS)


def _dedupe(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    """同一 URL 去重，同域最多 2 条，保证来源多样性。"""
    picked: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    per_host: dict[str, int] = {}
    for item in items:
        url = item["url"].split("#")[0]
        host = urlparse(url).netloc
        if url in seen_urls or per_host.get(host, 0) >= 2:
            continue
        seen_urls.add(url)
        per_host[host] = per_host.get(host, 0) + 1
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def search_web(question: str, *, limit: int = 5) -> list[ChatEvidence]:
    """按 Bing → DuckDuckGo 顺序检索，返回可直接引用的网页证据。"""
    query = question.strip()[:300]
    if not query:
        raise WebSearchError("检索词为空")
    errors: list[str] = []
    items: list[dict[str, str]] = []
    for engine in (_search_api, _search_so, _search_bing, _search_duckduckgo):
        try:
            raw = engine(query, limit * 3)
        except Exception as exc:  # 单引擎失败不影响其他引擎
            errors.append(f"{engine.__name__}: {type(exc).__name__}")
            continue
        if raw is None:  # 未配置的专业检索 API，直接跳过
            continue
        items = _dedupe([item for item in raw if _useful(item)], limit)
        if items:
            # 只对最终保留的结果解析跳转链接，避免为无效结果浪费请求
            items = [{**item, "url": _resolve_so_link(item["url"])} for item in items]
            break
        errors.append(f"{engine.__name__}: 无有效结果")
    if not items:
        raise WebSearchError("实时网页检索失败：" + "; ".join(errors))

    evidences: list[ChatEvidence] = []
    for index, item in enumerate(items):
        evidences.append(ChatEvidence(
            key=f"web:{index + 1}",
            kind="web_source",
            title=item["title"],
            text=item["snippet"] or "网页搜索仅返回标题，未返回可核查摘要。",
            citation={
                "id": f"web:{index + 1}", "type": "web_source",
                "title": item["title"], "url": item["url"],
            },
        ))
    return evidences

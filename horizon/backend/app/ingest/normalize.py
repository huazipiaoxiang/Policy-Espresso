"""归一化（03 §3.1）：trafilatura 正文抽取、语言识别、日期归一、附件链接抽取。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

import trafilatura
from trafilatura.metadata import extract_metadata


@dataclass
class NormalizedDoc:
    title: str
    content_text: str
    lang: str  # zh-Hant / zh-Hans / en
    published_at: datetime | None
    attachments: list[dict] = field(default_factory=list)  # [{name, url}]


_TRADITIONAL_MARKERS = set(
    "臺灣香港體學國後發現這裏麼為黨見說話語讀書車門開關長風雲電話號碼時間問題現實際會議經濟發展"
    "佈報財經監辦匯險務業數據將準構訊調議員屬現時獲廣東產權證監會"  # 繁体特有字（简体文本几乎不出现）
)
_CJK_RE = re.compile(r"[一-鿿]")
_DATE_RE = re.compile(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})")
_ATTACHMENT_RE = re.compile(r'href=["\']([^"\']+\.(?:pdf|docx?|xlsx?))(?:\?[^"\']*)?["\']', re.IGNORECASE)


def detect_lang(text: str) -> str:
    """粗粒度语言识别：CJK 占比低 → en；含繁体特征字 → zh-Hant；否则 zh-Hans。"""
    if not text:
        return ""
    sample = text[:3000]
    cjk = len(_CJK_RE.findall(sample))
    if cjk < len(sample) * 0.15:
        return "en"
    trad = sum(1 for ch in sample if ch in _TRADITIONAL_MARKERS)
    # 长文本需 ≥3 个繁体特征字防误判；短文本出现任一繁体特有字即可判定
    return "zh-Hant" if trad >= 3 or (trad >= 1 and len(sample) < 60) else "zh-Hans"


def parse_date(text: str) -> datetime | None:
    """从文本中找首个中文/ISO 日期（UTC 存不起时区信息时按 +08:00 处理）。"""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        from datetime import timedelta

        return datetime(y, mo, d, tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
    except ValueError:
        return None


_ATTACHMENT_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")


def extract_attachments(html: str, base_url: str) -> list[dict]:
    """抽取 PDF/Word/Excel 附件链接（仅登记；PDF 解析由 pipeline 调 pdf_parse.enrich_attachments）。

    只收 URL 路径本身以扩展名结尾的链接，排除 viewer.html?file=x.pdf 这类阅读器页。
    """
    from urllib.parse import urlparse

    seen, out = set(), []
    for m in _ATTACHMENT_RE.finditer(html or ""):
        url = urljoin(base_url, m.group(1))
        path = urlparse(url).path.lower()
        if not path.endswith(_ATTACHMENT_EXTS):
            continue
        if url not in seen:
            seen.add(url)
            out.append({"name": path.rsplit("/", 1)[-1], "url": url, "local_path": None, "parsed_text_path": None})
    return out


def normalize_html(html: str | bytes, url: str, *, fallback_title: str = "", fallback_date: datetime | None = None,
                   fallback_lang: str = "") -> NormalizedDoc:
    """HTML → 结构化文档。失败模式：正文抽取失败 → content_text 为空串（由调用方决定 ignored）。"""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")

    content = trafilatura.extract(html, include_links=False, include_tables=True, favor_recall=True) or ""
    meta = extract_metadata(html)

    title = (meta.title if meta and meta.title else fallback_title) or ""
    # 日期优先级：RSS/列表给的日期 > 中文页面正文日期（trafilatura 对"2026年11月1日"会误解析）> meta.date
    published = fallback_date
    if published is None and _CJK_RE.search(html[:2000]):
        published = parse_date(html[:2000])
    if published is None and meta and meta.date:
        published = parse_date(meta.date)
    if published is None:
        published = parse_date(html[:2000])
    lang = detect_lang(content or title) or fallback_lang

    return NormalizedDoc(
        title=title.strip(),
        content_text=content.strip(),
        lang=lang,
        published_at=published,
        attachments=extract_attachments(html, url),
    )

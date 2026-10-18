"""证据定位：quote → (span_start, span_end)。定位失败返回 None（该条证据作废）。"""
from __future__ import annotations

import re
import unicodedata


def normalize_for_locate(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def locate_quote(content_text: str, quote: str) -> tuple[int, int] | None:
    """在原文中定位 quote，返回**原始文本**的 [start, end) 字符区间。

    归一化比对（去空白 + NFKC），命中后把区间映射回原始文本的字符下标。
    失败返回 None，由调用方丢弃该证据。
    """
    if not content_text or not quote:
        return None
    q = normalize_for_locate(quote)
    if not q:
        return None
    norm_chars: list[str] = []
    index_map: list[int] = []  # 归一化字符 → 原文字符下标
    for i, ch in enumerate(content_text):
        n = unicodedata.normalize("NFKC", ch)
        n = re.sub(r"\s+", "", n)
        for nc in n:
            norm_chars.append(nc)
            index_map.append(i)
    norm_text = "".join(norm_chars)
    pos = norm_text.find(q)
    if pos < 0:
        return None
    start = index_map[pos]
    end = index_map[pos + len(q) - 1] + 1
    return start, end

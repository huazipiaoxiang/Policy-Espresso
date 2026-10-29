"""正文切分：为向量检索提供固定窗口 + 句读对齐的切片。

切分只做文本处理，不触碰数据库；调用方负责持久化与去重。
"""
from __future__ import annotations

import re

# 句读边界优先（中英文混排常见），找不到时退化为硬窗口，保证切片不丢字。
_BOUNDARY_RE = re.compile(r"[。！？；\n]|(?<=[.!?;])\s")

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_MAX_CHUNKS = 20


def chunk_text(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> list[str]:
    """把长正文切成 ≤size 的片段，相邻片段重叠 overlap 个字符。

    空正文返回空列表；max_chunks 控制单文档切片上限，避免超长 PDF 撑爆索引。
    """
    clean = " ".join(str(text or "").split())
    if not clean:
        return []
    size = max(200, int(size))
    overlap = max(0, min(int(overlap), size // 2))

    chunks: list[str] = []
    start = 0
    length = len(clean)
    while start < length and len(chunks) < max_chunks:
        end = min(start + size, length)
        if end < length:
            window = clean[start:end]
            # 在窗口后半段找最后一个句读边界，尽量不把一个句子劈开
            search_from = max(0, len(window) - max(1, size // 3))
            boundary = None
            for match in _BOUNDARY_RE.finditer(window, search_from):
                boundary = match.end()
            if boundary and boundary > size // 3:
                end = start + boundary
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks

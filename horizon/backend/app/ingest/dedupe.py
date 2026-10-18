"""去重（06 §5.5）：URL 归一化精确去重 + simhash64 近重复（汉明距离 ≤3）。"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_DROP_PARAMS = {"fbclid", "gclid", "spm"}  # utm_* 单独处理
_TUNIS_RE = re.compile(r"^https?://[a-z]{2}\.isd\.gov\.hk/TuniS//", re.IGNORECASE)


def canonicalize_url(url: str) -> str:
    """去 utm/fbclid/#anchor，统一 https，去 www.，去末尾 /；ISD TuniS 代理还原为真实 URL。"""
    url = url.strip()
    m = _TUNIS_RE.match(url)
    if m:
        url = "https://" + url[m.end():]
    parsed = urlparse(url)
    scheme = "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
         if k not in _DROP_PARAMS and not k.lower().startswith("utm_")]
    )
    return urlunparse((scheme, netloc, path, "", query, ""))


def rewrite_fetch_url(url: str) -> str:
    """抓取前重写：ISD TuniS 代理（sc.isd.gov.hk robots 全站禁止）还原为真实地址再抓。"""
    m = _TUNIS_RE.match(url.strip())
    return "https://" + url.strip()[m.end():] if m else url


def normalize_content(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_content(text).encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    """CJK 用字符 bigram，拉丁用词；对政策文本足够稳定。"""
    text = normalize_content(text)
    if len(text) < 2:
        return [text] if text else []
    return [text[i : i + 2] for i in range(len(text) - 1)]


def simhash64(text: str) -> int:
    """经典 simhash：token 哈希加权投影到 64 位。"""
    vec = [0] * 64
    for token in _tokens(text):
        h = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            vec[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(64):
        if vec[i] > 0:
            fingerprint |= 1 << i
    # SQLite/PG 的 BIGINT 均为有符号 64 位，掩去最高位避免溢出
    return fingerprint & (2**63 - 1)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_near_duplicate(hash_a: int, hash_b: int, *, threshold: int = 3) -> bool:
    return hamming(hash_a, hash_b) <= threshold


def title_similarity(a: str, b: str) -> float:
    """Jaccard 字符 bigram 相似度，用于跨源转载聚类提示。"""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

"""PDF 附件解析（06 §5.6）：

- 经 http 礼让层取回 bytes → 内容 sha256 去重（同 hash 复用已落盘文本，不重复解析）
- pdfplumber 抽取文本；文本层字符数 < 100 判定为扫描件（MVP 跳过 OCR，标注需人工阅读）
- 文本落盘 {storage_dir}/attachments/{sha[:2]}/{sha}.txt，路径回写 attachments JSON

失败模式：抓取/解析失败不阻塞文档入库，附件 status=failed 并记 error。
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingest import http

log = get_logger("ingest.pdf")

# 06 §5.6：文本层字符数低于此阈值判定为扫描件
TEXT_LAYER_MIN_CHARS = 100

_STATUS_PARSED = "parsed"
_STATUS_SCANNED = "scanned"
_STATUS_FAILED = "failed"
_STATUS_UNSUPPORTED = "unsupported"  # doc/docx/xls/xlsx：待 MinerU/Docling 接入

_SCANNED_NOTE = "附件为扫描件，需人工阅读"


@dataclass
class AttachmentResult:
    sha256: str = ""
    status: str = _STATUS_FAILED
    char_count: int = 0
    parsed_text_path: str | None = None
    error: str | None = None


def _attachments_root() -> Path:
    root = Path(get_settings().storage_dir) / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _paths(sha: str) -> tuple[Path, Path, Path]:
    """返回 (pdf 路径, 文本路径, 扫描件标记路径)。"""
    sub = _attachments_root() / sha[:2]
    sub.mkdir(parents=True, exist_ok=True)
    return sub / f"{sha}.pdf", sub / f"{sha}.txt", sub / f"{sha}.scanned"


_FAILED_TTL_HOURS = 24


def _failed_mark(url: str) -> Path:
    """URL 级失败负缓存：已知 404/损坏的附件 24 小时内不重抓（同一附件常被多文档引用）。"""
    sub = _attachments_root() / "failed"
    sub.mkdir(parents=True, exist_ok=True)
    return sub / f"{sha256_bytes(url.encode('utf-8'))}.txt"


def _recently_failed(url: str) -> AttachmentResult | None:
    mark = _failed_mark(url)
    if not mark.exists():
        return None
    age = datetime.now(timezone.utc).timestamp() - mark.stat().st_mtime
    if age > _FAILED_TTL_HOURS * 3600:
        return None
    return AttachmentResult(status=_STATUS_FAILED, error=f"缓存的失败: {mark.read_text(encoding='utf-8')}")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """pdfplumber 逐页抽文本。失败模式：结构损坏 → 抛异常（由调用方降级为 failed）。"""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def parse_pdf_bytes(pdf_bytes: bytes) -> AttachmentResult:
    """解析 PDF 字节流：sha256 → 命中缓存直接复用；否则抽文本并按阈值判扫描件。"""
    sha = sha256_bytes(pdf_bytes)
    pdf_path, txt_path, scanned_mark = _paths(sha)

    if txt_path.exists():  # 附件去重（06 §5.5）：同 sha256 直接复用
        text = txt_path.read_text(encoding="utf-8")
        return AttachmentResult(sha256=sha, status=_STATUS_PARSED, char_count=len(text),
                                parsed_text_path=str(txt_path))
    if scanned_mark.exists():
        return AttachmentResult(sha256=sha, status=_STATUS_SCANNED, error=_SCANNED_NOTE)

    text = extract_pdf_text(pdf_bytes)
    pdf_path.write_bytes(pdf_bytes)
    if len(text) < TEXT_LAYER_MIN_CHARS:
        scanned_mark.touch()
        log.warning("pdf_scanned", sha256=sha, char_count=len(text))
        return AttachmentResult(sha256=sha, status=_STATUS_SCANNED, char_count=len(text), error=_SCANNED_NOTE)
    txt_path.write_text(text, encoding="utf-8")
    return AttachmentResult(sha256=sha, status=_STATUS_PARSED, char_count=len(text),
                            parsed_text_path=str(txt_path))


def parse_attachment(url: str, *, timeout: float = 60.0) -> AttachmentResult:
    """抓取并解析单个 PDF 附件。失败模式：网络/限流/解析异常 → status=failed（不向上抛）。

    失败结果写 URL 级负缓存，24 小时内同一 URL 直接返回失败，避免重复抓取已知坏链。
    """
    cached = _recently_failed(url)
    if cached is not None:
        return cached
    try:
        resp = http.fetch(url, timeout=timeout)
    except Exception as e:
        log.warning("attachment_fetch_failed", url=url, error=str(e))
        _failed_mark(url).write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
        return AttachmentResult(status=_STATUS_FAILED, error=f"{type(e).__name__}: {e}")
    try:
        return parse_pdf_bytes(resp.content)
    except Exception as e:
        log.error("attachment_parse_failed", url=url, error=str(e))
        _failed_mark(url).write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
        return AttachmentResult(status=_STATUS_FAILED, error=f"{type(e).__name__}: {e}")


def enrich_attachments(attachments: list[dict], max_count: int | None = None) -> list[dict]:
    """就地丰富附件元数据：PDF 解析入库，Office 文档标记 unsupported。

    每文档最多处理前 max_count 个（默认取配置 crawl_max_attachments_per_doc）。
    """
    if max_count is None:
        max_count = get_settings().crawl_max_attachments_per_doc
    out = []
    pdf_count = 0
    for att in attachments:
        att = dict(att)
        name = (att.get("name") or att.get("url") or "").lower()
        if not name.endswith(".pdf"):
            att["status"] = _STATUS_UNSUPPORTED
            out.append(att)
            continue
        pdf_count += 1
        if pdf_count > max_count:
            att["status"] = "skipped"  # 超出每文档附件上限，留待人工
            out.append(att)
            continue
        result = parse_attachment(att["url"])
        att.update(
            sha256=result.sha256 or None, status=result.status,
            char_count=result.char_count, parsed_text_path=result.parsed_text_path,
            error=result.error,
        )
        out.append(att)
    return out

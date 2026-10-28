"""抓取管线（01 §五 Phase 1 段）：

discover → canonical URL 精确去重 → fetch → normalize → 内容 hash/simhash
→ 近重复聚类（duplicate_of）→ 变更检测（document_version）→ gate-1 过滤 → 入库

失败分级：网络/限流 retryable 记日志跳过；解析/结构 fatal 落 dead_letter（doc.status=failed）。
"""
from __future__ import annotations

from dataclasses import replace as dc_replace
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Document, DocumentVersion, Source
from app.ingest import change_detect, dedupe, gate1, http
from app.ingest.pdf_parse import enrich_attachments
from app.ingest.adapters import get_adapter
from app.ingest.normalize import normalize_html

log = get_logger("ingest.pipeline")

def _existing_by_canonical(db: Session, canonical_url: str) -> Document | None:
    return db.scalar(select(Document).where(Document.canonical_url == canonical_url))


def _find_near_duplicate(db: Session, source: Source, simhash: int) -> Document | None:
    """跨源近重复聚类（06 §5.5）：同一政策多源转载，保留先到的为 primary。

    只在近 30 天、其他源的文档中比对（同源同内容按 canonical URL 精确去重已覆盖）。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    candidates = db.scalars(
        select(Document).where(
            Document.fetched_at >= cutoff, Document.simhash.isnot(None),
            Document.source_id != source.id,
        ).limit(500)
    ).all()
    for doc in candidates:
        if doc.simhash is not None and dedupe.is_near_duplicate(simhash, doc.simhash):
            return doc
    return None


def ingest_document(db: Session, source: Source, raw, ref) -> tuple[Document | None, str]:  # noqa: ANN001
    """单条处理。返回 (document|None, outcome)：created/updated/duplicate/ignored/failed。"""
    canonical = dedupe.canonicalize_url(raw.url)
    existing = _existing_by_canonical(db, canonical)

    norm = normalize_html(
        raw.html, raw.url,
        fallback_title=ref.title, fallback_date=raw.published_at_guess, fallback_lang=source.lang,
    )
    if not norm.content_text:
        log.warning("extract_empty", url=raw.url, source=source.code)
        if existing is None:
            doc = Document(
                source_id=source.id, url=raw.url, canonical_url=canonical,
                title=norm.title or ref.title or raw.url, lang=norm.lang or source.lang,
                published_at=norm.published_at, content_text="", content_hash="",
                status="failed",
            )
            db.add(doc)
            db.flush()
            return doc, "failed"
        return existing, "failed"

    new_hash = dedupe.content_hash(norm.content_text)
    new_simhash = dedupe.simhash64(norm.content_text)

    if existing is not None:
        if existing.content_hash == new_hash:
            return existing, "unchanged"
        # 变更检测：生成 document_version
        diff = change_detect.compute_diff(existing.content_text, norm.content_text)
        version_no = len(existing.versions) + 2  # v1 = 初次入库
        db.add(DocumentVersion(
            document_id=existing.id, version_no=version_no, content_hash=new_hash,
            diff_json={"items": diff.diff}, changed_ratio=diff.changed_ratio, minor_edit=diff.minor_edit,
        ))
        existing.content_text = norm.content_text
        existing.content_hash = new_hash
        existing.simhash = new_simhash
        existing.title = norm.title or existing.title
        existing.fetched_at = datetime.now(timezone.utc)
        # 内容变更必须重新进入分析队列；重复源仍由 duplicate_of 排除。
        existing.status = "new"
        if norm.attachments:
            existing.attachments = enrich_attachments(norm.attachments)
        db.flush()
        log.info("doc_updated", url=canonical, ratio=diff.changed_ratio, minor=diff.minor_edit)
        return existing, "updated"

    doc = Document(
        source_id=source.id, url=raw.url, canonical_url=canonical,
        title=norm.title or ref.title or raw.url, lang=norm.lang or source.lang,
        published_at=norm.published_at, fetched_at=datetime.now(timezone.utc),
        content_text=norm.content_text, content_hash=new_hash, simhash=new_simhash,
        attachments=enrich_attachments(norm.attachments) if norm.attachments else norm.attachments,
        status="new",
    )
    # 跨源近重复：同一政策多源转载，保留先到的为 primary
    dup = _find_near_duplicate(db, source, new_simhash)
    if dup is not None:
        doc.duplicate_of = dup.id
        doc.status = "ignored"
        db.add(doc)
        db.flush()
        return doc, "duplicate"

    passed, hits = gate1.gate1_pass(doc.title, doc.content_text)
    if not passed:
        doc.status = "ignored"  # 非金融内容，入库备查但不进分析管线
    db.add(doc)
    db.flush()
    return doc, "created" if passed else "ignored"


def crawl_source(db: Session, source: Source) -> dict:
    """抓取单个源。返回统计 dict；源级异常向上抛由 job 记录。"""
    adapter = get_adapter(source)
    stats = {"discovered": 0, "created": 0, "updated": 0, "duplicate": 0, "ignored": 0, "failed": 0, "errors": []}

    refs = adapter.discover(since=None)
    stats["discovered"] = len(refs)
    log.info("discovered", source=source.code, count=len(refs))

    from app.core.config import get_settings

    cap = get_settings().crawl_max_items_per_source
    if cap > 0 and len(refs) > cap:
        log.info("crawl_capped", source=source.code, cap=cap)
        refs = refs[:cap]

    for ref in refs:
        canonical = dedupe.canonicalize_url(ref.url)
        try:
            fetch_url = dedupe.rewrite_fetch_url(ref.url)
            if fetch_url != ref.url:
                ref = dc_replace(ref, url=fetch_url)
            raw = adapter.fetch(ref)
            _, outcome = ingest_document(db, source, raw, ref)
            stats[outcome] = stats.get(outcome, 0) + 1
            db.commit()
        except http.RobotsDisallowedError as e:
            stats["ignored"] += 1
            stats["errors"].append(str(e))
            db.rollback()
        except http.FetchError as e:
            stats["failed"] += 1
            stats["errors"].append(f"{ref.url}: {e}")
            db.rollback()
            log.warning("fetch_failed", source=source.code, url=ref.url, error=str(e))
        except Exception as e:  # 解析/结构类 fatal
            stats["failed"] += 1
            stats["errors"].append(f"{ref.url}: fatal {type(e).__name__}: {e}")
            db.rollback()
            log.error("ingest_fatal", source=source.code, url=ref.url, error=str(e))
    return stats


def is_circuit_open(source: Source) -> bool:
    """熔断检查（06 §5.3）：连续失败 ≥5 次熔断 6 小时，期间跳过该源。"""
    until = (source.health or {}).get("circuit_open_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now(timezone.utc)
    except ValueError:
        return False


def update_source_health(db: Session, source: Source, *, ok: bool, latency_ms: int | None, stats: dict) -> None:
    """更新 source.health：连续失败、最近成功时间、本轮统计。"""
    health = dict(source.health or {})
    health["consecutive_fail"] = 0 if ok else int(health.get("consecutive_fail", 0)) + 1
    if ok:
        health["last_ok_at"] = datetime.now(timezone.utc).isoformat()
    if latency_ms is not None:
        health["avg_latency_ms"] = latency_ms
    health["last_run_stats"] = {k: v for k, v in stats.items() if k != "errors"}
    if stats.get("errors"):
        health["last_errors"] = stats["errors"][-5:]  # 保留最近 5 条错误摘要
    health["circuit_open_until"] = (
        (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        if health["consecutive_fail"] >= 5 else None
    )
    source.health = health
    db.commit()

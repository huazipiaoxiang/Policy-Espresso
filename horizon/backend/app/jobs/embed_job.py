"""切片与嵌入重建（Chat Agent 语义检索的离线通道）。

幂等：按 (document_id, chunk_index) 唯一约束 upsert；文档 content_hash 未变且已全部嵌入时跳过。
不做定时注册——重建由 /internal/jobs/embed 显式触发，避免污染调度任务集合。
"""
from __future__ import annotations

import time
from array import array
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, Policy, utcnow
from app.db.session import SessionLocal
from app.search import embedder, index as vector_index
from app.search.chunking import chunk_text

log = get_logger("jobs.embed")

EMBED_BATCH = 10


def _existing_chunks(db: Session, document_id: str) -> dict[int, DocumentChunk]:
    rows = db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).all()
    return {int(row.chunk_index): row for row in rows}


def _policy_id_of(db: Session, document_id: str) -> str | None:
    return db.scalar(select(Policy.id).where(Policy.document_id == document_id))


def embed_document(db: Session, document: Document) -> int:
    """为单篇文档重建切片与嵌入，返回写入的切片数（跳过时返回 0）。"""
    settings = get_settings()
    content_hash = document.content_hash or ""
    chunks = chunk_text(
        document.content_text,
        size=settings.search_chunk_size,
        overlap=settings.search_chunk_overlap,
        max_chunks=settings.search_chunk_max_per_doc,
    )
    existing = _existing_chunks(db, document.id)

    if not chunks:
        for row in existing.values():
            db.delete(row)
        db.flush()
        return 0

    unchanged = len(existing) >= len(chunks) and all(
        index in existing
        and existing[index].content_hash == content_hash
        and existing[index].embedding is not None
        for index in range(len(chunks))
    )
    if unchanged:
        return 0

    policy_id = _policy_id_of(db, document.id)
    written = 0
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        try:
            vectors = embedder.embed_texts(batch).vectors
        except embedder.EmbedError as exc:
            log.warning("embed_batch_failed", document_id=document.id, error=str(exc))
            return written
        for offset, (text, vector) in enumerate(zip(batch, vectors)):
            position = start + offset
            blob = array("f", [float(value) for value in vector]).tobytes()
            row = existing.get(position)
            if row is None:
                row = DocumentChunk(
                    document_id=document.id, policy_id=policy_id, chunk_index=position,
                )
                db.add(row)
            row.text = text
            row.content_hash = content_hash
            row.embedding = blob
            row.embedded_at = utcnow()
            written += 1

    # 文档变短后清理多余旧切片
    for position, row in existing.items():
        if position >= len(chunks):
            db.delete(row)
    db.flush()
    return written


def _utcnow():
    from app.db.models import utcnow

    return utcnow()


def rebuild_chunks(db: Session | None = None, *, limit: int = 0) -> dict[str, Any]:
    """全量/限量重建。limit>0 时只处理最近抓取的 limit 篇（调试用）。"""
    started = time.monotonic()
    settings = get_settings()
    if not settings.search_vector_enabled:
        return {"status": "disabled", "documents": 0, "chunks": 0}
    if not vector_index.numpy_available():
        return {"status": "numpy_missing", "documents": 0, "chunks": 0}

    owns_session = db is None
    session = db or SessionLocal()
    documents = 0
    chunks = 0
    try:
        stmt = select(Document).where(Document.content_text.isnot(None)).order_by(Document.fetched_at.desc())
        if limit and limit > 0:
            stmt = stmt.limit(int(limit))
        for document in session.scalars(stmt).unique():
            if not (document.content_text or "").strip():
                continue
            written = embed_document(session, document)
            if written:
                documents += 1
                chunks += written
        session.commit()
    except Exception as exc:
        session.rollback()
        log.warning("embed_rebuild_failed", error_type=type(exc).__name__)
        return {"status": "failed", "documents": documents, "chunks": chunks}
    finally:
        if owns_session:
            session.close()

    vector_index.invalidate()
    log.info(
        "embed_rebuild_done", documents=documents, chunks=chunks,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return {
        "status": "ok", "documents": documents, "chunks": chunks,
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> None:
    """本地直跑入口：python -m app.jobs.embed_job [limit]"""
    import sys

    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    print(rebuild_chunks(limit=limit))


if __name__ == "__main__":
    main()

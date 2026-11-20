"""存量文档去重回填：补齐「标题+正文」指纹，并把重复文档标记为 duplicate。

用法：`python -m app.jobs.dedup_job`

- 不删除任何数据：重复文档保留备查，status=duplicate、duplicate_of 指向首个入库文档；
- 已生成政策（policy）的文档不标记，避免破坏已发布内容，只计数提示；
- 幂等：重复执行不会新增标记。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Base, Document
from app.db.session import SessionLocal, engine
from app.ingest import dedupe

log = get_logger("dedup")


def backfill_fingerprints(db: Session) -> int:
    """为所有文档计算/刷新 content_fingerprint（标题 + 正文）。"""
    updated = 0
    for doc in db.scalars(select(Document).order_by(Document.fetched_at)).all():
        fingerprint = dedupe.fingerprint(doc.title, doc.content_text or "")
        if doc.content_fingerprint != fingerprint:
            doc.content_fingerprint = fingerprint
            updated += 1
    db.commit()
    return updated


def mark_duplicates(db: Session) -> dict:
    """按指纹分组，首个入库者为 primary，其余（跨源）标记 duplicate。

    与抓取链路一致：同源不同 URL 视为不同页面，不按指纹合并。
    """
    seen: dict[str, tuple[str, str]] = {}  # fingerprint -> (primary_id, primary_source_id)
    marked = 0
    skipped_with_policy = 0
    for doc in db.scalars(select(Document).order_by(Document.fetched_at)).all():
        fingerprint = doc.content_fingerprint or dedupe.fingerprint(doc.title, doc.content_text or "")
        if not fingerprint:
            continue
        if doc.status == "duplicate" or doc.duplicate_of:
            seen.setdefault(fingerprint, (doc.duplicate_of or doc.id, doc.source_id))
            continue
        primary = seen.get(fingerprint)
        if primary is None:
            seen[fingerprint] = (doc.id, doc.source_id)
            continue
        primary_id, primary_source = primary
        if primary_source == doc.source_id:  # 同源不同 URL：保留各自记录
            continue
        if doc.policy is not None:
            skipped_with_policy += 1
            continue
        doc.status = "duplicate"
        doc.duplicate_of = primary_id
        marked += 1
        log.info("marked_duplicate", document_id=doc.id, duplicate_of=primary_id, title=doc.title[:40])
    db.commit()
    return {
        "marked": marked,
        "skipped_with_policy": skipped_with_policy,
        "unique_fingerprints": len(seen),
    }


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        updated = backfill_fingerprints(db)
        stats = mark_duplicates(db)
    print(
        f"去重回填完成：指纹更新 {updated} 条，标记重复 {stats['marked']} 条，"
        f"因已有政策跳过 {stats['skipped_with_policy']} 条，唯一指纹 {stats['unique_fingerprints']} 个"
    )


if __name__ == "__main__":
    main()

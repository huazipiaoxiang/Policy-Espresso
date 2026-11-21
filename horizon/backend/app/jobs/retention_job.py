"""数据保留清理任务（B 模块）。

策略：
- B1：政策库 + 政策预处理仅保留近 5 年——删除「发布日期超 5 年且未被跟进专员标记跟进」的政策
  （及其分析/预处理等关联记录），原始文档保留；
- B2：原文库超 5 年的文档，删除其 PDF/HTML 源文件，仅保留基础信息、正文文本与原文链接，
  供搜索命中后跳转；
- B3：`Policy.followup == True`（被标记跟进）的政策永久保留，豁免 B1 清理。

用法：`python -m app.jobs.retention_job --dry-run`（只统计不删除）
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.models import Document, Policy
from app.db.session import SessionLocal, engine
from app.domain.policy_admin import delete_policy_records

log = get_logger("retention_job")

RETENTION_YEARS = 5


def _storage_root() -> Path:
    return Path(get_settings().storage_dir).resolve()


def _remove_source_file(rel: str | None) -> bool:
    """删除存储目录内的源文件（PDF/HTML 快照），返回是否实际删除。"""
    if not rel:
        return False
    root = _storage_root()
    candidate = (root / rel).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        candidate.unlink(missing_ok=True)
        return True
    return False


def _archive_doc_source_files(doc: Document) -> bool:
    """删除原文库超期文档的 PDF/HTML 源文件，保留基础信息、正文与链接。"""
    removed = False
    kept: list = []
    for att in doc.attachments or []:
        path = att.get("path") if isinstance(att, dict) else None
        if path and _remove_source_file(path):
            removed = True
            continue  # 源文件已删除，从附件列表移除该条
        kept.append(att)
    if removed:
        doc.attachments = kept
    if doc.content_html_path and _remove_source_file(doc.content_html_path):
        doc.content_html_path = None
        removed = True
    return removed


def run_retention(db: Session, *, years: int = RETENTION_YEARS, dry_run: bool = False) -> dict:
    """执行 5 年保留策略；返回统计。不 catch 单条异常（由调用方决定回滚粒度）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * years)

    # B1：删除超期且未标记跟进的政策（原文保留，交 B2 处理）
    stale_policies = db.scalars(
        select(Policy).where(
            Policy.published_at < cutoff,
            Policy.followup.is_(False),
        )
    ).all()
    for policy in stale_policies:
        delete_policy_records(db, policy)

    # B2：超期原文删 PDF/HTML 源文件
    stale_docs = db.scalars(
        select(Document).where(Document.published_at < cutoff)
    ).all()
    archived_docs = sum(1 for doc in stale_docs if _archive_doc_source_files(doc))

    if not dry_run:
        db.commit()

    return {
        "cutoff": cutoff.isoformat(),
        "policies_deleted": len(stale_policies),
        "documents_archived": archived_docs,
        "documents_stale": len(stale_docs),
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="执行 5 年数据保留清理")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不删除")
    parser.add_argument("--years", type=int, default=RETENTION_YEARS)
    args = parser.parse_args()

    configure_logging()
    from app.db.models import Base

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = run_retention(db, years=args.years, dry_run=args.dry_run)
    print(
        f"保留清理完成：删除政策 {stats['policies_deleted']} 条 | 归档原文 {stats['documents_archived']}/{stats['documents_stale']} 篇"
        + ("（dry-run）" if stats["dry_run"] else "")
    )


if __name__ == "__main__":
    main()

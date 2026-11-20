"""无关政策清理任务：按 Skill「irrelevant_policy_cleanup」扫描存量政策。

用法：`python -m app.jobs.cleanup_job --dry-run`（只判定不删除）

- 只删除「对汇丰完全没有影响」的政策及原文：相关性/合规/差异维度均为 0、
  目标实体 low/not_mentioned、适用范围不含外资行、无受影响业务线、
  P3 且综合分低于阈值、未发布、无使用者反馈；
- 每次删除都写审计（delete_policy / delete_document），文件同时清理。
"""
from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.cleanup import assess_hsbc_impact, cleanup_policy_if_irrelevant
from app.core.logging import configure_logging, get_logger
from app.db.models import Base, Policy
from app.db.session import SessionLocal, engine

log = get_logger("cleanup_job")


def cleanup_all(db: Session, *, dry_run: bool = False) -> dict:
    policy_ids = list(db.scalars(select(Policy.id)).all())
    total = len(policy_ids)
    deleted = 0
    kept = 0
    errors: list[str] = []
    candidates: list[str] = []

    for policy_id in policy_ids:
        policy = db.get(Policy, policy_id)
        if policy is None:
            continue
        try:
            verdict = assess_hsbc_impact(db, policy)
            if verdict["verdict"] != "none":
                kept += 1
                continue
            if dry_run:
                candidates.append(policy_id)
                continue
            result = cleanup_policy_if_irrelevant(db, policy)
            if result.get("deleted"):
                deleted += 1
            else:
                kept += 1
        except Exception as exc:  # 单条失败不影响整批
            db.rollback()
            errors.append(f"{policy_id}: {type(exc).__name__}: {exc}")
            log.warning("cleanup_failed", policy_id=policy_id, error_type=type(exc).__name__)

    return {
        "total": total,
        "deleted": deleted,
        "kept": kept,
        "dry_run_candidates": candidates,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="清理对汇丰完全没有影响的政策及原文")
    parser.add_argument("--dry-run", action="store_true", help="只判定，不删除")
    args = parser.parse_args()

    configure_logging()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = cleanup_all(db, dry_run=args.dry_run)
    print(
        f"无关政策清理完成：共 {stats['total']} 条 | 删除 {stats['deleted']} | 保留 {stats['kept']} | "
        f"异常 {len(stats['errors'])}"
    )
    if stats["dry_run_candidates"]:
        print(f"可清理候选（dry-run）：{', '.join(stats['dry_run_candidates'])}")


if __name__ == "__main__":
    main()

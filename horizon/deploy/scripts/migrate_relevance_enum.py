#!/usr/bin/env python3
"""旧相关性枚举 → 三级相关性枚举（high/medium/low/not_mentioned/na）数据迁移。

用法：
    python deploy/scripts/migrate_relevance_enum.py [--db ../backend/horizon.db] [--dry-run] [--reverse]

映射（与 docs/05 p3_scope 判定规则一致）：
    covered  → high   被覆盖 → 高度相关
    excluded → low    被排除（境内/中资限定）→ 低度相关
其余取值（high/medium/low/not_mentioned/na）保持不变，可重复执行。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

MAP = {"covered": "high", "excluded": "low"}
REVERSE_MAP = {"high": "covered", "low": "excluded"}
TABLES = [("policy", "target_entity_status"), ("scope_judgement", "result")]


def migrate(conn: sqlite3.Connection, mapping: dict[str, str], *, dry_run: bool) -> None:
    for table, column in TABLES:
        for source, target in mapping.items():
            count = conn.execute(
                f"select count(*) from {table} where {column} = ?", (source,)  # noqa: S608 - 表名来自上方固定常量
            ).fetchone()[0]
            print(f"{table}.{column}: {source} -> {target}  ({count} 行)")
            if count and not dry_run:
                conn.execute(f"update {table} set {column} = ? where {column} = ?", (target, source))
    if not dry_run:
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).resolve().parents[2] / "backend/horizon.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reverse", action="store_true", help="回滚为旧枚举（high→covered、low→excluded）")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"数据库文件不存在: {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    try:
        print(f"目标库：{args.db}{'（试运行）' if args.dry_run else ''}")
        migrate(conn, REVERSE_MAP if args.reverse else MAP, dry_run=args.dry_run)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

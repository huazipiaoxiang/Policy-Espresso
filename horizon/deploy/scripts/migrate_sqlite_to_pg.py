#!/usr/bin/env python3
"""SQLite → PostgreSQL 迁移（10 §3 步骤 1）：逐表 upsert，向量列重算。

用法：
    DATABASE_URL=postgresql+psycopg://horizon:horizon@localhost:5432/horizon \
    SQLITE_PATH=../backend/horizon.db \
    python deploy/scripts/migrate_sqlite_to_pg.py

幂等：按主键 upsert（ON CONFLICT DO UPDATE），可重复执行。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

TABLES = [
    "source", "job_run", "document", "document_version", "policy", "assessment",
    "evidence", "scope_judgement", "case", "policy_case_link", "review_task",
    "review_decision", "alert", "dispatch", "studio_project", "proposal",
    "audit_log", "llm_call_log",
]


def main() -> None:
    import sqlalchemy as sa

    sqlite_path = os.environ.get("SQLITE_PATH", "../backend/horizon.db")
    pg_url = os.environ.get("DATABASE_URL", "")
    if not pg_url.startswith("postgresql"):
        print("DATABASE_URL 必须指向 PostgreSQL（目标库），已中止")
        sys.exit(1)
    if not Path(sqlite_path).exists():
        print(f"SQLite 文件不存在: {sqlite_path}")
        sys.exit(1)

    src = sa.create_engine(f"sqlite:///{sqlite_path}")
    dst = sa.create_engine(pg_url)

    total = 0
    with src.connect() as s, dst.begin() as d:
        for table in TABLES:
            rows = [dict(r) for r in s.execute(sa.text(f"SELECT * FROM {table}"))]
            if not rows:
                print(f"[skip] {table}: 0 行")
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            col_list = ", ".join(f'"{c}"' for c in cols)
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c != "id")
            stmt = sa.text(
                f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) '
                f'ON CONFLICT (id) DO UPDATE SET {updates}'
            )
            for row in rows:
                d.execute(stmt, row)
            total += len(rows)
            print(f"[ok] {table}: {len(rows)} 行 upsert")
    print(f"迁移完成，共 {total} 行。下一步：接入 EmbeddingProvider 重算向量列。")


if __name__ == "__main__":
    main()

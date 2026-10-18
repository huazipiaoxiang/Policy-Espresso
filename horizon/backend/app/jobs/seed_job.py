"""seed 导入：数据源清单 / 主题词表 / 目标实体 / 历史案例 / 合成客户。

用法：make seed（或 python -m app.jobs.seed_job）。幂等：按 code/名称去重。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Case, Source
from app.db.session import SessionLocal

log = get_logger("jobs.seed")

SEED_DIR = Path(os.environ.get("SEED_DIR", Path(__file__).resolve().parents[3] / "seed"))


def seed_sources(db) -> int:  # noqa: ANN001
    """幂等 upsert：按 code 去重；已存在的源同步 url/adapter/config 等字段（seed 文件为准）。"""
    path = SEED_DIR / "sources.json"
    if not path.exists():
        log.warning("seed_file_missing", path=str(path))
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for row in rows:
        existing = db.scalar(select(Source).where(Source.code == row["code"]))
        if existing is None:
            db.add(Source(**row))
            created += 1
            continue
        for field, value in row.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
    db.commit()
    return created


def seed_cases(db) -> int:  # noqa: ANN001
    path = SEED_DIR / "cases.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for row in rows:
        if db.scalar(select(Case).where(Case.title == row["title"])):
            continue
        db.add(Case(**row))
        created += 1
    db.commit()
    return created


def main() -> None:
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)  # 本地直跑兜底；docker 走 alembic
    with SessionLocal() as db:
        n_src = seed_sources(db)
        n_case = seed_cases(db)
    print(f"seed 完成：新增数据源 {n_src}，案例 {n_case}")


if __name__ == "__main__":
    main()

"""政策预处理表格重建：按当前政策与评估结果重算全部预处理记录。

用法：`python -m app.jobs.preprocess_job`

- 幂等：逐政策 upsert，不删数据；
- 用于规则升级后回填（影响业务/客户类型兜底、百分比降级估算等口径调整）；
- 输出本次重建的覆盖率，便于确认默认值问题是否修好。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Base, Policy
from app.db.session import SessionLocal, engine
from app.domain.preprocess import upsert_preprocess

log = get_logger("preprocess_job")


def rebuild_all(db: Session) -> dict:
    total = 0
    with_business = 0
    with_segments = 0
    estimated = 0
    fallback_business = 0
    policies = db.scalars(select(Policy)).all()
    for policy in policies:
        record = upsert_preprocess(db, policy)
        total += 1
        if total % 10 == 0:
            print(f"  已重建 {total}/{len(policies)} 条（含联网检索）", flush=True)
        if record.affected_business:
            with_business += 1
        if record.customer_segments:
            with_segments += 1
        extras = record.extras or {}
        if extras.get("estimated_dimensions"):
            estimated += 1
        if "规则推断" in str(extras.get("business_basis", "")):
            fallback_business += 1
    db.commit()
    return {
        "total": total,
        "with_business": with_business,
        "with_segments": with_segments,
        "estimated_percentages": estimated,
        "fallback_business": fallback_business,
    }


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = rebuild_all(db)
    print(
        f"预处理重建完成：共 {stats['total']} 条 | 影响业务非空 {stats['with_business']} | "
        f"客户类型非空 {stats['with_segments']} | 关键词兜底业务线 {stats['fallback_business']} | "
        f"百分比含降级估算 {stats['estimated_percentages']}"
    )


if __name__ == "__main__":
    main()

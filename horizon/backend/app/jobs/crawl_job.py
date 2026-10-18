"""抓取任务（Phase 1 真实管线）。幂等键：(source_id, job_type, run_window)，30 分钟窗口。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import JobRun, Source
from app.ingest.pipeline import crawl_source, is_circuit_open, update_source_health

log = get_logger("jobs.crawl")


def current_window(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%d%H") + ("00" if now.minute < 30 else "30")


def enqueue_crawl(db: Session, source: Source) -> str:
    """登记一次抓取运行；同窗口重复触发返回已有 job_id，不重复执行。"""
    window = current_window()
    job = JobRun(job_type="crawl", source_id=source.id, run_window=window, status="running")
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(JobRun)
            .filter(JobRun.source_id == source.id, JobRun.job_type == "crawl", JobRun.run_window == window)
            .first()
        )
        return existing.id if existing else ""
    return job.id


def run_crawl(db: Session, source: Source, job_id: str | None = None) -> dict:
    """执行单源抓取并回写 job_run 与 source.health。"""
    job = db.get(JobRun, job_id) if job_id else None
    try:
        stats = crawl_source(db, source)
        ok = stats["discovered"] > 0 or not stats["errors"]
        if job:
            job.status = "ok" if ok else "failed"
            job.stats = stats
            job.error = "; ".join(stats["errors"][-3:]) or None
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        update_source_health(db, source, ok=ok, latency_ms=None, stats=stats)
        return stats
    except Exception as e:
        log.error("crawl_source_failed", source=source.code, error=str(e))
        if job:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        update_source_health(db, source, ok=False, latency_ms=None, stats={"errors": [str(e)]})
        return {"discovered": 0, "created": 0, "failed": 1, "errors": [str(e)]}


def main() -> None:
    """make crawl 入口：对全部启用源各跑一次。"""
    from app.core.logging import configure_logging
    from app.db.models import Base
    from app.db.session import SessionLocal, engine

    configure_logging()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sources = db.query(Source).filter(Source.enabled.is_(True)).all()
        if not sources:
            print("无启用数据源，请先 make seed")
            return
        total_new = 0
        for src in sources:
            if is_circuit_open(src):
                until = (src.health or {}).get("circuit_open_until")
                print(f"[{src.code}] 熔断中，跳过（至 {until}）")
                continue
            job_id = enqueue_crawl(db, src)
            stats = run_crawl(db, src, job_id)
            total_new += stats.get("created", 0)
            errs = f" | 错误 {len(stats.get('errors', []))}" if stats.get("errors") else ""
            print(
                f"[{src.code}] 发现 {stats.get('discovered', 0)} | 新增 {stats.get('created', 0)} | "
                f"更新 {stats.get('updated', 0)} | 重复 {stats.get('duplicate', 0)} | "
                f"忽略 {stats.get('ignored', 0)} | 失败 {stats.get('failed', 0)}{errs}"
            )
        print(f"本轮合计新增 {total_new} 条")


if __name__ == "__main__":
    main()

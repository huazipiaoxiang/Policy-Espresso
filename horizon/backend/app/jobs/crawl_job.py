"""抓取任务：按日幂等执行启用源，并持久化逐源 JobRun。"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import JobRun, Source
from app.ingest.pipeline import crawl_source, is_circuit_open, update_source_health

log = get_logger("jobs.crawl")


def current_window(now: datetime | None = None) -> str:
    """返回调度时区内的日窗口，供每日抓取幂等键使用。"""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo(get_settings().scheduler_timezone)).strftime("%Y%m%d")


def enqueue_crawl(db: Session, source: Source) -> str:
    """登记每日单源运行；同日已有运行时返回空串，避免重复执行。"""
    window = current_window()
    job = JobRun(job_type="crawl", source_id=source.id, run_window=window, status="running")
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return ""
    return job.id


def run_crawl(db: Session, source: Source, job_id: str | None = None) -> dict:
    """执行单源抓取并回写 job_run 与 source.health。"""
    job = db.get(JobRun, job_id) if job_id else None
    try:
        stats = crawl_source(db, source)
        ok = stats["failed"] == 0
        if job:
            job.status = "ok" if ok else "failed"
            job.stats = stats
            job.error = "; ".join(stats["errors"][-3:]) or None
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        update_source_health(db, source, ok=ok, latency_ms=None, stats=stats)
        return stats
    except Exception as e:
        db.rollback()
        log.error("crawl_source_failed", source=source.code, error=str(e))
        job = db.get(JobRun, job_id) if job_id else None
        if job:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        update_source_health(db, source, ok=False, latency_ms=None, stats={"errors": [str(e)]})
        return {"discovered": 0, "created": 0, "failed": 1, "errors": [str(e)]}


def run_source_now(db: Session, source: Source) -> dict:
    """管理员「立即抓取」：当场执行抓取并接着分析，运行记录按当日第几次手动抓取登记。

    与每日任务的区别只在幂等键：每日按日窗口（同日不重复跑），手动抓取必须每次都能执行，
    否则接口只会留下一条永远 running 的记录，按钮等于什么都没做。
    """
    day = current_window()
    attempts = db.scalar(
        select(func.count(JobRun.id)).where(
            JobRun.source_id == source.id,
            JobRun.job_type == "crawl",
            JobRun.run_window.like(f"{day}#%"),
        )
    ) or 0
    job = JobRun(job_type="crawl", source_id=source.id, run_window=f"{day}#{attempts + 1}", status="running")
    db.add(job)
    db.commit()
    stats = run_crawl(db, source, job.id)
    from app.jobs.scheduler import analyze_all_pending

    analysis = analyze_all_pending()
    return {
        "job_id": job.id,
        "discovered": stats.get("discovered", 0),
        "created": stats.get("created", 0),
        "updated": stats.get("updated", 0),
        "failed": stats.get("failed", 0) + analysis.get("failed", 0),
        "analyzed": analysis.get("analyzed", 0),
        "errors": stats.get("errors", [])[:3] + analysis.get("errors", [])[:1],
    }


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
            if not job_id:
                print(f"[{src.code}] 今日已有运行记录，跳过重复执行")
                continue
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

"""APScheduler 调度：每日抓取后分析、逐源隔离、小时健康与可配置周心跳。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import JobRun, Source
from app.db.session import SessionLocal
from app.ingest.pipeline import is_circuit_open
from app.jobs.analyze_job import analyze_pending
from app.jobs.crawl_job import current_window, enqueue_crawl, run_crawl
from app.jobs.health_job import run_health_check

log = get_logger("jobs.scheduler")
_crawl_lock = Lock()
_analyze_lock = Lock()
_heartbeat_lock = Lock()


def _empty_stats() -> dict:
    return {"sources": 0, "created": 0, "updated": 0, "failed": 0, "errors": []}


def _record_crawl_failure(db, source: Source, job_id: str | None, error: Exception) -> None:  # noqa: ANN001
    """记录调度入口异常；单源失败不得中止其他源。"""
    db.rollback()
    job = db.get(JobRun, job_id) if job_id else None
    if job is None:
        job = db.scalar(select(JobRun).where(
            JobRun.source_id == source.id,
            JobRun.job_type == "crawl",
            JobRun.run_window == current_window(),
        ))
    if job is None:
        job = JobRun(job_type="crawl", source_id=source.id, run_window=current_window())
        db.add(job)
    job.status = "failed"
    job.error = f"{type(error).__name__}: {error}"
    job.finished_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        # 另一进程已登记同一日窗口时，保留其运行记录。
        db.rollback()


def crawl_all() -> dict:
    """每日抓取全部启用源；单源失败隔离，随后仅分析 new/changed 文档。"""
    if not _crawl_lock.acquire(blocking=False):
        log.info("crawl_skipped_already_running")
        return {"status": "already_running", **_empty_stats()}
    try:
        with SessionLocal() as db:
            sources = db.query(Source).filter(Source.enabled.is_(True)).all()
            stats = _empty_stats()
            stats["sources"] = len(sources)
            for src in sources:
                if is_circuit_open(src):
                    log.warning("crawl_skipped_circuit_open", source=src.code)
                    continue
                job_id = None
                try:
                    job_id = enqueue_crawl(db, src)
                    if not job_id:
                        continue  # 同日已有运行记录，不重复执行
                    source_stats = run_crawl(db, src, job_id)
                except Exception as e:
                    db.rollback()
                    _record_crawl_failure(db, src, job_id, e)
                    source_stats = {"failed": 1, "errors": [f"{type(e).__name__}: {e}"]}
                    log.error("crawl_source_failed", source=src.code, error=str(e))
                for key in ("created", "updated", "failed"):
                    stats[key] += source_stats.get(key, 0)
                stats["errors"].extend(source_stats.get("errors", []))
                log.info("crawl_done", source=src.code, **{k: v for k, v in source_stats.items() if k != "errors"})
            analyze_stats = analyze_all_pending()
            stats.update({k: v for k, v in analyze_stats.items() if k in ("analyzed", "skipped", "errors")})
            stats["failed"] += analyze_stats.get("failed", 0)
            return stats
    finally:
        _crawl_lock.release()


def analyze_all_pending() -> dict:
    """持久化分析 JobRun；原子文档认领防止并发重复分析。"""
    if not _analyze_lock.acquire(blocking=False):
        return {"analyzed": 0, "skipped": 0, "failed": 0, "errors": [], "status": "already_running"}
    try:
        with SessionLocal() as db:
            job = JobRun(job_type="analyze", run_window=current_window(), status="running")
            db.add(job)
            db.commit()
            try:
                stats = {"analyzed": 0, "skipped": 0, "failed": 0, "errors": []}
                while True:
                    batch = analyze_pending(db)
                    for key in ("analyzed", "skipped", "failed"):
                        stats[key] += batch[key]
                    stats["errors"].extend(batch["errors"])
                    if sum(batch[key] for key in ("analyzed", "skipped", "failed")) < 10:
                        break
                job.status = "failed" if stats["failed"] else "ok"
                job.stats = stats
                job.error = "; ".join(stats["errors"][-3:]) or None
                if stats["analyzed"] or stats["failed"]:
                    log.info("analyze_done", **stats)
                return stats
            except Exception as e:
                db.rollback()
                job = db.get(JobRun, job.id)
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
                log.error("analyze_job_failed", error=str(e))
                return {"analyzed": 0, "skipped": 0, "failed": 1, "errors": [job.error]}
            finally:
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
    finally:
        _analyze_lock.release()


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    timezone = ZoneInfo(settings.scheduler_timezone)
    scheduler = BackgroundScheduler(
        timezone=timezone,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    scheduler.add_job(
        crawl_all, CronTrigger(hour=9, minute=0, timezone=timezone), id="crawl_all",
        replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_health_check, CronTrigger(minute=0, timezone=timezone), id="health_check",
        replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _heartbeat,
        CronTrigger.from_crontab(settings.scheduler_heartbeat_cron, timezone=timezone),
        id="heartbeat", replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=3600,
    )
    return scheduler


def _heartbeat() -> None:
    """可配置 cron 的轻量心跳，运行结果写入 JobRun 供状态接口查询。"""
    if not _heartbeat_lock.acquire(blocking=False):
        return
    try:
        with SessionLocal() as db:
            job = JobRun(job_type="heartbeat", run_window=current_window(), status="running")
            db.add(job)
            db.commit()
            try:
                stale_before = datetime.now(timezone.utc) - timedelta(hours=24)
                stale_jobs = db.scalars(select(JobRun).where(
                    JobRun.job_type.in_(["crawl", "analyze", "health"]),
                    JobRun.status == "running",
                    JobRun.started_at < stale_before,
                )).all()
                stale_ids = [item.id for item in stale_jobs]
                job.status = "failed" if stale_ids else "ok"
                job.stats = {
                    "heartbeat": "ok", "checked_jobs": ["crawl", "analyze", "health"],
                    "stale_jobs": stale_ids,
                }
                job.error = f"发现超过 24 小时未结束的后台任务：{', '.join(stale_ids)}" if stale_ids else None
                log.debug("scheduler_heartbeat", stale_jobs=stale_ids)
            except Exception as e:
                db.rollback()
                job = db.get(JobRun, job.id)
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
                log.error("heartbeat_failed", error=str(e))
            finally:
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
    finally:
        _heartbeat_lock.release()

"""APScheduler 调度（03 §3.5）。云端如需换 ARQ/Celery，业务入口函数签名不变。"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.db.models import JobRun, Source
from app.db.session import SessionLocal
from app.ingest.pipeline import is_circuit_open
from app.jobs.analyze_job import analyze_pending
from app.jobs.crawl_job import enqueue_crawl, run_crawl
from app.jobs.health_job import run_health_check

log = get_logger("jobs.scheduler")


def crawl_all() -> None:
    """每 30 分钟：对全部启用源各跑一轮抓取；熔断中的源跳过。"""
    with SessionLocal() as db:
        sources = db.query(Source).filter(Source.enabled.is_(True)).all()
        for src in sources:
            if is_circuit_open(src):
                log.warning("crawl_skipped_circuit_open", source=src.code)
                continue
            job_id = enqueue_crawl(db, src)
            job = db.get(JobRun, job_id) if job_id else None
            if job is None or job.status != "running":
                continue  # 同窗口已跑过（如手动 make crawl），不重复执行
            stats = run_crawl(db, src, job_id)
            log.info("crawl_done", source=src.code, **{k: v for k, v in stats.items() if k != "errors"})


def analyze_all_pending() -> None:
    """每 5 分钟：分析待处理文档（Phase 2 接入）。"""
    with SessionLocal() as db:
        stats = analyze_pending(db)
        if stats["analyzed"] or stats["failed"]:
            log.info("analyze_done", **stats)


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(crawl_all, CronTrigger(minute="*/30"), id="crawl_all", replace_existing=True)
    scheduler.add_job(analyze_all_pending, CronTrigger(minute="*/5"), id="analyze_pending", replace_existing=True)
    scheduler.add_job(run_health_check, CronTrigger(minute=0), id="health_check", replace_existing=True)
    scheduler.add_job(_heartbeat, CronTrigger(day_of_week="mon", hour=0), id="weekly_digest", replace_existing=True)  # 08:00 HKT
    return scheduler


def _heartbeat() -> None:
    log.debug("scheduler_tick")

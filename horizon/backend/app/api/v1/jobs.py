"""任务运行历史与调度状态。"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_api_key, require_roles
from app.db.models import JobRun
from app.db.session import get_db
from app.jobs.scheduler import build_scheduler

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key), Depends(require_roles("admin"))])


@router.get("/status")
def scheduler_status(db: Session = Depends(get_db)):
    """返回各调度任务的最近一次结果/错误与下一次触发时间。"""
    scheduler = build_scheduler()
    jobs = []
    job_types = {"crawl_all": "crawl", "health_check": "health", "heartbeat": "heartbeat"}
    for scheduled in scheduler.get_jobs():
        latest = db.scalars(
            select(JobRun).where(JobRun.job_type == job_types[scheduled.id])
            .order_by(JobRun.started_at.desc()).limit(1)
        ).first()
        jobs.append({
            "job_type": scheduled.id,
            "next_run_at": scheduled.trigger.get_next_fire_time(None, datetime.now(scheduler.timezone)),
            "last_run": None if latest is None else {
                "id": latest.id, "status": latest.status, "stats": latest.stats,
                "error": latest.error, "started_at": latest.started_at, "finished_at": latest.finished_at,
            },
        })
    latest = db.scalars(
        select(JobRun).where(JobRun.job_type == "analyze").order_by(JobRun.started_at.desc()).limit(1)
    ).first()
    jobs.append({
        "job_type": "analyze_pending",
        "next_run_at": scheduler.get_job("crawl_all").trigger.get_next_fire_time(None, datetime.now(scheduler.timezone)),
        "last_run": None if latest is None else {
            "id": latest.id, "status": latest.status, "stats": latest.stats,
            "error": latest.error, "started_at": latest.started_at, "finished_at": latest.finished_at,
        },
    })
    return {"jobs": jobs}


@router.get("")
def list_jobs(page: int = 1, page_size: int = 20, job_type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(JobRun).order_by(JobRun.started_at.desc())
    if job_type:
        stmt = stmt.where(JobRun.job_type == job_type)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.query(JobRun).count()
    return {
        "items": [
            {
                "id": j.id, "job_type": j.job_type, "source_id": j.source_id,
                "run_window": j.run_window, "status": j.status, "stats": j.stats,
                "error": j.error, "started_at": j.started_at, "finished_at": j.finished_at,
            }
            for j in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }

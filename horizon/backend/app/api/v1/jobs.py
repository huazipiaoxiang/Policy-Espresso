"""任务运行历史（04 §4.2）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import JobRun
from app.db.session import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


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

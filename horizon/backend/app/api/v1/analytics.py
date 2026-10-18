"""KPI 汇总（雷达页顶条）。"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas import AnalyticsOverview
from app.core.security import require_api_key
from app.db.models import JobRun, Policy, Source
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])

TZ_HK = ZoneInfo("Asia/Hong_Kong")


@router.get("/overview", response_model=AnalyticsOverview)
def overview(db: Session = Depends(get_db)):
    # "今日新增"按香港时区（UTC+8）的今天 0 点统计，转 UTC 后与库内 UTC 时间比较
    today_start = datetime.now(TZ_HK).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today_new = db.scalar(select(func.count(Policy.id)).where(Policy.published_at >= today_start)) or 0
    pending = db.scalar(
        select(func.count(Policy.id)).where(Policy.status.in_(["pending_review", "in_review"]))
    ) or 0
    p0p1 = db.scalar(
        select(func.count(Policy.id)).where(
            Policy.priority.in_(["P0", "P1"]),
            Policy.status.notin_(["published", "archived", "rejected"]),
        )
    ) or 0
    sources_total = db.scalar(select(func.count(Source.id))) or 0
    unhealthy = len([s for s in db.scalars(select(Source)).all() if (s.health or {}).get("consecutive_fail", 0) >= 3])
    last_crawl = db.scalar(
        select(func.max(JobRun.finished_at)).where(JobRun.job_type == "crawl", JobRun.status == "ok")
    )
    return AnalyticsOverview(
        today_new=today_new,
        pending_review=pending,
        p0_p1_open=p0p1,
        avg_response_min=None,  # Phase 3 按审核决策时间计算
        sources_total=sources_total,
        sources_unhealthy=unhealthy,
        last_crawl_at=last_crawl,
    )

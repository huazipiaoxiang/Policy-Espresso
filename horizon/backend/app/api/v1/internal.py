"""内部任务触发（10 §2）：函数计算 FC 定时调用，带签名令牌。"""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.jobs.crawl_job import run_crawl
from app.jobs.scheduler import crawl_all

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_token(x_job_token: str | None, settings: Settings) -> None:
    if not settings.job_trigger_token:
        raise ApiError("TRIGGER_DISABLED", "未配置 JOB_TRIGGER_TOKEN，内部触发已禁用", 403)
    if x_job_token != settings.job_trigger_token:
        raise ApiError("UNAUTHORIZED", "签名令牌错误", 401)


@router.post("/jobs/crawl")
def trigger_crawl(
    x_job_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """FC 定时抓取入口（30min）。ECS 内 APScheduler 与 FC 二选一，避免双跑。"""
    _check_token(x_job_token, settings)
    crawl_all()
    return {"status": "ok", "job": "crawl_all"}


@router.post("/jobs/analyze")
def trigger_analyze(
    x_job_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """FC 定时分析入口（5min）。"""
    from app.jobs.scheduler import analyze_all_pending

    _check_token(x_job_token, settings)
    analyze_all_pending()
    return {"status": "ok", "job": "analyze_pending"}

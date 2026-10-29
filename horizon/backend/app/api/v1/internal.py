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
    """FC 每日抓取并分析入口；与 APScheduler 双触发时按日幂等。"""
    _check_token(x_job_token, settings)
    crawl_all()
    return {"status": "ok", "job": "crawl_all"}


@router.post("/jobs/analyze")
def trigger_analyze(
    x_job_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """手动/FC 补偿分析入口；文档级原子认领避免重复分析。"""
    from app.jobs.scheduler import analyze_all_pending

    _check_token(x_job_token, settings)
    analyze_all_pending()
    return {"status": "ok", "job": "analyze_pending"}


@router.post("/jobs/embed")
def trigger_embed(
    x_job_token: str | None = Header(default=None),
    limit: int = 0,
    settings: Settings = Depends(get_settings),
):
    """重建正文切片与向量索引（Chat Agent 语义检索通道）。

    未配置 SEARCH_VECTOR_ENABLED / 缺 numpy / 嵌入不可达时返回 disabled|numpy_missing，不报错。
    limit>0 只处理最近抓取的 limit 篇，便于调试。
    """
    from app.jobs.embed_job import rebuild_chunks

    _check_token(x_job_token, settings)
    result = rebuild_chunks(limit=limit)
    return {"job": "embed", **result}

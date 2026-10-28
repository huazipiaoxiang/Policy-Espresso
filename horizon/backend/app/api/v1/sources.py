"""数据源管理（04 §4.2）。路由只做参数校验与编排。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas import Page, SourceCreate, SourceOut, SourcePatch
from app.core.errors import ApiError, not_found
from app.core.security import require_api_key, require_roles
from app.db.models import JobRun, Source
from app.db.session import get_db
from app.ingest.pipeline import is_circuit_open
from app.jobs.crawl_job import run_source_now

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_api_key), Depends(require_roles("admin"))])


@router.get("", response_model=Page[SourceOut])
def list_sources(page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    stmt = select(Source).order_by(Source.tier, Source.code)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.query(Source).count()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=SourceOut, status_code=201)
def create_source(body: SourceCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Source).where(Source.code == body.code)):
        raise ApiError("DUPLICATE_CODE", f"数据源 code 已存在: {body.code}", 409)
    src = Source(**body.model_dump())
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.patch("/{source_id}", response_model=SourceOut)
def patch_source(source_id: str, body: SourcePatch, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src:
        raise not_found("数据源", source_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(src, field, value)
    db.commit()
    db.refresh(src)
    return src


@router.post("/{source_id}/run")
def run_source(source_id: str, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src:
        raise not_found("数据源", source_id)
    if not src.enabled:
        raise ApiError("SOURCE_DISABLED", f"「{src.name}」已停用，请先启用后再抓取", 409)
    if is_circuit_open(src):
        raise ApiError("CIRCUIT_OPEN", f"「{src.name}」连续失败后处于熔断冷却中，请稍后再试", 409)
    if db.scalar(select(JobRun).where(
        JobRun.source_id == src.id, JobRun.job_type == "crawl", JobRun.status == "running",
    )):
        raise ApiError("CRAWL_RUNNING", f"「{src.name}」上一轮抓取还没有结束，请等待完成后再试", 409)
    result = run_source_now(db, src)
    return {"status": "failed" if result["failed"] else "ok", **result}

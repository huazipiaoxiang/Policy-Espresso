"""审计查询与导出（04 §4.2 /admin/audit；10 §8 保留 ≥7 年）。"""
import csv
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_api_key, require_roles
from app.db.models import AuditLog, JobRun, LLMCallLog, Source
from app.db.session import get_db

# 审计查询只读，运营角色均可查看（发布中心/原文库的审计跳转入口依赖此权限）；
# 导出与模型台账仍仅限管理员。
router = APIRouter(prefix="/admin", tags=["audit"], dependencies=[Depends(require_api_key)])

# 系统运行日志的任务类型标签（JobRun.job_type → 展示名）
JOB_TYPE_LABELS = {
    "crawl": "抓取政策",
    "analyze": "政策分析",
    "health": "健康检查",
    "heartbeat": "心跳巡检",
    "retention": "保留清理",
    "digest": "摘要生成",
}


@router.get("/system-logs", dependencies=[Depends(require_roles("admin", "processor"))])
def list_system_logs(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db)):
    """系统运行日志（按天分组）：每日抓取/分析/健康检查/心跳/保留等运行记录，含失败错误。

    数据源为 JobRun（调度器每次运行都会落一条），按调度时区自然日归档为「每天一份」，
    便于运营一眼看到某天系统抓取与运行是否正常、哪些任务出错、错误内容是什么。
    """
    tz = ZoneInfo(get_settings().scheduler_timezone)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(JobRun, Source.code)
        .outerjoin(Source, JobRun.source_id == Source.id)
        .where(JobRun.started_at >= since)
        .order_by(JobRun.started_at.desc())
    ).all()

    grouped: dict[str, list[dict]] = {}
    for job, source_code in rows:
        local = job.started_at.astimezone(tz)
        day = local.strftime("%Y-%m-%d")
        grouped.setdefault(day, []).append({
            "id": job.id,
            "job_type": job.job_type,
            "label": JOB_TYPE_LABELS.get(job.job_type, job.job_type),
            "source_code": source_code,
            "status": job.status,
            "error": job.error,
            "stats": job.stats,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            # 调度时区本地时钟，直接展示，避免前端再换算时区
            "clock": local.strftime("%H:%M:%S"),
        })

    days_out = []
    for day in sorted(grouped, reverse=True):
        runs = grouped[day]
        days_out.append({
            "date": day,
            "runs": runs,
            "summary": {
                "total": len(runs),
                "ok": sum(1 for r in runs if r["status"] == "ok"),
                "failed": sum(1 for r in runs if r["status"] == "failed"),
                "running": sum(1 for r in runs if r["status"] == "running"),
            },
        })
    return {"days": days_out, "total_days": len(days_out)}


@router.get("/audit", dependencies=[Depends(require_roles("admin", "processor"))])
def list_audit(
    actor: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    filters = []
    if actor:
        filters.append(AuditLog.actor == actor)
    if object_type:
        filters.append(AuditLog.object_type == object_type)
    if object_id:
        filters.append(AuditLog.object_id == object_id)
    stmt = select(AuditLog).where(*filters).order_by(AuditLog.at.desc())
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.execute(select(func.count(AuditLog.id)).where(*filters)).scalar_one()
    return {
        "items": [
            {
                "id": a.id, "actor": a.actor, "action": a.action,
                "object_type": a.object_type, "object_id": a.object_id,
                "before": a.before, "after": a.after, "reason": a.reason, "at": a.at,
            }
            for a in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/audit/export", dependencies=[Depends(require_roles("admin"))])
def export_audit(object_id: str | None = None, db: Session = Depends(get_db)):
    """CSV 导出（只追加日志，导出不改状态）。"""
    stmt = select(AuditLog).order_by(AuditLog.at.asc())
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    rows = db.scalars(stmt).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "at", "actor", "action", "object_type", "object_id", "before", "after", "reason"])
    for a in rows:
        writer.writerow([a.id, a.at.isoformat(), a.actor, a.action, a.object_type, a.object_id,
                         str(a.before), str(a.after), a.reason])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@router.get("/llm-calls", dependencies=[Depends(require_roles("admin"))])
def list_llm_calls(task: str | None = None, page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    """模型调用台账（token 与耗时成本核算）。"""
    stmt = select(LLMCallLog).order_by(LLMCallLog.at.desc())
    if task:
        stmt = stmt.where(LLMCallLog.task == task)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "items": [
            {
                "id": c.id, "provider": c.provider, "model": c.model, "task": c.task,
                "prompt_version": c.prompt_version, "tokens_in": c.tokens_in,
                "tokens_out": c.tokens_out, "latency_ms": c.latency_ms,
                "status": c.status, "error": c.error, "at": c.at,
            }
            for c in items
        ],
        "total": db.query(LLMCallLog).count(), "page": page, "page_size": page_size,
    }

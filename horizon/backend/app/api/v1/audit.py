"""审计查询与导出（04 §4.2 /admin/audit；10 §8 保留 ≥7 年）。"""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import AuditLog, LLMCallLog
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["audit"], dependencies=[Depends(require_api_key)])


@router.get("/audit")
def list_audit(
    actor: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.at.desc())
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total = db.query(AuditLog).count()
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


@router.get("/audit/export")
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


@router.get("/llm-calls")
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

"""预警列表（04 §4.2 /alerts）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import Alert
from app.db.session import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_alerts(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if status:
        stmt = stmt.where(Alert.status == status)
    return {
        "items": [
            {
                "id": a.id, "assessment_id": a.assessment_id, "title": a.title,
                "body_md": a.body_md, "channel_scope": a.channel_scope,
                "status": a.status, "created_at": a.created_at,
            }
            for a in db.scalars(stmt).all()
        ]
    }

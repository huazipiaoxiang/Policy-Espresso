"""存活 + 依赖检查（04 §4.2）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    provider = get_provider()
    return {
        "status": "ok" if db_ok else "degraded",
        "checks": {
            "db": "ok" if db_ok else "fail",
            "llm_provider": provider.name,
        },
        "version": "0.1.0",
    }

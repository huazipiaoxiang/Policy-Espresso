"""业务图谱 API（04 §4.2 /business-map）：业务线 × 主题 矩阵热力数据。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import Policy
from app.db.session import get_db
from app.domain.business_map import load_business_map

router = APIRouter(prefix="/business-map", tags=["business-map"], dependencies=[Depends(require_api_key)])


@router.get("")
def business_map(months: int = 12, db: Session = Depends(get_db)):
    """行=业务线，列=16 主题，格值={policy_count, avg_score}（近 N 个月）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    policies = db.scalars(select(Policy).where(Policy.published_at >= cutoff)).all()

    themes: list[str] = []
    for line in load_business_map():
        for t in line.themes_sensitivity:
            if t not in themes:
                themes.append(t)

    matrix: dict[str, dict[str, dict]] = {}
    for line in load_business_map():
        matrix[line.code] = {
            "name": line.name,
            "sensitivity": line.themes_sensitivity,
            "cells": {},
        }
        for theme in themes:
            # 命中条件：政策主题 ∈ 该业务线高敏感主题（敏感度≥3）
            if line.themes_sensitivity.get(theme, 0) >= 3:
                related = [p for p in policies if theme in (p.themes or [])]
                scores = [p.score_total for p in related if p.score_total]
                matrix[line.code]["cells"][theme] = {
                    "policy_count": len(related),
                    "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
                }

    # 高敏感主题月度趋势（Top5）
    theme_totals = {t: sum(matrix[code]["cells"].get(t, {}).get("policy_count", 0)
                           for code in matrix) for t in themes}
    top_themes = sorted(theme_totals, key=theme_totals.get, reverse=True)[:5]
    trends = {t: theme_totals[t] for t in top_themes}

    return {"themes": themes, "matrix": matrix, "top_themes": trends, "months": months}

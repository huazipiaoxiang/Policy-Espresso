"""业务图谱 API（04 §4.2 /business-map）：业务线 × 主题 矩阵热力数据。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_demo_role, require_api_key
from app.db.models import Document, Policy
from app.db.session import get_db
from app.domain.business_map import load_business_map

router = APIRouter(prefix="/business-map", tags=["business-map"], dependencies=[Depends(require_api_key)])


@router.get("")
def business_map(
    months: int = 12,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    jurisdiction: str | None = None,
    theme: str | None = None,
    scope: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
):
    """返回实时政策库生成的矩阵；下钻列表与计数使用同一去重数据集。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(months, 0) * 30)
    # 手动上传的政策可能没有发布日期，按原文收录时间计入，否则这条政策在矩阵里永远不出现。
    effective_date = func.coalesce(Policy.published_at, Document.fetched_at)
    stmt = (
        select(Policy, Document.fetched_at)
        .outerjoin(Document, Document.id == Policy.document_id)
        .where(effective_date >= cutoff)
    )
    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Policy.title.ilike(search_pattern),
            Policy.issuing_body.ilike(search_pattern),
            Policy.summary_zh.ilike(search_pattern),
        ))
    # 使用者只能看到已发布政策，显式传入其他 status 也不能绕过该限制。
    if role == "consumer":
        stmt = stmt.where(Policy.status == "published")
    elif status:
        stmt = stmt.where(Policy.status == status)
    if priority:
        stmt = stmt.where(Policy.priority == priority)
    if jurisdiction:
        stmt = stmt.where(Policy.jurisdiction == jurisdiction)
    if scope:
        stmt = stmt.where(Policy.target_entity_status == scope)
    rows = db.execute(stmt).all()
    policies = [row[0] for row in rows]
    ingested_at = {row[0].id: row[1] for row in rows}
    if theme:
        # JSON 字符串 contains 在 SQLite/PG 语义不同；按实际数组值筛选可移植。
        policies = [policy for policy in policies if theme in (policy.themes or [])]

    def sort_key(policy: Policy) -> tuple:
        return (policy.published_at or ingested_at.get(policy.id) or cutoff, policy.id)

    lines = load_business_map()

    themes: list[str] = []
    for line in lines:
        for theme in line.themes_sensitivity:
            if theme not in themes:
                themes.append(theme)

    matrix: dict[str, dict] = {}
    for line in lines:
        domain_policy_ids: set[str] = set()
        cells: dict[str, dict] = {}
        for theme in themes:
            # 命中条件：政策主题 ∈ 该业务线高敏感主题（敏感度≥3）。
            if line.themes_sensitivity.get(theme, 0) < 3:
                continue
            related_by_id = {p.id: p for p in policies if theme in (p.themes or [])}
            related = list(related_by_id.values())
            domain_policy_ids.update(related_by_id)
            scores = [p.score_total for p in related if p.score_total is not None]
            cells[theme] = {
                "policy_count": len(related_by_id),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
                "policies": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "summary_zh": p.summary_zh,
                        "themes": p.themes or [],
                        "score_total": p.score_total or 0.0,
                        "priority": p.priority,
                        "status": p.status,
                        "jurisdiction": p.jurisdiction,
                        "published_at": p.published_at,
                    }
                    for p in sorted(related, key=sort_key, reverse=True)
                ],
            }
        domain_policies = [p for p in policies if p.id in domain_policy_ids]
        matrix[line.code] = {
            "name": line.name,
            "sensitivity": line.themes_sensitivity,
            "policy_count": len(domain_policy_ids),
            "policies": [
                {
                    "id": p.id,
                    "title": p.title,
                    "summary_zh": p.summary_zh,
                    "themes": p.themes or [],
                    "score_total": p.score_total or 0.0,
                    "priority": p.priority,
                    "status": p.status,
                    "jurisdiction": p.jurisdiction,
                    "published_at": p.published_at,
                }
                for p in sorted(domain_policies, key=sort_key, reverse=True)
            ],
            "cells": cells,
        }

    # Top 主题按全业务线去重后的政策数统计，避免同一政策跨业务线重复计数。
    theme_policy_ids = {theme: set() for theme in themes}
    for line in lines:
        for theme in themes:
            if line.themes_sensitivity.get(theme, 0) >= 3:
                theme_policy_ids[theme].update(
                    p.id for p in policies if theme in (p.themes or [])
                )
    top_themes = {
        theme: len(theme_policy_ids[theme])
        for theme in sorted(themes, key=lambda theme: (-len(theme_policy_ids[theme]), themes.index(theme)))[:5]
    }

    return {"themes": themes, "matrix": matrix, "top_themes": top_themes, "months": months}

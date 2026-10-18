"""案例库 API（04 §4.2 /cases，支持语义检索 ?q=）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.security import require_api_key
from app.db.models import Case
from app.db.session import get_db
from app.domain.business_map import load_business_map

router = APIRouter(prefix="/cases", tags=["cases"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_cases(
    q: str | None = None,
    theme: str | None = None,
    business_line: str | None = None,
    db: Session = Depends(get_db),
):
    """混合检索：业务线 → 映射主题 → 主题过滤 + 关键词相似度排序。

    Phase 4 起为规则+相似度混合；向量检索（pgvector）在 Phase 5 接入后替换排序实现。
    """
    from app.ingest.dedupe import title_similarity

    cases = db.scalars(select(Case)).all()
    theme_filter = theme
    if business_line and not theme_filter:
        line = next((l for l in load_business_map() if l.code == business_line), None)
        if line:
            theme_filter = None  # 业务线不直接映射单一主题，改为加权

    scored: list[tuple[float, Case]] = []
    for case in cases:
        if theme and theme not in (case.themes or []):
            continue
        score = title_similarity(q or "", case.title + case.policy_summary) if q else 1.0
        if business_line:
            line = next((l for l in load_business_map() if l.code == business_line), None)
            if line:
                overlap = len(set(case.themes or []) & set(line.themes_sensitivity))
                score = max(score, overlap / max(len(line.themes_sensitivity), 1))
        scored.append((score, case))
    scored.sort(key=lambda item: item[0], reverse=True)
    return {
        "items": [
            {
                "id": c.id, "title": c.title, "year": c.year, "jurisdiction": c.jurisdiction,
                "themes": c.themes or [], "outcome": c.outcome,
                "impact": c.impact, "similarity": round(s, 3),
            }
            for s, c in scored
        ]
    }


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case:
        raise not_found("案例", case_id)
    return {
        "id": case.id, "title": case.title, "year": case.year, "jurisdiction": case.jurisdiction,
        "themes": case.themes or [], "policy_summary": case.policy_summary, "impact": case.impact,
        "hsbc_response": case.hsbc_response, "outcome": case.outcome, "lessons": case.lessons or [],
        "source_refs": case.source_refs or [],
    }

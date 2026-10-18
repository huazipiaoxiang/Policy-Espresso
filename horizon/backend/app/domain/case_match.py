"""案例匹配（Phase 2 轻量版）：主题重叠 + 标题相似度 + 关键词加权。

Phase 4 将替换为 向量 + BM25 混合检索；此处接口保持一致（返回 TopN + similarity）。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case
from app.ingest.dedupe import title_similarity


@dataclass
class CaseHit:
    case_id: str
    title: str
    similarity: float
    themes: list[str]
    lessons: list[str]


def match_cases(db: Session, *, themes: list[str], text: str, top_n: int = 5, min_similarity: float = 0.6) -> list[CaseHit]:
    """相似度 = 0.6×主题Jaccard + 0.4×标题相似度 + 主题关键词在正文的命中加成。"""
    cases = db.scalars(select(Case)).all()
    scored: list[tuple[float, Case]] = []
    theme_set = set(themes)
    for case in cases:
        case_themes = set(case.themes or [])
        theme_sim = len(theme_set & case_themes) / len(theme_set | case_themes) if theme_set else 0.0
        title_sim = title_similarity(text[:200], case.title + case.policy_summary[:200])
        keyword_bonus = 0.1 if (theme_set & case_themes) else 0.0
        similarity = round(0.6 * theme_sim + 0.4 * title_sim + keyword_bonus, 3)
        scored.append((min(similarity, 1.0), case))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        CaseHit(case_id=c.id, title=c.title, similarity=s, themes=c.themes or [], lessons=c.lessons or [])
        for s, c in scored[:top_n] if s >= min_similarity
    ]

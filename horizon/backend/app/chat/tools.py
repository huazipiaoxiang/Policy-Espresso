"""Fixed SQLAlchemy queries exposed to the chat service.

This module deliberately accepts search text, never SQL. Every query has a small
result limit and all role filtering happens here, before evidence is returned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Assessment, Document, Policy, ReviewTask, Source

RESULT_LIMIT = 6
TEXT_LIMIT = 1200
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,63}|\b(?:p|d|s|a|rt)_[A-Za-z0-9_-]+\b", re.I)
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_QUOTED_RE = re.compile(r"[《》\"'“”‘’]([^《》\"'“”‘’]{2,120})[《》\"'“”‘’]")
_GENERIC_BIGRAMS = {
    "政策", "影响", "业务", "文件", "文档", "来源", "总结", "分析", "请问",
    "什么", "哪些", "如何", "最新", "最近", "相关", "内容", "介绍", "帮助",
    "一下", "我们", "当前", "数据", "资料", "回答", "问题", "机构", "监管",
    "关于", "有些", "一些", "有关", "哪些", "能否", "帮我", "查找", "查询",
    "请问", "信息", "情况", "动态", "通知", "公告", "规定", "办法", "意见",
}


@dataclass(frozen=True)
class ChatEvidence:
    """Server-owned evidence and its public citation metadata."""

    key: str
    kind: str
    title: str
    text: str
    citation: dict[str, Any]
    score: int = 0


def normalize_role(role: object) -> str:
    value = getattr(role, "value", role)
    return str(value or "consumer").strip().lower()


def _clean_text(value: object, limit: int = TEXT_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _format_date(value: datetime | None) -> str:
    return value.date().isoformat() if value else "日期未知"


def search_terms(query: str) -> list[str]:
    """Extract bounded lexical terms; these are values in ORM ``ilike`` filters."""

    candidates: list[str] = []
    quoted = [match.strip() for match in _QUOTED_RE.findall(query)]
    if quoted:
        candidates.extend(quoted)
    else:
        candidates.extend(match.group(0) for match in _WORD_RE.finditer(query))
        for sequence in _CJK_RE.findall(query):
            if 2 <= len(sequence) <= 24:
                candidates.append(sequence)
            # Chinese questions often have no spaces. Bigrams allow a title term in
            # a natural-language question to match without passing raw SQL anywhere.
            candidates.extend(sequence[index : index + 2] for index in range(max(0, len(sequence) - 1)))

    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        term = candidate.strip()[:120]
        folded = term.casefold()
        if len(term) < 2 or folded in seen or (len(term) == 2 and term in _GENERIC_BIGRAMS):
            continue
        seen.add(folded)
        terms.append(term)
        if len(terms) == 10:
            break
    return terms


def _pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filters(columns: list[Any], terms: list[str]) -> list[Any]:
    return [column.ilike(_pattern(term), escape="\\") for column in columns for term in terms]


def _score_of(query: str, row: Any, title: Any, body: Any, extra: Any = None) -> int:
    terms = search_terms(query)
    row_title = str(title(row) or "").casefold()
    row_body = str(body(row) or "").casefold()
    folded_query = query.strip().casefold()
    quoted = [match.strip().casefold() for match in _QUOTED_RE.findall(query)]
    exact = 1000 if (
        any(phrase in row_title for phrase in quoted)
        or (folded_query and folded_query in row_title)
    ) else 0
    matched = sum(8 for term in terms if term.casefold() in row_title)
    matched += sum(1 for term in terms if term.casefold() in row_body)
    if extra is not None:
        matched += int(extra(row) or 0)
    return exact + matched


def _rank(query: str, rows: list[Any], title: Any, body: Any, extra: Any = None) -> list[Any]:
    def key(row: Any) -> tuple[int, int]:
        return _score_of(query, row, title, body, extra), -len(str(title(row) or ""))

    return sorted(rows, key=key, reverse=True)


_REVIEW_INTENT_WORDS = ("审核", "审查", "复核", "审批", "待办", "待审", "review", "assignee")


def _has_review_intent(query: str) -> bool:
    folded = query.casefold()
    return any(word in folded for word in _REVIEW_INTENT_WORDS)


def _excerpt(text: str, query: str) -> str:
    clean = _clean_text(text, 20000)
    if not clean:
        return ""
    lowered = clean.casefold()
    positions = [lowered.find(term.casefold()) for term in search_terms(query)]
    positions = [position for position in positions if position >= 0]
    start = max(0, min(positions) - 120) if positions else 0
    end = min(len(clean), start + TEXT_LIMIT)
    prefix = "…" if start else ""
    suffix = "…" if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


def _theme_terms(db: Session, query: str) -> tuple[list[str], list[str]]:
    """政策主题常不出现在标题里（如「人民币国际化」）；问题中出现主题词时按主题数组匹配。

    JSON 列存的是转义文本（CJK 存成 \\uXXXX），SQL 层 ilike 匹配不到中文，
    所以主题匹配在 Python 侧完成，再以 id 列表回推 SQL。
    """
    rows = db.execute(select(Policy.id, Policy.themes).where(Policy.themes.isnot(None))).all()
    known: set[str] = set()
    ids_by_theme: dict[str, list[str]] = {}
    for policy_id, themes in rows:
        for value in themes or []:
            if isinstance(value, str) and 2 <= len(value) <= 24:
                known.add(value)
                ids_by_theme.setdefault(value, []).append(policy_id)
    terms = sorted((theme for theme in known if theme in query), key=len, reverse=True)[:5]
    matched_ids = sorted({policy_id for theme in terms for policy_id in ids_by_theme.get(theme, [])})
    return terms, matched_ids


class ChatTools:
    """A fixed allow-list of read-only retrieval operations."""

    def __init__(self, db: Session, role: object):
        self.db = db
        self.role = normalize_role(role)

    @property
    def is_consumer(self) -> bool:
        # Defense in depth: dependency validation is primary, unknown roles fail closed.
        return self.role not in {"admin", "analyst", "approver", "publisher"}

    def search_policies(self, query: str) -> list[ChatEvidence]:
        stmt = select(Policy).options(joinedload(Policy.document).joinedload(Document.source))
        if self.is_consumer:
            stmt = stmt.where(Policy.status == "published")
        terms = search_terms(query)
        theme_terms, theme_matched_ids = _theme_terms(self.db, query)
        filters = _filters([Policy.title, Policy.summary_zh, Policy.issuing_body, Policy.doc_number], terms)
        if theme_matched_ids:
            filters.append(Policy.id.in_(theme_matched_ids))
        if filters:
            stmt = stmt.where(or_(*filters))
        rows = list(self.db.scalars(stmt.order_by(Policy.published_at.desc().nullslast()).limit(40)).unique())
        if theme_terms:
            # 问题里的主题词是强信号：优先只保留主题命中的政策，避免「人民/国际」等泛词命中挤占结果。
            themed = [row for row in rows if any(term in (row.themes or []) for term in theme_terms)]
            if themed:
                rows = themed
        title_of = lambda row: row.title
        body_of = lambda row: row.summary_zh
        theme_bonus = lambda row: sum(24 for term in theme_terms if term in (row.themes or []))
        rows = _rank(query, rows, title_of, body_of, theme_bonus)[:RESULT_LIMIT]

        evidence: list[ChatEvidence] = []
        for policy in rows:
            document = policy.document
            summary = _clean_text(policy.summary_zh)
            if not summary and document:
                summary = _excerpt(document.content_text, query)
            details = [f"发布机构：{policy.issuing_body}" if policy.issuing_body else ""]
            if policy.doc_number:
                details.append(f"文号：{policy.doc_number}")
            details.append(f"发布日期：{_format_date(policy.published_at)}")
            if not self.is_consumer:
                details.append(f"状态：{policy.status}")
            text = "；".join(part for part in details if part)
            if summary:
                text = f"{text}\n摘要：{summary}"
            evidence.append(ChatEvidence(
                key=f"policy:{policy.id}",
                kind="policy",
                title=policy.title,
                text=text or "当前记录没有可用摘要。",
                score=_score_of(query, policy, title_of, body_of, theme_bonus),
                citation={
                    "id": f"policy:{policy.id}",
                    "type": "policy",
                    "title": policy.title,
                    "url": document.url if document else "",
                    "policy_id": policy.id,
                    "document_id": document.id if document else None,
                    "source_id": document.source_id if document else None,
                },
            ))
        return evidence

    def search_documents(self, query: str) -> list[ChatEvidence]:
        stmt = select(Document).join(Source, Document.source_id == Source.id).options(joinedload(Document.source))
        if self.is_consumer:
            stmt = stmt.join(Policy, Policy.document_id == Document.id).where(Policy.status == "published")
        terms = search_terms(query)
        if terms:
            stmt = stmt.where(or_(*_filters([Document.title, Document.content_text, Source.name], terms)))
        rows = list(self.db.scalars(stmt.order_by(Document.published_at.desc().nullslast()).limit(40)).unique())
        title_of = lambda row: row.title
        body_of = lambda row: row.content_text
        rows = _rank(query, rows, title_of, body_of)[:RESULT_LIMIT]
        return [ChatEvidence(
            key=f"document:{document.id}",
            kind="document",
            title=document.title,
            text=f"发布日期：{_format_date(document.published_at)}\n原文摘录：{_excerpt(document.content_text, query) or '当前记录没有可用正文。'}",
            score=_score_of(query, document, title_of, body_of),
            citation={
                "id": f"document:{document.id}",
                "type": "document",
                "title": document.title,
                "url": document.url,
                "policy_id": None,
                "document_id": document.id,
                "source_id": document.source_id,
            },
        ) for document in rows]

    def search_sources(self, query: str) -> list[ChatEvidence]:
        """Return public source summaries only; never source config or health."""

        stmt = select(Source)
        terms = search_terms(query)
        if terms:
            stmt = stmt.where(or_(*_filters([Source.name, Source.org, Source.jurisdiction], terms)))
        rows = list(self.db.scalars(stmt.order_by(Source.tier, Source.name).limit(40)))
        name_of = lambda row: row.name
        org_of = lambda row: row.org
        rows = _rank(query, rows, name_of, org_of)[:RESULT_LIMIT]
        return [ChatEvidence(
            key=f"source:{source.id}",
            kind="source",
            title=source.name,
            text=(
                f"公开来源：{source.name}；机构：{source.org or '未注明'}；"
                f"地区：{source.jurisdiction}；来源级别：{source.tier}。"
            ),
            score=_score_of(query, source, name_of, org_of),
            citation={
                "id": f"source:{source.id}",
                "type": "web_source",
                "title": source.name,
                "url": source.url,
                "policy_id": None,
                "document_id": None,
                "source_id": source.id,
            },
        ) for source in rows]

    def search_reviews(self, query: str) -> list[ChatEvidence]:
        if self.is_consumer:
            return []
        stmt = (
            select(ReviewTask, Policy, Document)
            .join(Policy, ReviewTask.policy_id == Policy.id)
            .join(Document, Policy.document_id == Document.id)
        )
        if self.role == "analyst":
            stmt = stmt.where(ReviewTask.level == 1)
        elif self.role == "approver":
            stmt = stmt.where(ReviewTask.level == 2)
        terms = search_terms(query)
        if terms:
            stmt = stmt.where(or_(*_filters(
                [Policy.title, ReviewTask.status, ReviewTask.assignee], terms,
            )))
        rows = list(self.db.execute(stmt.order_by(ReviewTask.created_at.desc()).limit(40)).all())
        fallback = False
        if not rows and _has_review_intent(query):
            # 「我的待办」这类问题往往匹配不到标题/负责人，直接列出可处理的待办任务。
            fallback_stmt = (
                select(ReviewTask, Policy, Document)
                .join(Policy, ReviewTask.policy_id == Policy.id)
                .join(Document, Policy.document_id == Document.id)
                .where(ReviewTask.status.in_(["pending", "claimed"]))
            )
            if self.role == "analyst":
                fallback_stmt = fallback_stmt.where(ReviewTask.level == 1)
            elif self.role == "approver":
                fallback_stmt = fallback_stmt.where(ReviewTask.level == 2)
            rows = list(self.db.execute(
                fallback_stmt.order_by(ReviewTask.created_at.desc()).limit(RESULT_LIMIT)
            ).all())
            fallback = True
        title_of = lambda row: row[1].title
        body_of = lambda row: f"{row[0].status} {row[0].assignee}"
        rows = _rank(query, rows, title_of, body_of)[:RESULT_LIMIT]
        evidence: list[ChatEvidence] = []
        for task, policy, document in rows:
            evidence.append(ChatEvidence(
                key=f"review:{task.id}",
                kind="review",
                title=f"审核任务：{policy.title}",
                text=(
                    f"政策：{policy.title}；任务级别：{task.level}；状态：{task.status}；"
                    f"负责人：{task.assignee or '未分配'}；创建日期：{_format_date(task.created_at)}。"
                ),
                score=16 if fallback else _score_of(query, (task, policy, document), title_of, body_of),
                citation={
                    "id": f"review:{task.id}",
                    "type": "policy",
                    "title": policy.title,
                    "url": document.url,
                    "policy_id": policy.id,
                    "document_id": document.id,
                    "source_id": document.source_id,
                },
            ))
        return evidence

    def search_business_impacts(self, query: str) -> list[ChatEvidence]:
        if self.is_consumer:
            return []
        stmt = (
            select(Assessment)
            .join(Policy, Assessment.policy_id == Policy.id)
            .options(joinedload(Assessment.policy).joinedload(Policy.document))
        )
        terms = search_terms(query)
        if terms:
            stmt = stmt.where(or_(*_filters([Policy.title, Policy.summary_zh], terms)))
        rows = list(self.db.scalars(stmt.order_by(Assessment.created_at.desc()).limit(40)).unique())
        title_of = lambda row: row.policy.title
        body_of = lambda row: row.policy.summary_zh
        rows = _rank(query, rows, title_of, body_of)[:RESULT_LIMIT]
        evidence: list[ChatEvidence] = []
        for assessment in rows:
            policy = assessment.policy
            document = policy.document
            impact = _clean_text({
                "direction": assessment.direction,
                "priority": assessment.priority,
                "score_total": assessment.score_total,
                "affected": assessment.affected,
                "transmission_chain": assessment.transmission_chain,
                "recommended_actions": assessment.recommended_actions,
                "confidence": assessment.confidence,
            })
            evidence.append(ChatEvidence(
                key=f"impact:{assessment.id}",
                kind="business_impact",
                title=f"业务影响：{policy.title}",
                text=f"政策：{policy.title}\n影响评估：{impact}",
                score=_score_of(query, assessment, title_of, body_of),
                citation={
                    "id": f"impact:{assessment.id}",
                    "type": "policy",
                    "title": policy.title,
                    "url": document.url if document else "",
                    "policy_id": policy.id,
                    "document_id": document.id if document else None,
                    "source_id": document.source_id if document else None,
                },
            ))
        return evidence

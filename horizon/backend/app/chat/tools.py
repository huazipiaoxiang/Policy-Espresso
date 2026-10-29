"""Fixed SQLAlchemy queries exposed to the chat service.

This module deliberately accepts search text, never SQL. Every query has a small
result limit and all role filtering happens here, before evidence is returned.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Assessment, Document, Policy, ReviewTask, Source

RESULT_LIMIT = 8
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

_INTERPRET_WORDS = ("解读", "分析", "总结", "要点", "重点", "介绍", "内容", "是什么")
INTERPRET_EXCERPT_LIMIT = 3000


def _has_interpret_intent(query: str) -> bool:
    return any(word in query for word in _INTERPRET_WORDS)


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
_IMPACT_INTENT_WORDS = ("影响", "业务", "风险", "传导", "应对", "行动", "impact", "business")


def _has_review_intent(query: str) -> bool:
    folded = query.casefold()
    return any(word in folded for word in _REVIEW_INTENT_WORDS)


def _has_impact_intent(query: str) -> bool:
    folded = query.casefold()
    return any(word in folded for word in _IMPACT_INTENT_WORDS)


def _excerpt(text: str, query: str, limit: int = TEXT_LIMIT) -> str:
    clean = _clean_text(text, 20000)
    if not clean:
        return ""
    lowered = clean.casefold()
    positions = [lowered.find(term.casefold()) for term in search_terms(query)]
    positions = [position for position in positions if position >= 0]
    start = max(0, min(positions) - 120) if positions else 0
    end = min(len(clean), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


# Agent 模式下同一问题会在多轮里被反复检索，这两处全表扫描会被线性放大，
# 因此做进程内缓存：主题词表按「政策数 + 最大 id」指纹缓存，正文低频词按查询串缓存。
# 两者都带 TTL，避免长期持有陈旧数据；测试可用 clear_query_caches() 强制失效。
_CACHE_TTL_SECONDS = 60.0
_THEME_CACHE: tuple[str, float, dict[str, list[str]]] | None = None
_CONTENT_TERM_CACHE: dict[str, tuple[float, list[str]]] = {}
_CONTENT_TERM_CACHE_MAX = 256


def clear_query_caches() -> None:
    """清空检索缓存（测试与重建索引后使用）。"""
    global _THEME_CACHE
    _THEME_CACHE = None
    _CONTENT_TERM_CACHE.clear()


def _theme_vocabulary(db: Session) -> dict[str, list[str]]:
    """主题词 → 政策 id 列表。按 (count, max_id) 指纹 + TTL 缓存，避免每轮全表扫描。"""
    global _THEME_CACHE
    now = time.monotonic()
    fingerprint_row = db.execute(select(func.count(Policy.id), func.max(Policy.id))).first()
    fingerprint = f"{fingerprint_row[0]}:{fingerprint_row[1]}" if fingerprint_row else ""
    if _THEME_CACHE and _THEME_CACHE[0] == fingerprint and now - _THEME_CACHE[1] < _CACHE_TTL_SECONDS:
        return _THEME_CACHE[2]

    rows = db.execute(select(Policy.id, Policy.themes).where(Policy.themes.isnot(None))).all()
    ids_by_theme: dict[str, list[str]] = {}
    for policy_id, themes in rows:
        for value in themes or []:
            if isinstance(value, str) and 2 <= len(value) <= 24:
                ids_by_theme.setdefault(value, []).append(policy_id)
    _THEME_CACHE = (fingerprint, now, ids_by_theme)
    return ids_by_theme


def _theme_terms(db: Session, query: str) -> tuple[list[str], list[str]]:
    """政策主题常不出现在标题里（如「人民币国际化」）；问题中出现主题词时按主题数组匹配。

    JSON 列存的是转义文本（CJK 存成 \\uXXXX），SQL 层 ilike 匹配不到中文，
    所以主题匹配在 Python 侧完成，再以 id 列表回推 SQL。
    """
    ids_by_theme = _theme_vocabulary(db)
    terms = sorted((theme for theme in ids_by_theme if theme in query), key=len, reverse=True)[:5]
    matched_ids = sorted({policy_id for theme in terms for policy_id in ids_by_theme.get(theme, [])})
    return terms, matched_ids


# 正文匹配词的文档频率窗口（当前约 1.4k 文档的语料下取值）。
# 上限排除导航菜单等垃圾高频词（金融 769 / 銀行 666 / 香港 843 / 的政 64）；
# 下限排除只出现在单篇文档的跨词噪声二元组（如「和贴」）。
_MAX_CONTENT_DF = 50
_MIN_CONTENT_DF = 2


def _content_terms(db: Session, query: str) -> list[str]:
    """提取用于原文正文匹配的低频词：词条 + CJK 二元组，排除语料高频与通用词。

    每个候选词都要一次全表 COUNT，是检索路径上最贵的一步，结果按查询串缓存 60 秒。
    """
    cached = _CONTENT_TERM_CACHE.get(query)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    candidates: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(query):
        term = match.group(0)
        if term.casefold() not in seen:
            seen.add(term.casefold())
            candidates.append(term)
    for sequence in _CJK_RE.findall(query):
        for index in range(max(0, len(sequence) - 1)):
            term = sequence[index : index + 2]
            if term in _GENERIC_BIGRAMS or term in seen:
                continue
            seen.add(term)
            candidates.append(term)
    if not candidates:
        return []
    kept: list[str] = []
    for term in candidates:
        freq = db.scalar(
            select(func.count(Document.id)).where(
                Document.content_text.ilike(_pattern(term), escape="\\")
            )
        ) or 0
        if _MIN_CONTENT_DF <= freq <= _MAX_CONTENT_DF:
            kept.append(term)
    if len(_CONTENT_TERM_CACHE) >= _CONTENT_TERM_CACHE_MAX:
        _CONTENT_TERM_CACHE.clear()
    _CONTENT_TERM_CACHE[query] = (time.monotonic(), kept)
    return kept


def _content_hits(content: str, content_terms: list[str]) -> int:
    """正文命中数 → 分数：2 个低频词及以上视为强信号（与主题命中同权重）。"""
    if not content:
        return 0
    hits = sum(1 for term in content_terms if term in content)
    return 24 if hits >= 2 else 8 * hits


_DIRECTION_LABELS = {
    "positive": "利好（积极影响）",
    "negative": "利空（不利影响）",
    "mixed": "有正面也有负面影响",
    "neutral": "中性（暂无明确利好或利空）",
}
_PRIORITY_LABELS = {
    "P0": "P0（最高优先）",
    "P1": "P1（高优先）",
    "P2": "P2（中等优先）",
    "P3": "P3（低优先）",
}


def _format_business_impact(assessment: Assessment) -> str:
    """把影响评估的结构化字段翻译成业务用户能看懂的中文。"""
    lines: list[str] = []
    direction = str(assessment.direction or "neutral")
    lines.append(f"影响方向：{_DIRECTION_LABELS.get(direction, direction)}")
    priority = str(assessment.priority or "P3")
    lines.append(f"优先级：{_PRIORITY_LABELS.get(priority, priority)}")
    lines.append(f"综合影响分：{assessment.score_total} 分（满分 100，越高越需要关注）")

    affected = assessment.affected or {}
    business_lines = affected.get("business_lines") or []
    segments = affected.get("segments") or []
    exposure = affected.get("exposure_range")
    if business_lines:
        lines.append(f"受影响业务线：{'、'.join(str(line) for line in business_lines)}")
    if segments:
        lines.append(f"受影响客群：{'、'.join(str(segment) for segment in segments)}")
    if isinstance(exposure, dict) and exposure:
        low, high = exposure.get("low"), exposure.get("high")
        if low is not None or high is not None:
            currency = exposure.get("currency") or ""
            unit = exposure.get("unit") or ""
            lines.append(f"敞口范围：{low}–{high} {currency}{unit}".strip())
    if not business_lines and not segments and not (isinstance(exposure, dict) and exposure):
        lines.append("影响对象：暂未识别到具体业务线或客群")

    chain = assessment.transmission_chain or []
    if chain:
        lines.append(f"传导链条：{' → '.join(str(step) for step in chain)}")
    else:
        lines.append("传导链条：无")

    actions = assessment.recommended_actions or []
    if actions:
        parts: list[str] = []
        for item in actions:
            if isinstance(item, dict):
                action = str(item.get("action") or "")
                owner = str(item.get("owner") or "")
                deadline = str(item.get("deadline") or "")
                text = action
                if owner:
                    text += f"（负责人：{owner}）"
                if deadline:
                    text += f"（截止：{deadline}）"
                parts.append(text)
            else:
                parts.append(str(item))
        lines.append("建议动作：" + "；".join(parts))
    else:
        lines.append("建议动作：暂无需跟进")

    confidence = assessment.confidence
    if confidence is not None:
        lines.append(f"置信度：{round(float(confidence) * 100)}%")
    return "\n".join(lines)


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
        # 引号内的完整标题是精确查找信号，不再叠加正文匹配，
        # 避免「香港金融管理局」这类每篇都有的语料词把无关通告挤进候选。
        content_terms = [] if _QUOTED_RE.search(query) else _content_terms(self.db, query)
        stmt = stmt.outerjoin(Document, Policy.document_id == Document.id)
        filters = _filters([Policy.title, Policy.summary_zh, Policy.issuing_body, Policy.doc_number], terms)
        if content_terms:
            filters.extend(_filters([Document.content_text], content_terms))
        if theme_matched_ids:
            filters.append(Policy.id.in_(theme_matched_ids))
        if filters:
            stmt = stmt.where(or_(*filters))
        rows = list(self.db.scalars(stmt.order_by(
            Policy.published_at.desc().nullslast(), Policy.id,
        ).limit(40)).unique())
        if theme_terms:
            # 问题里的主题词是强信号：优先只保留主题命中的政策，避免「人民/国际」等泛词命中挤占结果。
            themed = [row for row in rows if any(term in (row.themes or []) for term in theme_terms)]
            if themed:
                rows = themed
        title_of = lambda row: row.title
        body_of = lambda row: row.summary_zh
        theme_bonus = lambda row: sum(24 for term in theme_terms if term in (row.themes or []))
        combined_bonus = lambda row: theme_bonus(row) + _content_hits(
            (row.document.content_text or "") if row.document else "", content_terms,
        )
        rows = _rank(query, rows, title_of, body_of, combined_bonus)[:RESULT_LIMIT]
        return self._policy_evidence(rows, query, title_of=title_of, body_of=body_of, extra=combined_bonus)

    def _policy_evidence(
        self,
        rows: list[Policy],
        query: str,
        *,
        title_of: Callable[[Policy], str],
        body_of: Callable[[Policy], str],
        extra: Callable[[Policy], int],
        include_fetched: bool = False,
    ) -> list[ChatEvidence]:
        """把 Policy 列表组装成 ChatEvidence；query 为空串时 score=0、不补原文。"""
        interpret = _has_interpret_intent(query)
        evidence: list[ChatEvidence] = []
        for policy in rows:
            document = policy.document
            summary = _clean_text(policy.summary_zh)
            content_excerpt = ""
            if document:
                excerpt = _excerpt(
                    document.content_text, query,
                    limit=INTERPRET_EXCERPT_LIMIT if interpret else TEXT_LIMIT,
                )
                if excerpt:
                    if summary:
                        content_excerpt = excerpt
                    else:
                        summary = excerpt
            details = [f"发布机构：{policy.issuing_body}" if policy.issuing_body else ""]
            if policy.doc_number:
                details.append(f"文号：{policy.doc_number}")
            details.append(f"发布日期：{_format_date(policy.published_at)}")
            if include_fetched and document:
                details.append(f"入库时间：{_format_date(document.fetched_at)}")
            if not self.is_consumer:
                details.append(f"状态：{policy.status}")
            text = "；".join(part for part in details if part)
            if summary:
                text = f"{text}\n摘要：{summary}"
            # 摘要过短或要求解读时补原文摘录，给 LLM 提供可解读的实质内容
            if content_excerpt and (interpret or len(summary) < 100):
                text = f"{text}\n原文摘录：{content_excerpt}"
            evidence.append(ChatEvidence(
                key=f"policy:{policy.id}",
                kind="policy",
                title=policy.title,
                text=text or "当前记录没有可用摘要。",
                score=_score_of(query, policy, title_of, body_of, extra),
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

    def search_recent_policies(self, *, since: datetime | None = None, limit: int = RESULT_LIMIT) -> list[ChatEvidence]:
        """按入库时间（document.fetched_at）降序返回最新入库的政策。

        用于「今天/最近新增」类问题：政策发布日期（published_at）可能远早于入库时间，
        只有 fetched_at 能表达「新增」语义。
        """
        stmt = select(Policy).options(joinedload(Policy.document).joinedload(Document.source))
        if self.is_consumer:
            stmt = stmt.where(Policy.status == "published")
        stmt = stmt.outerjoin(Document, Policy.document_id == Document.id)
        if since is not None:
            stmt = stmt.where(Document.fetched_at >= since)
        rows = list(self.db.scalars(
            stmt.order_by(Document.fetched_at.desc(), Policy.id).limit(limit)
        ).unique())
        return self._policy_evidence(
            rows, "",
            title_of=lambda row: row.title,
            body_of=lambda row: row.summary_zh,
            extra=lambda row: 0,
            include_fetched=True,
        )

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
        if not rows and _has_impact_intent(query):
            # 影响类问题常按「业务线/风险」等内部术语提问，这些词不出现在政策标题里，
            # 按标题过滤会把结果滤空；此时直接列出最新评估，与 search_reviews 的兜底一致。
            fallback_stmt = (
                select(Assessment)
                .join(Policy, Assessment.policy_id == Policy.id)
                .options(joinedload(Assessment.policy).joinedload(Policy.document))
            )
            rows = list(self.db.scalars(
                fallback_stmt.order_by(Assessment.created_at.desc()).limit(RESULT_LIMIT)
            ).unique())
        title_of = lambda row: row.policy.title
        body_of = lambda row: row.policy.summary_zh
        rows = _rank(query, rows, title_of, body_of)[:RESULT_LIMIT]
        evidence: list[ChatEvidence] = []
        for assessment in rows:
            policy = assessment.policy
            document = policy.document
            evidence.append(ChatEvidence(
                key=f"impact:{assessment.id}",
                kind="business_impact",
                title=f"业务影响：{policy.title}",
                text=f"政策：{policy.title}\n{_format_business_impact(assessment)}",
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

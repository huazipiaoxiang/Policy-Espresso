"""语义检索与 RRF 融合：向量召回 + 既有词法打分，输出与 ChatTools 同构的证据。

融合在「文档级」进行——向量命中的切片统一折叠为 document:{id}，
与词法侧的 document 证据按 RRF(k=60) 合并去重，避免同一文档重复占用证据预算。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.tools import ChatEvidence, ChatTools, normalize_role
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, Policy
from app.search import embedder, index as vector_index

log = get_logger("search.retriever")

_PRIVILEGED_ROLES = {"admin", "analyst", "approver", "publisher"}


def is_consumer(role: object) -> bool:
    return normalize_role(role) not in _PRIVILEGED_ROLES


def vector_available(db: Session) -> bool:
    """向量通道是否可用：总开关 + numpy + 嵌入可达 + 索引非空。"""
    if not get_settings().search_vector_enabled:
        return False
    if not vector_index.numpy_available() or not embedder.embed_available():
        return False
    return vector_index.get_index(db) is not None


def _chunk_texts(db: Session, chunk_ids: list[str]) -> dict[str, str]:
    if not chunk_ids:
        return {}
    rows = db.execute(
        select(DocumentChunk.id, DocumentChunk.text).where(DocumentChunk.id.in_(chunk_ids))
    ).all()
    return {chunk_id: text or "" for chunk_id, text in rows}


def _visible_document_ids(db: Session, document_ids: list[str], role: object) -> set[str]:
    if not is_consumer(role):
        return set(document_ids)
    rows = db.execute(
        select(Policy.document_id).where(
            Policy.document_id.in_(document_ids), Policy.status == "published",
        )
    ).all()
    return {document_id for (document_id,) in rows}


def search_vector(db: Session, query: str, *, role: object, limit: int = 8) -> list[ChatEvidence]:
    """纯向量召回。任一步不可用返回空列表（调用方降级，不抛异常）。"""
    settings = get_settings()
    if not settings.search_vector_enabled or not vector_index.numpy_available():
        return []
    try:
        result = embedder.embed_texts([query])
        vector = result.vectors[0] if result.vectors else []
    except embedder.EmbedError as exc:
        log.warning("search_embed_failed", error=str(exc))
        return []
    if not vector:
        return []
    idx = vector_index.get_index(db)
    if idx is None:
        return []
    hits = idx.search(vector, max(int(limit) * 3, int(limit)))
    if not hits:
        return []

    visible = _visible_document_ids(db, [hit.document_id for hit in hits], role)
    kept = [hit for hit in hits if hit.document_id in visible]
    if not kept:
        return []

    texts = _chunk_texts(db, [hit.chunk_id for hit in kept][: len(kept)])
    documents = {
        document.id: document
        for document in db.scalars(select(Document).where(
            Document.id.in_({hit.document_id for hit in kept})
        ))
    }

    evidence: list[ChatEvidence] = []
    seen: set[str] = set()
    for hit in kept:
        if hit.document_id in seen or len(evidence) >= limit:
            continue
        document = documents.get(hit.document_id)
        if document is None:
            continue
        seen.add(hit.document_id)
        snippet = " ".join((texts.get(hit.chunk_id) or "").split())[:800]
        published = document.published_at.date().isoformat() if document.published_at else "日期未知"
        evidence.append(ChatEvidence(
            key=f"document:{document.id}",
            kind="document",
            title=document.title,
            text=f"发布日期：{published}\n语义匹配片段：{snippet}" if snippet
                 else f"发布日期：{published}\n（切片正文缺失）",
            score=int(round(max(0.0, min(1.0, hit.score)) * 100)),
            citation={
                "id": f"document:{document.id}",
                "type": "document",
                "title": document.title,
                "url": document.url,
                "policy_id": hit.policy_id,
                "document_id": document.id,
                "source_id": document.source_id,
            },
        ))
    return evidence


def fuse(
    lexical: list[ChatEvidence],
    vector: list[ChatEvidence],
    *,
    k: int = 60,
    limit: int = 8,
) -> list[ChatEvidence]:
    """RRF 融合：score = Σ 1/(k + rank)。同一 key 只保留首次出现（词法优先带 citation 全字段）。"""
    by_key: dict[str, ChatEvidence] = {}
    for evidence in lexical:
        by_key.setdefault(evidence.key, evidence)
    for evidence in vector:
        by_key.setdefault(evidence.key, evidence)

    scores: dict[str, float] = {}
    for rank, evidence in enumerate(lexical):
        scores[evidence.key] = scores.get(evidence.key, 0.0) + 1.0 / (k + rank + 1)
    for rank, evidence in enumerate(vector):
        scores[evidence.key] = scores.get(evidence.key, 0.0) + 1.0 / (k + rank + 1)

    ordered = sorted(by_key.values(), key=lambda item: scores.get(item.key, 0.0), reverse=True)
    return ordered[:limit]


def hybrid_search(
    db: Session,
    tools: ChatTools,
    query: str,
    *,
    limit: int = 8,
) -> list[ChatEvidence]:
    """语义 + 词法混合检索：向量不可用时退化为纯词法结果（顺序保持不变）。"""
    lexical = tools.search_documents(query)
    vector = search_vector(db, query, role=tools.role, limit=limit)
    if not vector:
        return lexical[:limit]
    settings = get_settings()
    return fuse(lexical, vector, k=settings.search_rrf_k, limit=limit)

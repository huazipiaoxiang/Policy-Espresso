"""进程内向量索引：懒加载 + TTL 缓存 + 余弦召回。

设计约束：
- 索引只驻留「向量 + 主键」，切片正文按需回查，避免把整库正文常驻内存；
- numpy 缺失（可选依赖未装）时整体禁用向量通道，由调用方降级为纯词法；
- 任何异常都只记日志并返回 None，绝不阻断检索主流程。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import DocumentChunk

log = get_logger("search.index")

try:  # numpy 是可选依赖：缺失时禁用向量通道，不阻断词法检索
    import numpy as np
except ImportError:  # pragma: no cover - 取决于运行环境
    np = None  # type: ignore[assignment]

INDEX_TTL_SECONDS = 300


@dataclass(frozen=True)
class ChunkHit:
    """向量召回结果（不含正文，正文由检索层按需回查）。"""

    chunk_id: str
    document_id: str
    policy_id: str | None
    chunk_index: int
    score: float


@dataclass
class VectorIndex:
    chunk_ids: list[str]
    document_ids: list[str]
    policy_ids: list[str | None]
    chunk_indexes: list[int]
    matrix: Any          # numpy 2D float32
    norms: Any           # numpy 1D float32，行范数，避免每次重算
    built_at: float

    @property
    def size(self) -> int:
        return len(self.chunk_ids)

    def search(self, vector: list[float], top_k: int) -> list[ChunkHit]:
        if np is None or self.size == 0 or not vector:
            return []
        query = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm == 0:
            return []
        similarity = (self.matrix @ query) / (self.norms * norm)
        count = min(int(top_k), self.size)
        if count <= 0:
            return []
        # 全量排序在 3 万级切片上仍是毫秒级，无需引入近似索引
        order = np.argsort(-similarity)[:count]
        return [
            ChunkHit(
                chunk_id=self.chunk_ids[int(rank)],
                document_id=self.document_ids[int(rank)],
                policy_id=self.policy_ids[int(rank)],
                chunk_index=self.chunk_indexes[int(rank)],
                score=float(similarity[int(rank)]),
            )
            for rank in order
            if float(similarity[int(rank)]) > 0
        ]


_INDEX: VectorIndex | None = None
_INDEX_AT = 0.0


def numpy_available() -> bool:
    return np is not None


def invalidate() -> None:
    """清空索引缓存（重建嵌入后调用）。"""
    global _INDEX, _INDEX_AT
    _INDEX = None
    _INDEX_AT = 0.0


def build_index(db: Session) -> VectorIndex | None:
    """从 document_chunk 读取已嵌入切片，构建内存索引。无数据返回 None。"""
    if np is None:
        return None
    rows = list(db.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.policy_id,
            DocumentChunk.chunk_index,
            DocumentChunk.embedding,
        ).where(DocumentChunk.embedding.isnot(None))
    ).all())
    vectors: list[Any] = []
    chunk_ids: list[str] = []
    document_ids: list[str] = []
    policy_ids: list[str | None] = []
    chunk_indexes: list[int] = []
    dimension: int | None = None
    for chunk_id, document_id, policy_id, chunk_index, blob in rows:
        if not blob:
            continue
        array = np.frombuffer(blob, dtype=np.float32)
        if dimension is None:
            dimension = int(array.shape[0])
        elif int(array.shape[0]) != dimension:
            continue  # 维度不一致（换过嵌入模型）的切片跳过，避免矩阵错位
        vectors.append(array)
        chunk_ids.append(chunk_id)
        document_ids.append(document_id)
        policy_ids.append(policy_id)
        chunk_indexes.append(int(chunk_index or 0))
    if not vectors:
        return None
    matrix = np.stack(vectors).astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1e-9
    return VectorIndex(
        chunk_ids=chunk_ids,
        document_ids=document_ids,
        policy_ids=policy_ids,
        chunk_indexes=chunk_indexes,
        matrix=matrix,
        norms=norms,
        built_at=time.monotonic(),
    )


def get_index(db: Session, *, force: bool = False) -> VectorIndex | None:
    """带 TTL 的懒加载；构建失败返回 None（调用方降级）。"""
    global _INDEX, _INDEX_AT
    now = time.monotonic()
    if not force and _INDEX is not None and now - _INDEX_AT < INDEX_TTL_SECONDS:
        return _INDEX
    try:
        index = build_index(db)
    except Exception as exc:  # 索引构建是增强通道，失败只记日志
        log.warning("search_index_build_failed", error_type=type(exc).__name__)
        _INDEX, _INDEX_AT = None, now
        return None
    _INDEX, _INDEX_AT = index, now
    if index is None:
        log.info("search_index_empty", reason="no_embedded_chunks")
    return index

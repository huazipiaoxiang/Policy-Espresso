"""检索层：向量 + 词法混合 + RRF 融合；本地进程内索引，云端预留 pgvector。

对外只暴露三个入口：
- ``hybrid_search`` —— Chat Agent 的语义检索工具；
- ``rebuild_index`` —— 离线/内部任务触发的切片与嵌入重建；
- ``vector_available`` —— 运行时探活，供日志与降级判断使用。

向量通道是增强项：索引为空、numpy 缺失、嵌入不可达时一律静默降级为纯词法。
"""
from __future__ import annotations

from app.search.retriever import fuse, hybrid_search, search_vector, vector_available

__all__ = ["hybrid_search", "search_vector", "vector_available", "fuse", "rebuild_index"]


def rebuild_index(*, limit: int = 0) -> dict:
    """重建切片与嵌入（延迟导入，避免运行期依赖 jobs 层）。"""
    from app.jobs.embed_job import rebuild_chunks

    return rebuild_chunks(limit=limit)

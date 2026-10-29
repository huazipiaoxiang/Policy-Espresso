"""检索层测试：切分、嵌入写入、RRF 融合与向量不可用时的降级。

向量通道是增强项：numpy 缺失/开关关闭时必须静默退化为纯词法，且不能抛异常。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.chat.tools import ChatEvidence, ChatTools
from app.db.models import Base, Document, DocumentChunk, Source
from app.jobs.embed_job import embed_document, rebuild_chunks
from app.search.chunking import chunk_text
from app.search.retriever import fuse, hybrid_search, search_vector


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_document(db: Session, *, title: str, content: str, doc_id: str) -> Document:
    source = db.scalar(select(Source).where(Source.code == "regulator"))
    if source is None:
        source = Source(id="s_regulator", code="regulator", name="示例监管机构", org="示例监管机构",
                        jurisdiction="HK", tier=1, adapter="manual", url="https://regulator.example/")
        db.add(source)
        db.flush()
    document = Document(id=doc_id, source_id=source.id, url=f"https://regulator.example/{doc_id}",
                        canonical_url=f"https://regulator.example/{doc_id}", title=title,
                        content_text=content, content_hash=f"hash-{doc_id}")
    db.add(document)
    db.commit()
    return document


def evidence(key: str, title: str) -> ChatEvidence:
    return ChatEvidence(key=key, kind="document", title=title, text=f"{title} 片段",
                        citation={"id": key, "type": "document", "title": title, "url": ""})


# ---------- 切分 ----------


def test_chunk_text_respects_size_overlap_and_limit():
    text = "第一句话。" * 400
    chunks = chunk_text(text, size=200, overlap=40, max_chunks=3)
    assert len(chunks) == 3
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_keeps_content_without_splitting_words_away():
    original = "".join(f"条款{i}：内容{i}。" for i in range(200))
    joined = "".join(chunk_text(original, size=300, overlap=50, max_chunks=50))
    for index in (0, 50, 199):
        assert f"条款{index}：内容{index}。" in joined


# ---------- 融合 ----------


def test_rrf_fusion_ranks_dual_hit_first():
    lexical = [evidence("document:a", "A"), evidence("document:b", "B")]
    vector = [evidence("document:b", "B"), evidence("document:c", "C")]
    fused = fuse(lexical, vector, k=60, limit=8)
    assert [item.key for item in fused] == ["document:b", "document:a", "document:c"]


def test_fusion_dedupes_and_respects_limit():
    lexical = [evidence(f"document:{index}", f"T{index}") for index in range(10)]
    assert len(fuse(lexical, lexical, limit=3)) == 3


# ---------- 降级 ----------


def test_vector_search_is_skipped_when_disabled(db, monkeypatch):
    monkeypatch.setattr("app.search.retriever.get_settings",
                        lambda: SimpleNamespace(search_vector_enabled=False, search_rrf_k=60))
    assert search_vector(db, "任意查询", role="analyst") == []


def test_hybrid_search_degrades_to_lexical_without_vector(db, monkeypatch):
    add_document(db, title="虚拟银行监管新规", content="虚拟银行监管新规 原文", doc_id="d_1")
    monkeypatch.setattr("app.search.retriever.get_settings",
                        lambda: SimpleNamespace(search_vector_enabled=False, search_rrf_k=60))
    result = hybrid_search(db, ChatTools(db, "analyst"), "虚拟银行监管新规")
    assert [item.key for item in result] == ["document:d_1"]


# ---------- 嵌入写入 ----------


def test_embed_document_writes_chunks_and_is_idempotent(db):
    document = add_document(db, title="长文政策", content="这是一段用于切片的正文。" * 200, doc_id="d_long")
    written = embed_document(db, document)
    assert written >= 2
    rows = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == "d_long")))
    assert len(rows) == written
    assert all(row.embedding for row in rows)
    assert embed_document(db, document) == 0, "内容未变且已嵌入时应跳过"


def test_embed_document_clears_chunks_when_content_emptied(db):
    document = add_document(db, title="长文政策", content="正文。" * 500, doc_id="d_gone")
    assert embed_document(db, document) >= 1
    document.content_text = ""
    db.commit()
    assert embed_document(db, document) == 0
    assert db.scalar(select(DocumentChunk.id).where(DocumentChunk.document_id == "d_gone")) is None


def test_rebuild_chunks_without_numpy_reports_degradation(db, monkeypatch):
    monkeypatch.setattr("app.search.index.numpy_available", lambda: False)
    add_document(db, title="政策", content="正文。" * 100, doc_id="d_1")
    assert rebuild_chunks(db)["status"] == "numpy_missing"


def test_rebuild_and_search_roundtrip(db, monkeypatch):
    pytest.importorskip("numpy")
    # mock 嵌入是按 hash 生成的伪向量，没有语义含义；这里换成确定性的「词袋」向量，
    # 让「跨境支付」的查询与对应文档在向量空间里确实更近。
    dims = ("跨境", "支付", "试点", "办法", "条款", "工资", "最低", "标准")
    monkeypatch.setattr(
        "app.search.embedder.embed_texts",
        lambda texts: SimpleNamespace(
            vectors=[[float(text.count(word)) for word in dims] for text in texts],
            model="fake-bag", latency_ms=0,
        ),
    )

    add_document(db, title="跨境支付试点办法", content="跨境支付试点办法 详细条款。" * 120, doc_id="d_cross")
    add_document(db, title="无关的最低工资通知", content="最低工资标准调整。", doc_id="d_wage")
    result = rebuild_chunks(db)
    assert result["status"] == "ok" and result["chunks"] >= 2

    from app.search import index as vector_index

    vector_index.invalidate()
    hits = search_vector(db, "跨境支付试点办法", role="analyst", limit=3)
    assert hits, "重建索引后语义检索应能召回对应文档"
    assert hits[0].key == "document:d_cross"
    assert hits[0].citation["type"] == "document"
    assert "document:d_wage" not in [hit.key for hit in hits]

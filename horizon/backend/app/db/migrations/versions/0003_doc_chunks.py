"""正文切片与向量表（Chat Agent 语义检索通道）

Revision ID: 0003_doc_chunks
Revises: 0002_pgvector
Create Date: 2026-10-28

说明：
- 显式 op.create_table（0001_initial 已 create_all，避免全新库上重复建表）；
- SQLite / PG 双兼容，向量索引仅在 PG 生效（沿用 0002 的 _is_postgres 守卫）；
- 向量不可用时（SQLite 且未建索引）检索层静默降级为纯词法，见 app/search/。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0003_doc_chunks"
down_revision = "0002_pgvector"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """离线（--sql）与在线两种模式都可靠地拿到 dialect 名。"""
    if context.is_offline_mode():
        return context.get_context().dialect.name == "postgresql"
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("document_id", sa.String(32), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("policy_id", sa.String(32), sa.ForeignKey("policy.id"), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_document_chunk_document_id", "document_chunk", ["document_id"])
    op.create_index("ix_document_chunk_policy_id", "document_chunk", ["policy_id"])
    op.create_index("ix_document_chunk_content_hash", "document_chunk", ["content_hash"])
    op.create_index(
        "uq_doc_chunk_doc_index", "document_chunk", ["document_id", "chunk_index"], unique=True,
    )
    if _is_postgres():
        # PG 环境预留 pgvector 列与索引；SQLite 跳过，由进程内索引做余弦检索。
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.drop_index("uq_doc_chunk_doc_index", table_name="document_chunk")
    op.drop_index("ix_document_chunk_content_hash", table_name="document_chunk")
    op.drop_index("ix_document_chunk_policy_id", table_name="document_chunk")
    op.drop_index("ix_document_chunk_document_id", table_name="document_chunk")
    op.drop_table("document_chunk")

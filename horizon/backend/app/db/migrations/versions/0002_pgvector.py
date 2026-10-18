"""pgvector 扩展与向量索引（Phase 5，仅 PostgreSQL 生效）

Revision ID: 0002_pgvector
Revises: 0001_initial
Create Date: 2026-10-17

说明：SQLite 环境自动跳过（向量检索在本地降级为关键词，见 03 §3.3）。
云端 HNSW 参数按 03 文档：m=16, ef_construction=64。
"""
from alembic import context, op

revision = "0002_pgvector"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """离线（--sql）与在线两种模式都可靠地拿到 dialect 名。"""
    if context.is_offline_mode():
        return context.get_context().dialect.name == "postgresql"
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return  # 本地 SQLite：跳过，向量能力不可用时降级关键词检索
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # 案例集合的向量索引（政策/业务图谱集合在接入嵌入 Provider 后由 repository 建）
    op.execute(
        'CREATE INDEX IF NOT EXISTS idx_case_embedding ON "case" '
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP INDEX IF EXISTS idx_case_embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")

"""document 增加标题+正文指纹（跨源转载判重）

Revision ID: 0006_doc_fingerprint
Revises: 0005_policy_preprocess
Create Date: 2026-11-20

说明：
- `content_fingerprint` = sha256(normalize(title) + normalize(content))，
  同标题同正文即视为同一政策，多站转载（URL 不同）也能一次命中；
- 仅加 nullable 列 + 索引，SQLite / PG 双兼容；
- 存量文档由 `python -m app.jobs.dedup_job` 回填。
"""
from alembic import context, op
import sqlalchemy as sa

revision = "0006_doc_fingerprint"
down_revision = "0005_policy_preprocess"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all-based installations may already contain the column.
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns("document")}
    indexes = set() if inspector is None else {i["name"] for i in inspector.get_indexes("document")}
    if "content_fingerprint" not in columns:
        op.add_column(
            "document",
            sa.Column("content_fingerprint", sa.String(64), nullable=False, server_default=""),
        )
    if "ix_document_content_fingerprint" not in indexes:
        op.create_index("ix_document_content_fingerprint", "document", ["content_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_document_content_fingerprint", table_name="document")
    op.drop_column("document", "content_fingerprint")

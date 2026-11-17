"""initial schema（17 表，见 docs/04 §2）

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-17

说明：初始版本直接按 metadata 建表，保证 SQLite/PG 一致；后续变更走 autogenerate。
"""
from alembic import op
from sqlalchemy import engine_from_config

from app.db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # document_chunk belongs to revision 0003, even when current metadata includes it.
    tables = [table for table in Base.metadata.sorted_tables if table.name != "document_chunk"]
    Base.metadata.create_all(bind, tables=tables)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)

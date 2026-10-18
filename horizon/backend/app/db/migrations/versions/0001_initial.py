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
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)

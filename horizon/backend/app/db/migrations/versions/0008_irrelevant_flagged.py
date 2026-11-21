"""policy 增加 irrelevant_flagged 字段（AI 判定疑似完全无影响，待跟进专员复核）

Revision ID: 0008_irrelevant_flagged
Revises: 0007_followup
Create Date: 2026-11-21

说明：
- 每日抓取分析后，AI 用确定性门禁判定「对汇丰完全无影响」的政策；
- 判定为无影响时不再自动删除，而是置 irrelevant_flagged=True，进入跟进中心待复核；
- 跟进专员可「保留」（置 followup=True 永久保留）或「删除」。
"""
from alembic import context, op
import sqlalchemy as sa

revision = "0008_irrelevant_flagged"
down_revision = "0007_followup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns("policy")}
    if "irrelevant_flagged" not in columns:
        op.add_column(
            "policy",
            sa.Column("irrelevant_flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("policy", "irrelevant_flagged")

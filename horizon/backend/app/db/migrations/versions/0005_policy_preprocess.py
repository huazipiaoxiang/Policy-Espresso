"""政策预处理表（抓取入库 + AI 分析后自动生成）

Revision ID: 0005_policy_preprocess
Revises: 0004_llm_policy_id
Create Date: 2026-11-20

说明：
- 一政策一条（policy_id 唯一）：关键词、影响业务、客户类型、
  损失/盈利/信誉/机会百分比、汇丰与他行反应链接、市场应用、其它补充；
- 百分比口径复用 domain/consumer_impact.compute_consumer_impact，0–100 程度分；
- 表已由 create_all 建立时（本地直跑）自动跳过，SQLite / PG 双兼容。
"""
from alembic import context, op
import sqlalchemy as sa

revision = "0005_policy_preprocess"
down_revision = "0004_llm_policy_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = None if context.is_offline_mode() else sa.inspect(bind)
    if inspector is not None and "policy_preprocess" in inspector.get_table_names():
        return  # 本地 create_all 已建表
    op.create_table(
        "policy_preprocess",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("policy_id", sa.String(32), sa.ForeignKey("policy.id"), nullable=False, unique=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("affected_business", sa.JSON(), nullable=True),
        sa.Column("customer_segments", sa.JSON(), nullable=True),
        sa.Column("loss_pct", sa.Float(), nullable=True),
        sa.Column("profit_pct", sa.Float(), nullable=True),
        sa.Column("reputation_pct", sa.Float(), nullable=True),
        sa.Column("opportunity_pct", sa.Float(), nullable=True),
        sa.Column("impact_total", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("hsbc_response", sa.JSON(), nullable=True),
        sa.Column("peer_bank_response", sa.JSON(), nullable=True),
        sa.Column("market_applications", sa.JSON(), nullable=True),
        sa.Column("extras", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_policy_preprocess_policy_id", "policy_preprocess", ["policy_id"], unique=True)
    op.create_index("idx_preprocess_total", "policy_preprocess", ["impact_total"])


def downgrade() -> None:
    op.drop_index("idx_preprocess_total", table_name="policy_preprocess")
    op.drop_index("ix_policy_preprocess_policy_id", table_name="policy_preprocess")
    op.drop_table("policy_preprocess")

"""llm_call_log 关联政策（AI 分析过程拆解展示用）

Revision ID: 0004_llm_policy_id
Revises: 0003_doc_chunks
Create Date: 2026-11-14

说明：
- 每条 LLM 调用记录可关联到触发分析的政策，用于详情页按步骤展示
  「分类打标 → 结构化抽取 → 适用性判定 → 影响分析 → 预警草稿」的调用明细；
- 历史数据（迁移前分析的）policy_id 为空，界面显示为未关联；
- 仅加 nullable 列 + 索引，SQLite / PG 双兼容。
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_llm_policy_id"
down_revision = "0003_doc_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_call_log", sa.Column("policy_id", sa.String(32), nullable=True))
    op.create_index("ix_llm_call_log_policy_id", "llm_call_log", ["policy_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_log_policy_id", table_name="llm_call_log")
    op.drop_column("llm_call_log", "policy_id")

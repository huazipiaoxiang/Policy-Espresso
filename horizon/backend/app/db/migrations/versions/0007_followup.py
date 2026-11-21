"""policy 增加 followup 字段（跟进专员标记跟进，豁免 5 年清理）

Revision ID: 0007_followup
Revises: 0006_doc_fingerprint
Create Date: 2026-11-21

说明：
- `followup` 为布尔标记：跟进专员在跟进中心对「疑似无影响」政策选择保留时置为 True；
- 置为 True 的政策永久保留，不参与「政策库/预处理仅保留 5 年」的清理；
- 仅加 nullable 列，SQLite / PG 双兼容。
"""
from alembic import context, op
import sqlalchemy as sa

revision = "0007_followup"
down_revision = "0006_doc_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns("policy")}
    if "followup" not in columns:
        op.add_column(
            "policy",
            sa.Column("followup", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("policy", "followup")

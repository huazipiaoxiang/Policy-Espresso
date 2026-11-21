#!/bin/sh
set -e

# 1) 应用数据库迁移
alembic upgrade head

# 2) create_all 兜底：确保所有模型表都存在（幂等，已存在跳过）。
#    旧库升级时若缺表（如 policy_preprocess / document_chunk / scope_judgement），
#    迁移可能因 inspector 判重而跳过，这里兜底补齐，避免删除/列表出现 500。
python -c "from app.db.models import Base; from app.db.session import engine; Base.metadata.create_all(engine)"

# 3) 启动 API
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

"""Phase 5 验收（本地等价验证）：存储抽象 / PG 迁移 SQL / 内部触发鉴权 / Provider 降级。"""
from __future__ import annotations

import os
from pathlib import Path


def test_storage_local_roundtrip(tmp_path):
    os.environ["STORAGE_DIR"] = str(tmp_path)
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.storage import get_storage

    storage = get_storage()
    assert storage.name == "local"
    key = "snapshots/test-doc.html"
    path = storage.save(key, "<html>政策原文</html>")
    assert Path(path).exists()
    assert storage.load(key) == "<html>政策原文</html>"
    get_settings.cache_clear()


def test_oss_requires_config():
    os.environ["STORAGE_BACKEND"] = "oss"
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.storage import get_storage

    try:
        get_storage()
        raise AssertionError("OSS 配置不完整必须报错")
    except ValueError:
        pass
    finally:
        os.environ["STORAGE_BACKEND"] = "local"
        get_settings.cache_clear()


def _offline_sql(database_url: str) -> str:
    from alembic.config import Config
    from alembic import command
    import io
    import contextlib

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    # env.py 以环境变量 DATABASE_URL 为最高优先级，测试需同步覆盖
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            command.upgrade(cfg, "head", sql=True)
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original
    return buf.getvalue()


def test_alembic_offline_sql_for_postgres():
    """离线生成 PG 迁移 SQL：验证 alembic 可在 PG dialect 下渲染（ECS/RDS 前置检查）。"""
    sql = _offline_sql("postgresql+psycopg://u:p@localhost/db")
    assert "CREATE TABLE" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql  # 0002_pgvector 已渲染


def test_alembic_offline_sql_for_sqlite_skips_vector():
    """SQLite 离线 SQL 不得包含 pgvector（本地降级）。"""
    sql = _offline_sql("sqlite:///tmp/horizon_offline.db")
    assert "CREATE TABLE" in sql
    assert "CREATE EXTENSION" not in sql


def test_internal_trigger_requires_token(client):
    """FC 内部触发：无令牌/错令牌必须拒绝。"""
    r = client.post("/api/v1/internal/jobs/crawl")
    assert r.status_code == 403  # 未配置 JOB_TRIGGER_TOKEN 时禁用

    import app.core.config as config_module

    settings = config_module.get_settings()
    settings.job_trigger_token = "secret-token"
    r = client.post("/api/v1/internal/jobs/crawl", headers={"X-Job-Token": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/v1/internal/jobs/crawl", headers={"X-Job-Token": "secret-token"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    settings.job_trigger_token = ""


def test_dashscope_missing_key_fails_fast():
    """云端 Provider 缺 Key 必须显式报错（不允许静默降级到幻觉输出）。"""
    os.environ["LLM_PROVIDER"] = "dashscope"
    os.environ["DASHSCOPE_API_KEY"] = ""
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.ai.provider import get_provider

        try:
            get_provider()
            raise AssertionError("缺 Key 必须报错")
        except ValueError:
            pass
    finally:
        os.environ["LLM_PROVIDER"] = "mock"
        os.environ["DASHSCOPE_API_KEY"] = "test-key"
        get_settings.cache_clear()

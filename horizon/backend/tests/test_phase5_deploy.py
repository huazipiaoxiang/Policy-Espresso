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


def test_alembic_fresh_sqlite_upgrade(tmp_path, monkeypatch):
    """全新数据库必须能完整迁移，并允许服务启动时再次执行。"""
    import sqlite3
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    database = tmp_path / "fresh.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "app/db/migrations"))
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    with sqlite3.connect(database) as db:
        from alembic.script import ScriptDirectory
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ScriptDirectory.from_config(cfg).get_current_head()
        indexes = {row[1] for row in db.execute("PRAGMA index_list(document_chunk)")}
        assert "uq_doc_chunk_doc_index" in indexes
        assert "policy_id" in {row[1] for row in db.execute("PRAGMA table_info(llm_call_log)")}


def test_alembic_upgrade_existing_metadata_database(tmp_path, monkeypatch):
    """兼容曾通过应用 create_all 建表的数据库，不删除已有表。"""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from app.db.models import Base

    backend_dir = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'existing.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    before = set(inspect(engine).get_table_names())
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "app/db/migrations"))
    command.upgrade(cfg, "head")
    assert before <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_alembic_offline_sql_creates_chunks_once():
    sql = _offline_sql("sqlite:///tmp/horizon_offline.db")
    assert sql.count("CREATE TABLE document_chunk (") == 1


def test_alembic_upgrades_old_call_logs_without_losing_data(tmp_path, monkeypatch):
    import sqlite3
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "old-call-logs.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "app/db/migrations"))
    command.upgrade(cfg, "0003_doc_chunks")
    with sqlite3.connect(database) as db:
        db.execute("DROP INDEX ix_llm_call_log_policy_id")
        db.execute("ALTER TABLE llm_call_log DROP COLUMN policy_id")
        db.execute("""INSERT INTO llm_call_log
            (id,provider,model,task,prompt_version,input_hash,tokens_in,tokens_out,latency_ms,status,at)
            VALUES ('old-log','mock','mock','classify','v1','hash',1,1,1,'ok','2026-11-17')""")
    command.upgrade(cfg, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT id,policy_id FROM llm_call_log").fetchone() == ("old-log", None)


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


def test_sqlite_to_pg_migration_covers_all_models():
    """PG 迁移清单必须覆盖全部模型，尤其推荐依赖的 policy_preprocess。"""
    import importlib.util
    from app.db.models import Base

    script = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "migrate_sqlite_to_pg.py"
    spec = importlib.util.spec_from_file_location("migrate_sqlite_to_pg", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module.TABLES) == set(Base.metadata.tables)
    assert "policy_preprocess" in module.TABLES


def test_startup_seed_includes_preprocess(monkeypatch):
    """上云启动自动 seed 必须补齐预处理，否则「为你推荐」为空。"""
    from contextlib import contextmanager

    import app.db.session as session_module
    import app.jobs.seed_job as seed_job
    import app.main as main

    calls: list[str] = []

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(session_module, "SessionLocal", fake_session)
    names = (
        "seed_sources", "seed_cases", "seed_demo_subsidy_policy",
        "seed_known_policies", "seed_rm_users", "seed_preprocess",
    )
    for name in names:
        monkeypatch.setattr(seed_job, name, lambda db, _n=name: calls.append(_n) or 0)

    counts = main.seed_on_startup()

    assert set(calls) == set(names)
    assert counts["preprocess"] == 0

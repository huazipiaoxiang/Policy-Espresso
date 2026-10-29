import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_DIR}/tests/test_horizon.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("API_KEY", "test-key")
# 本地 backend/.env 可能开启离线规则兜底；测试按用例显式切换该开关，这里统一归零保证确定性。
os.environ["LLM_OFFLINE_RULES"] = "false"

TEST_DB = BACKEND_DIR / "tests" / "test_horizon.db"


@pytest.fixture(scope="session", autouse=True)
def _fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    yield
    from app.db.session import engine

    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(autouse=True)
def _no_network_attachment_parse(monkeypatch):
    """管线测试离线确定性：附件网络抓取打桩为恒等；PDF 解析本身在 test_pdf_parse.py 覆盖。"""
    from app.ingest import pipeline

    monkeypatch.setattr(pipeline, "enrich_attachments", lambda atts, max_count=None: atts)


@pytest.fixture(autouse=True)
def _clear_retrieval_caches():
    """检索缓存是进程级的，必须逐用例失效，否则跨用例（各自独立的内存库）会串味。"""
    from app.chat.tools import clear_query_caches
    from app.search import index as vector_index

    clear_query_caches()
    vector_index.invalidate()
    yield
    clear_query_caches()
    vector_index.invalidate()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db.models import Base
    from app.db.session import engine
    from app.main import app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        c.headers.update({"X-API-Key": "test-key"})
        yield c
    engine.dispose()

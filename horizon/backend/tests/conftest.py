import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_DIR}/tests/test_horizon.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("API_KEY", "test-key")

TEST_DB = BACKEND_DIR / "tests" / "test_horizon.db"


@pytest.fixture(scope="session", autouse=True)
def _fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(autouse=True)
def _no_network_attachment_parse(monkeypatch):
    """管线测试离线确定性：附件网络抓取打桩为恒等；PDF 解析本身在 test_pdf_parse.py 覆盖。"""
    from app.ingest import pipeline

    monkeypatch.setattr(pipeline, "enrich_attachments", lambda atts, max_count=None: atts)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db.models import Base
    from app.db.session import engine
    from app.main import app

    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        c.headers.update({"X-API-Key": "test-key"})
        yield c

"""抓取韧性验收（06 §8）：robots 遵守、404 隔离、断供源不影响其他源、熔断、3 次连跑无重复。"""
from datetime import datetime, timedelta, timezone

from app.ingest import http
from app.ingest.adapters import ItemRef, RawDoc, register
from app.ingest.pipeline import crawl_source, is_circuit_open, update_source_health
from app.jobs.crawl_job import run_crawl
from app.jobs.health_job import compute_source_health

def _html(marker: str) -> str:
    """每个测试用独立正文，避免跨测试触发跨源近重复聚类。"""
    return f"""
<html><head><title>金融政策样本{marker}</title></head>
<body><article><h1>金融政策样本{marker}</h1>
<p>本办法自2026年11月1日起施行，适用于在广东省内注册的商业银行。{marker}</p>
</article></body></html>
"""


def _mk_source(db, code: str, adapter: str):
    from app.db.models import Source

    src = Source(code=code, name=code, jurisdiction="GD", adapter=adapter, url="https://ex.com")
    db.add(src)
    db.commit()
    return src


def _adapter_cls(name, docs, fail_urls=None, discover_exc=None):
    fail_urls = fail_urls or {}

    @register(name)
    class _Fake:
        def __init__(self, source):
            pass

        def discover(self, since):
            if discover_exc:
                raise discover_exc
            return [ItemRef(url=u, title="t") for u in docs]

        def fetch(self, ref):
            if ref.url in fail_urls:
                raise fail_urls[ref.url]
            return RawDoc(url=ref.url, html=docs[ref.url].encode(), headers={})

    return _Fake


def test_robots_disallowed_path_skipped(client):
    """robots.txt 禁止的路径：整条记 ignored，且同源其他条目不受影响。"""
    from app.db.session import SessionLocal

    docs = {
        "https://ex.com/allowed": _html("R"),
        "https://ex.com/blocked": _html("R"),
    }
    _adapter_cls("fake_robots", docs,
                 fail_urls={"https://ex.com/blocked": http.RobotsDisallowedError("robots.txt 禁止抓取")})
    with SessionLocal() as db:
        src = _mk_source(db, "src_robots", "fake_robots")
        stats = crawl_source(db, src)
        assert stats["created"] == 1
        assert stats["ignored"] == 1
        assert any("robots" in e for e in stats["errors"])


def test_http_robots_layer(monkeypatch):
    """http 层：robots parser can_fetch=False → 抛 RobotsDisallowedError，不发请求。"""

    class _DenyAll:
        def can_fetch(self, ua, url):
            return False

    monkeypatch.setitem(http._robots_cache, "https://deny.example.com", _DenyAll())
    try:
        http.fetch("https://deny.example.com/x")
        raise AssertionError("应抛 RobotsDisallowedError")
    except http.RobotsDisallowedError:
        pass


def test_robots_fetched_with_crawler_ua(monkeypatch):
    """robots.txt 用可识别 UA 抓取：403 → 全站禁止；200 → 按规则解析；404 → 放行。"""
    calls = []

    class _Resp:
        def __init__(self, status, text=""):
            self.status_code = status
            self.text = text

    def _get(url, **kw):
        calls.append(kw.get("headers", {}).get("User-Agent", ""))
        if "ok.example.com" in url:
            return _Resp(200, "User-agent: *\nDisallow: /private/\n")
        if "forbidden.example.com" in url:
            return _Resp(403)
        return _Resp(404)

    monkeypatch.setattr(http.httpx, "get", _get)
    http._robots_cache.clear()
    assert http._robots_allows("https://ok.example.com/public/x")
    assert not http._robots_allows("https://ok.example.com/private/x")
    assert not http._robots_allows("https://forbidden.example.com/anything")
    assert http._robots_allows("https://norobots.example.com/x")
    assert all("HORIZON-PolicyMonitor" in ua for ua in calls)
    http._robots_cache.clear()


def test_404_failed_but_others_ok(client):
    """单条 404：记 failed，不影响同源其他条目入库。"""
    from app.db.models import Document
    from app.db.session import SessionLocal

    docs = {
        "https://ex.com/ok1": _html("N"),
        "https://ex.com/gone": _html("N"),
        "https://ex.com/ok2": _html("X2"),
    }
    _adapter_cls("fake_404", docs,
                 fail_urls={"https://ex.com/gone": http.FetchError("HTTP 404", retryable=False, status=404)})
    with SessionLocal() as db:
        src = _mk_source(db, "src_404", "fake_404")
        stats = crawl_source(db, src)
        assert stats["created"] == 2 and stats["failed"] == 1
        assert db.query(Document).filter(Document.source_id == src.id).count() == 2


def test_broken_source_does_not_block_others(client):
    """某源 discover 直接抛异常：该源 job 记 failed，其他源照常抓取。"""
    from app.db.session import SessionLocal

    _adapter_cls("fake_down", {}, discover_exc=ConnectionError("站点不可达"))
    _adapter_cls("fake_ok", {"https://ex.com/fine": _html("G")})
    with SessionLocal() as db:
        bad = _mk_source(db, "src_down", "fake_down")
        good = _mk_source(db, "src_ok", "fake_ok")
        stats_bad = run_crawl(db, bad)
        stats_good = run_crawl(db, good)
        assert stats_bad["failed"] == 1 and stats_bad["errors"]
        assert stats_good["created"] == 1
        db.refresh(bad)
        assert bad.health["consecutive_fail"] == 1


def test_circuit_breaker(client):
    """连续失败 5 次 → 熔断 6 小时；熔断期 is_circuit_open=True。"""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        src = _mk_source(db, "src_circuit", "fake_ok")  # 复用已注册适配器，不实际抓取
        for _ in range(5):
            update_source_health(db, src, ok=False, latency_ms=None, stats={"errors": ["x"]})
        db.refresh(src)
        assert src.health["consecutive_fail"] == 5
        assert src.health["circuit_open_until"]
        assert is_circuit_open(src)
        # 成功后复位
        update_source_health(db, src, ok=True, latency_ms=100, stats={})
        db.refresh(src)
        assert src.health["consecutive_fail"] == 0 and src.health["circuit_open_until"] is None
        assert not is_circuit_open(src)
        # 过期熔断不拦截
        src.health = {"circuit_open_until": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
        assert not is_circuit_open(src)


def test_three_consecutive_runs_no_duplicates(client):
    """同一批内容连跑 3 次：仅首轮新增，后续 0 新增 0 重复，文档总数不变。"""
    from app.db.models import Document
    from app.db.session import SessionLocal

    docs = {f"https://ex.com/t{i}": _html(f"T{i}") for i in range(4)}
    _adapter_cls("fake_3run", docs)
    with SessionLocal() as db:
        src = _mk_source(db, "src_3run", "fake_3run")
        s1 = crawl_source(db, src)
        s2 = crawl_source(db, src)
        s3 = crawl_source(db, src)
        assert s1["created"] == 4 and s1["duplicate"] == 0
        for s in (s2, s3):
            assert s["created"] == 0 and s["duplicate"] == 0 and s["failed"] == 0
        assert db.query(Document).filter(Document.source_id == src.id).count() == 4


def test_health_check_flags_redesign(client):
    """06 §6：7 天新增 0 条但历史有产出 → 疑似改版告警。"""
    from app.db.models import Document
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        src = _mk_source(db, "src_health", "fake_ok")
        old = Document(
            source_id=src.id, url="https://ex.com/old", canonical_url="https://ex.com/old",
            title="旧文档", content_text="旧", content_hash="h",
            fetched_at=datetime.now(timezone.utc) - timedelta(days=30), status="processed",
        )
        db.add(old)
        db.commit()
        result = compute_source_health(db, src)
        db.commit()
        assert any("疑似改版" in a for a in result["alerts"])

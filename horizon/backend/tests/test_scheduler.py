"""Scheduler contracts: daily idempotency, isolation, reanalysis and observability."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Document, JobRun, Source
from app.db.session import SessionLocal
from app.jobs import scheduler


def _fake_crawl(db, source, job_id):  # noqa: ANN001
    job = db.get(JobRun, job_id)
    job.status = "ok"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"discovered": 3, "created": 2, "updated": 1, "failed": 0, "errors": []}


def test_manual_source_run_executes_crawl_and_records_job(client, monkeypatch):
    """立即抓取要当场跑完并回写运行记录：只登记不执行会让按钮永远停在 running。"""
    with SessionLocal() as db:
        src = Source(code="manual_run", name="manual", jurisdiction="HK", adapter="manual",
                     url="https://example.com", enabled=True)
        db.add(src)
        db.commit()
        source_id = src.id

    monkeypatch.setattr("app.jobs.crawl_job.run_crawl", _fake_crawl)
    monkeypatch.setattr(scheduler, "analyze_all_pending",
                        lambda: {"analyzed": 2, "skipped": 0, "failed": 0, "errors": []})

    from app.jobs.crawl_job import current_window

    day = current_window()
    first = client.post(f"/api/v1/sources/{source_id}/run", headers={"X-Demo-Role": "admin"})
    assert first.status_code == 200
    body = first.json()
    assert (body["discovered"], body["created"], body["updated"], body["analyzed"]) == (3, 2, 1, 2)
    with SessionLocal() as db:
        job = db.get(JobRun, body["job_id"])
        assert job.source_id == source_id and job.status == "ok" and job.finished_at is not None
        assert job.run_window == f"{day}#1"  # 手动抓取按当日第几次登记，不受每日幂等键限制

    second = client.post(f"/api/v1/sources/{source_id}/run", headers={"X-Demo-Role": "admin"})
    assert second.status_code == 200
    assert second.json()["job_id"] != body["job_id"]
    with SessionLocal() as db:
        assert db.get(JobRun, second.json()["job_id"]).run_window == f"{day}#2"

    with SessionLocal() as db:
        db.get(Source, source_id).enabled = False
        db.commit()
    blocked = client.post(f"/api/v1/sources/{source_id}/run", headers={"X-Demo-Role": "admin"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SOURCE_DISABLED"


def test_manual_source_run_guarded_while_running_or_circuit_open(client):
    with SessionLocal() as db:
        src = Source(code="manual_guard", name="guard", jurisdiction="HK", adapter="manual",
                     url="https://example.com", enabled=True)
        db.add(src)
        db.commit()
        db.add(JobRun(job_type="crawl", source_id=src.id, run_window="20261027090000", status="running"))
        db.commit()
        source_id = src.id

    overlap = client.post(f"/api/v1/sources/{source_id}/run", headers={"X-Demo-Role": "admin"})
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "CRAWL_RUNNING"

    with SessionLocal() as db:
        db.scalar(select(JobRun).where(
            JobRun.source_id == source_id, JobRun.status == "running",
        )).status = "ok"
        db.get(Source, source_id).health = {
            "circuit_open_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        db.commit()

    circuit = client.post(f"/api/v1/sources/{source_id}/run", headers={"X-Demo-Role": "admin"})
    assert circuit.status_code == 409
    assert circuit.json()["error"]["code"] == "CIRCUIT_OPEN"


def test_daily_schedule_health_and_monday_heartbeat(client):
    jobs = {job.id: job for job in scheduler.build_scheduler().get_jobs()}
    assert set(jobs) == {"crawl_all", "health_check", "heartbeat"}
    assert all(job.max_instances == 1 and job.coalesce for job in jobs.values())
    assert str(jobs["crawl_all"].trigger.timezone) == "Asia/Hong_Kong"
    assert "hour='9'" in str(jobs["crawl_all"].trigger)
    assert "minute='0'" in str(jobs["crawl_all"].trigger)
    assert "minute='0'" in str(jobs["health_check"].trigger)
    assert "day_of_week='mon'" in str(jobs["heartbeat"].trigger)
    assert "hour='8'" in str(jobs["heartbeat"].trigger)


def test_daily_crawl_isolates_source_failure_and_deduplicates(client, monkeypatch):
    with SessionLocal() as db:
        for index in range(6):
            code = f"sched_{index}"
            db.add(Source(code=code, name=code, jurisdiction="HK", adapter="manual",
                          url="https://example.com", enabled=True))
        db.add(Source(code="sched_disabled", name="disabled", jurisdiction="HK", adapter="manual",
                      url="https://example.com", enabled=False))
        db.commit()

    calls = []

    def fake_run(db, src, job_id):
        calls.append(src.code)
        if src.code == "sched_0":
            raise RuntimeError("source unavailable")
        return {"discovered": 1, "created": 1, "updated": 0, "failed": 0, "errors": []}

    monkeypatch.setattr(scheduler, "run_crawl", fake_run)
    stats = scheduler.crawl_all()
    stats_again = scheduler.crawl_all()
    assert stats["created"] == 5 and stats["failed"] == 1
    assert stats_again["created"] == 0 and stats_again["failed"] == 0
    assert len(calls) == 6
    with SessionLocal() as db:
        jobs = db.scalars(select(JobRun).where(JobRun.job_type == "crawl")).all()
        assert len(jobs) == 6
        assert sum(job.status == "failed" for job in jobs) == 1
        failed = next(job for job in jobs if job.status == "failed")
        assert "source unavailable" in failed.error


def test_concurrent_crawl_invocation_is_skipped(client):
    scheduler._crawl_lock.acquire()
    try:
        result = scheduler.crawl_all()
    finally:
        scheduler._crawl_lock.release()
    assert result["status"] == "already_running"


def test_changed_document_is_requeued(client):
    from app.ingest.adapters import ItemRef, RawDoc, register
    from app.ingest.pipeline import crawl_source

    url = "https://example.com/requeue"
    docs = {url: "<h1>银行政策</h1><p>2026年10月20日，适用于外资银行的政策正文，内容长度超过五十字，用于验证变更后重新进入分析队列。</p>"}

    @register("sched_requeue")
    class Adapter:
        def __init__(self, source):
            pass

        def discover(self, since):
            return [ItemRef(url=url, title="银行政策")]

        def fetch(self, ref):
            return RawDoc(url=ref.url, html=docs[ref.url].encode(), headers={})

    with SessionLocal() as db:
        src = Source(code="sched_requeue", name="requeue", jurisdiction="HK", adapter="sched_requeue", url=url)
        db.add(src)
        db.commit()
        crawl_source(db, src)
        doc = db.scalar(select(Document).where(Document.canonical_url == url))
        doc.status = "processed"
        db.commit()
        docs[url] += "<p>新增变更内容</p>"
        crawl_source(db, src)
        db.refresh(doc)
        assert doc.status == "new"
        assert len(doc.versions) == 1


def test_analyze_drains_all_changed_documents(client, monkeypatch):
    monkeypatch.setattr("app.jobs.analyze_job.analyze_document", lambda db, doc: None)
    with SessionLocal() as db:
        src = Source(code="sched_batch", name="batch", jurisdiction="HK", adapter="manual", url="https://example.com")
        db.add(src)
        db.flush()
        for index in range(11):
            db.add(Document(source_id=src.id, url=f"https://example.com/{index}", canonical_url=f"https://example.com/{index}",
                            title="policy", content_text="content", content_hash=f"h{index}", status="new"))
        db.commit()
        pending = db.query(Document).filter(Document.status == "new", Document.duplicate_of.is_(None)).count()
        assert pending >= 11
        assert scheduler.analyze_all_pending()["skipped"] == pending


def test_analyze_and_health_job_results_persisted(client):
    with SessionLocal() as db:
        failed = scheduler.analyze_all_pending()
        assert failed["failed"] == 0
        assert db.scalar(select(JobRun).where(JobRun.job_type == "analyze").order_by(JobRun.started_at.desc())).status == "ok"
        health = scheduler.run_health_check()
        assert isinstance(health, dict)
        assert db.scalar(select(JobRun).where(JobRun.job_type == "health").order_by(JobRun.started_at.desc())).status == "ok"
        scheduler._heartbeat()
        assert db.scalar(select(JobRun).where(JobRun.job_type == "heartbeat").order_by(JobRun.started_at.desc())).status == "ok"


def test_health_check_isolates_source_failure(client, monkeypatch):
    with SessionLocal() as db:
        for code in ("health_bad", "health_good"):
            db.add(Source(code=code, name=code, jurisdiction="HK", adapter="manual",
                          url="https://example.com", enabled=True))
        db.commit()

    def fake_health(db, source):
        if source.code == "health_bad":
            raise RuntimeError("health probe failed")
        return {"alerts": [], "success_rate_7d": 1.0, "new_docs_7d": 2}

    monkeypatch.setattr("app.jobs.health_job.compute_source_health", fake_health)
    result = scheduler.run_health_check()
    assert "health probe failed" in result["health_bad"]["error"]
    assert result["health_good"]["new_docs_7d"] == 2
    with SessionLocal() as db:
        job = db.scalar(select(JobRun).where(JobRun.job_type == "health").order_by(JobRun.started_at.desc()))
        assert job.status == "failed"
        assert job.stats == {"sources": 2, "succeeded": 1, "failed": 1}
        assert "health probe failed" in job.error


def test_concurrent_health_check_is_skipped(client):
    from app.jobs import health_job

    health_job._health_lock.acquire()
    try:
        assert scheduler.run_health_check() == {"status": "already_running"}
    finally:
        health_job._health_lock.release()


def test_heartbeat_reports_stale_background_jobs(client):
    with SessionLocal() as db:
        stale = JobRun(job_type="analyze", run_window="stale-test", status="running",
                       started_at=datetime.now(timezone.utc) - timedelta(hours=25))
        db.add(stale)
        db.commit()
        stale_id = stale.id

    scheduler._heartbeat()
    with SessionLocal() as db:
        heartbeat = db.scalar(select(JobRun).where(
            JobRun.job_type == "heartbeat",
        ).order_by(JobRun.started_at.desc()))
        assert heartbeat.status == "failed"
        assert heartbeat.stats["stale_jobs"] == [stale_id]
        assert stale_id in heartbeat.error


def test_job_status_exposes_last_error_and_next_run(client):
    with SessionLocal() as db:
        db.add(JobRun(job_type="crawl", run_window="20261020", status="failed",
                      error="boom", started_at=datetime.now(timezone.utc)))
        db.commit()
    body = client.get("/api/v1/jobs/status", headers={"X-Demo-Role": "admin"}).json()
    by_type = {item["job_type"]: item for item in body["jobs"]}
    assert by_type["crawl_all"]["last_run"]["error"] == "boom"
    assert by_type["crawl_all"]["next_run_at"] is not None
    assert by_type["analyze_pending"]["next_run_at"] == by_type["crawl_all"]["next_run_at"]
    assert "health_check" in by_type and "heartbeat" in by_type

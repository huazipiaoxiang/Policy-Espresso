"""数据源健康计算（06 §6）：每小时汇总成功率/新增条数，标记疑似改版与连续失败告警。

告警载体：source.health JSON（前端健康页展示）+ structlog 事件；站内/邮件通知在 Phase 3 分发层接入。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.db.models import Document, JobRun, Source
from app.db.session import SessionLocal

log = get_logger("jobs.health")
_health_lock = Lock()

_WINDOW = timedelta(days=7)


def compute_source_health(db, source: Source) -> dict:  # noqa: ANN001
    """计算单源近 7 天健康指标并回写 source.health。返回增量字段。"""
    now = datetime.now(timezone.utc)
    since = now - _WINDOW

    runs = db.scalars(
        select(JobRun).where(
            JobRun.source_id == source.id, JobRun.job_type == "crawl", JobRun.started_at >= since
        )
    ).all()
    total = len(runs)
    ok = sum(1 for r in runs if r.status == "ok")
    new_docs = db.scalar(
        select(func.count(Document.id)).where(
            Document.source_id == source.id, Document.fetched_at >= since
        )
    ) or 0
    total_docs = db.scalar(
        select(func.count(Document.id)).where(Document.source_id == source.id)
    ) or 0

    health = dict(source.health or {})
    health["success_rate_7d"] = round(ok / total, 3) if total else None
    health["new_docs_7d"] = new_docs
    health["checked_at"] = now.isoformat()

    alerts: list[str] = []
    consecutive_fail = int(health.get("consecutive_fail", 0))
    if consecutive_fail >= 3:
        alerts.append(f"连续失败 {consecutive_fail} 次")
    if new_docs == 0 and total_docs > 0:
        # 06 §6：7 天新增 0 条（而历史有产出）→ 疑似改版，最容易静默漏政策
        alerts.append("疑似改版：近 7 天新增 0 条")
    health["alerts"] = alerts
    source.health = health
    return {"alerts": alerts, "success_rate_7d": health["success_rate_7d"], "new_docs_7d": new_docs}


def run_health_check() -> dict:
    """每小时任务体：遍历启用源计算健康指标。"""
    if not _health_lock.acquire(blocking=False):
        log.info("health_check_skipped_already_running")
        return {"status": "already_running"}
    try:
        with SessionLocal() as db:
            job = JobRun(job_type="health", run_window=datetime.now(timezone.utc).strftime("%Y%m%d%H"),
                         status="running")
            db.add(job)
            db.commit()
            summary: dict[str, dict] = {}
            errors: list[str] = []
            try:
                sources = db.scalars(select(Source).where(Source.enabled.is_(True))).all()
                for src in sources:
                    try:
                        summary[src.code] = compute_source_health(db, src)
                        db.commit()
                        for alert in summary[src.code]["alerts"]:
                            log.warning("source_health_alert", source=src.code, alert=alert)
                    except Exception as exc:
                        db.rollback()
                        error = f"{src.code}: {type(exc).__name__}: {exc}"
                        errors.append(error)
                        summary[src.code] = {"alerts": [], "error": error}
                        log.error("source_health_check_failed", source=src.code, error=str(exc))
                job.status = "failed" if errors else "ok"
                job.stats = {"sources": len(sources), "succeeded": len(sources) - len(errors), "failed": len(errors)}
                job.error = "; ".join(errors[-3:]) or None
            except Exception as e:
                db.rollback()
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
                log.error("health_check_failed", error=str(e))
            finally:
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
            return summary
    finally:
        _health_lock.release()


if __name__ == "__main__":
    from app.core.logging import configure_logging

    configure_logging()
    for code, info in run_health_check().items():
        print(f"[{code}] {info}")

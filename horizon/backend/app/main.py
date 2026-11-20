"""HORIZON 政策雷达 — FastAPI 入口。"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    alerts, analytics, audit, auth, business_map, cases, chat, customers, documents, health, internal, jobs, policies, preprocess, review, settings, sources, stream, studio, users,
)
from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging, get_logger
from app.jobs.scheduler import build_scheduler, recover_interrupted_runs

configure_logging()
log = get_logger("app")


def seed_on_startup() -> dict[str, int]:
    """补齐启动种子数据（幂等）。

    与 `make seed` 保持一致：除数据源/案例/政策外，还要补客户经理账号和预处理记录。
    「为你推荐」只消费 policy_preprocess，漏掉这一步会导致云端有政策却无推荐。
    """
    from app.db.session import SessionLocal
    from app.jobs.seed_job import (
        seed_cases,
        seed_demo_subsidy_policy,
        seed_known_policies,
        seed_preprocess,
        seed_rm_users,
        seed_sources,
    )

    with SessionLocal() as db:
        return {
            "sources": seed_sources(db),
            "cases": seed_cases(db),
            "demo_policies": seed_demo_subsidy_policy(db),
            "known_policies": seed_known_policies(db),
            "users": seed_rm_users(db),
            "preprocess": seed_preprocess(db),
        }


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)  # 本地直跑兜底；生产走 alembic upgrade head
    # 测试环境通过 HORIZON_AUTO_SEED=0 关闭，避免与用例自造的数据冲突。
    seeded: dict[str, int] = {}
    if os.environ.get("HORIZON_AUTO_SEED", "1") != "0":
        seeded = seed_on_startup()
    recovered = recover_interrupted_runs()
    scheduler = build_scheduler()
    scheduler.start()
    log.info(
        "startup",
        llm_provider=get_settings().llm_provider,
        recovered_runs=recovered,
        seeded=seeded,
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="HORIZON 政策雷达", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(preprocess.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(business_map.router, prefix="/api/v1")
app.include_router(studio.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(internal.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")

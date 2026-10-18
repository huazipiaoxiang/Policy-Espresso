"""HORIZON 政策雷达 — FastAPI 入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    alerts, analytics, audit, business_map, cases, documents, health, internal, jobs, policies, review, settings, sources, stream, studio,
)
from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler
from app.core.logging import configure_logging, get_logger
from app.jobs.scheduler import build_scheduler

configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)  # 本地直跑兜底；生产走 alembic upgrade head
    scheduler = build_scheduler()
    scheduler.start()
    log.info("startup", llm_provider=get_settings().llm_provider)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="HORIZON 政策雷达", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(business_map.router, prefix="/api/v1")
app.include_router(studio.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(internal.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")

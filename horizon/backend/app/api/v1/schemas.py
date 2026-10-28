"""API v1 Pydantic Schema（与 docs/04 §4 契约一致）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


class SourceOut(BaseModel):
    id: str
    code: str
    name: str
    org: str
    jurisdiction: str
    tier: int
    adapter: str
    url: str
    lang: str
    poll_interval_min: int
    enabled: bool
    health: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class SourceCreate(BaseModel):
    code: str
    name: str
    org: str = ""
    jurisdiction: str
    tier: int = 1
    adapter: str
    url: str
    config: dict[str, Any] = Field(default_factory=dict)
    lang: str = "zh-Hant"
    poll_interval_min: int = 30


class SourcePatch(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    poll_interval_min: int | None = None


class PolicyOut(BaseModel):
    id: str
    document_id: str
    title: str
    url: str = ""
    issuing_body: str
    doc_number: str | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None
    expiry_at: datetime | None = None
    jurisdiction: str
    policy_type: str
    themes: list[str]
    applicable_entities_text: str = ""
    applicable_scope: str = "unclear"
    target_entity_status: str
    foreign_bank_differential: bool
    group_affiliate_mention: dict[str, Any] = Field(default_factory=dict)
    amounts: list[dict[str, Any]] = Field(default_factory=list)
    deadlines: list[dict[str, Any]] = Field(default_factory=list)
    obligations: list[dict[str, Any]] = Field(default_factory=list)
    incentives: list[dict[str, Any]] = Field(default_factory=list)
    summary_zh: str = ""
    confidence: float = 0.0
    status: str
    priority: str
    score_total: float
    prompt_version: str = ""
    impacted_domains: list[str] = Field(default_factory=list)
    review_completed_at: datetime | None = None
    dispatched_at: datetime | None = None

    model_config = {"from_attributes": True}


class AnalyticsOverview(BaseModel):
    today_new: int
    pending_review: int
    p0_p1_open: int
    avg_response_min: float | None
    sources_total: int
    sources_unhealthy: int
    last_crawl_at: datetime | None

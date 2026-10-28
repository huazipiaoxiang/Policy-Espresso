"""ORM 模型，与 docs/04_DATA_MODEL_API.md §2 一一对应。

枚举在 SQLite/PG 间保持可移植：DB 层存 String，合法值由 domain/ 与 Pydantic Schema 约束。
时间一律 UTC 存储；SQLite 读回为 naive，UTCDateTime 统一附加 UTC 时区。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) 的可移植实现：SQLite 读回 naive 时按 UTC 解释。"""

    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("s"))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    org: Mapped[str] = mapped_column(String(200), default="")
    jurisdiction: Mapped[str] = mapped_column(String(8))  # HK/GD/SZ/GBA/CN/MO
    tier: Mapped[int] = mapped_column(Integer, default=1)  # 1 官方/2 媒体/3 智库
    adapter: Mapped[str] = mapped_column(String(16))  # rss/sitemap/listing/pdf/manual
    url: Mapped[str] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    lang: Mapped[str] = mapped_column(String(16), default="zh-Hant")
    poll_interval_min: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[dict] = mapped_column(JSON, default=dict)

    documents: Mapped[list["Document"]] = relationship(back_populates="source")


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("j"))
    job_type: Mapped[str] = mapped_column(String(32))  # crawl/analyze/health/digest
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"), nullable=True)
    run_window: Mapped[str] = mapped_column(String(32), default="")  # 幂等键组成部分
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/ok/failed
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (Index("uq_jobrun_source_window", "source_id", "job_type", "run_window", unique=True),)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("d"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id"))
    url: Mapped[str] = mapped_column(String(2000))
    canonical_url: Mapped[str] = mapped_column(String(2000), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    lang: Mapped[str] = mapped_column(String(16), default="")
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    content_text: Mapped[str] = mapped_column(Text, default="")
    content_html_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    simhash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(32), default="news")
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new/processing/processed/failed/ignored
    duplicate_of: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[Source] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")
    policy: Mapped["Policy | None"] = relationship(back_populates="document", uselist=False)

    __table_args__ = (Index("idx_doc_source_pub", "source_id", "published_at"),)


class DocumentVersion(Base):
    __tablename__ = "document_version"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("dv"))
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    minor_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")


class Policy(Base):
    __tablename__ = "policy"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("p"))
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), unique=True)
    title: Mapped[str] = mapped_column(String(1000))
    issuing_body: Mapped[str] = mapped_column(String(500), default="")
    doc_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expiry_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String(8), default="")
    policy_type: Mapped[str] = mapped_column(String(32), default="press_release")
    themes: Mapped[list] = mapped_column(JSON, default=list)
    applicable_entities_text: Mapped[str] = mapped_column(Text, default="")
    applicable_scope: Mapped[str] = mapped_column(String(32), default="unclear")
    target_entity_status: Mapped[str] = mapped_column(String(32), default="not_mentioned")
    foreign_bank_differential: Mapped[bool] = mapped_column(Boolean, default=False)
    group_affiliate_mention: Mapped[dict] = mapped_column(JSON, default=dict)
    amounts: Mapped[list] = mapped_column(JSON, default=list)
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
    obligations: Mapped[list] = mapped_column(JSON, default=list)
    incentives: Mapped[list] = mapped_column(JSON, default=list)
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    score_total: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_version: Mapped[str] = mapped_column(String(64), default="")

    document: Mapped[Document] = relationship(back_populates="policy")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="policy")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="policy")

    __table_args__ = (
        Index("idx_policy_status_priority", "status", "priority"),
        Index("idx_policy_published", "published_at"),
    )


class Assessment(Base):
    __tablename__ = "assessment"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("a"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy.id"), index=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)  # 8 维：{score, reason, evidence_ids}
    direction: Mapped[str] = mapped_column(String(16), default="neutral")  # positive/negative/mixed/neutral
    score_total: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(4), default="P3")
    transmission_chain: Mapped[list] = mapped_column(JSON, default=list)
    affected: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    case_links: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    policy: Mapped[Policy] = relationship(back_populates="assessments")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("e"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy.id"), index=True)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessment.id"), nullable=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"))
    span_start: Mapped[int] = mapped_column(Integer)
    span_end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    field_name: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    policy: Mapped[Policy] = relationship(back_populates="evidence_items")

    __table_args__ = (Index("idx_evidence_policy", "policy_id"),)


class ScopeJudgement(Base):
    __tablename__ = "scope_judgement"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("sj"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy.id"), index=True)
    entity_id: Mapped[str] = mapped_column(String(32))  # hsbc_hk / hsbc_cn
    result: Mapped[str] = mapped_column(String(24))  # high/medium/low/not_mentioned/na
    rule_hits: Mapped[list] = mapped_column(JSON, default=list)
    llm_reason: Mapped[str] = mapped_column(Text, default="")
    conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Case(Base):
    __tablename__ = "case"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("c"))
    title: Mapped[str] = mapped_column(String(500))
    year: Mapped[int] = mapped_column(Integer)
    jurisdiction: Mapped[str] = mapped_column(String(8), default="")
    themes: Mapped[list] = mapped_column(JSON, default=list)
    policy_summary: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    hsbc_response: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(String(24), default="")  # win/lose/partial
    lessons: Mapped[list] = mapped_column(JSON, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # pgvector（PG）/ NULL（SQLite 降级）


class PolicyCaseLink(Base):
    __tablename__ = "policy_case_link"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("pcl"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id"), index=True)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)


class ReviewTask(Base):
    __tablename__ = "review_task"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("rt"))
    policy_id: Mapped[str] = mapped_column(ForeignKey("policy.id"), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)  # 1 分析师 / 2 合规或业务主管
    assignee: Mapped[str] = mapped_column(String(64), default="")
    sla_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")  # pending/claimed/approved/rejected/needs_info
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="task")


class ReviewDecision(Base):
    __tablename__ = "review_decision"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("rd"))
    task_id: Mapped[str] = mapped_column(ForeignKey("review_task.id"), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # approve/reject/request_info
    reason_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    field_diffs: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    task: Mapped[ReviewTask] = relationship(back_populates="decisions")


class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("al"))
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    body_md: Mapped[str] = mapped_column(Text, default="")
    channel_scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft/approved/sent
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Dispatch(Base):
    __tablename__ = "dispatch"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("dp"))
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))  # inapp/email/wecom/feishu/teams
    target: Mapped[str] = mapped_column(String(200), default="")
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class StudioProject(Base):
    __tablename__ = "studio_project"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("sp"))
    name: Mapped[str] = mapped_column(String(200))
    theme: Mapped[str] = mapped_column(String(64), default="")
    corpus_doc_ids: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Proposal(Base):
    __tablename__ = "proposal"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("pr"))
    project_id: Mapped[str] = mapped_column(ForeignKey("studio_project.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[list] = mapped_column(JSON, default=list)  # 5 段结构建议
    boundary_check: Mapped[dict] = mapped_column(JSON, default=dict)  # pass/warn/fail
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("au"))
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(32))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (Index("idx_audit_object", "object_type", "object_id", "at"),)


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("llm"))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

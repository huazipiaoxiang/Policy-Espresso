"""政策流水线 Agent：权限模型（除数据外泄外全开）与预处理 Agent 的降级/接管行为。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.agent.permissions import EGRESS, ToolPermissionError, check_tool_permission, sanitize_public_query
from app.ai.provider import LLMResult
from app.db.models import Assessment, Document, Policy, Source
from app.db.session import SessionLocal


class _FakeProvider:
    """可编排的生成式 provider：按顺序回放预设的 Agent 决策。"""

    name = "fake-llm"

    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, *, system: str, user: str, schema: dict | None, **kwargs) -> LLMResult:  # noqa: ANN003
        payload = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return LLMResult(text=json.dumps(payload, ensure_ascii=False), parsed=payload, model="fake-model")

    def complete_messages(self, **kwargs):  # noqa: ANN003
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []


def _make_policy(business_lines: list[str] | None = None) -> str:
    with SessionLocal() as db:
        source = Source(code="t_pre_agent", name="t", jurisdiction="HK", adapter="manual", url="https://t")
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url="https://t/pre-agent",
            canonical_url="https://t/pre-agent",
            title="小额贷款贴息政策",
            content_hash="h_pre_agent",
            content_text="为支持中小微企业，对符合条件的贷款给予贴息支持，鼓励银行加大信贷投放。",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title="小额贷款贴息政策",
            status="published",
            priority="P2",
            jurisdiction="HK",
            themes=["贷款与贴息"],
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={},
            direction="positive",
            score_total=55,
            priority="P2",
            affected={"business_lines": business_lines or ["CIB"], "segments": []},
            recommended_actions=[],
            confidence=0.6,
            model="offline-rules",
        ))
        db.commit()
        return policy.id


def test_egress_capability_is_denied():
    with pytest.raises(ToolPermissionError):
        check_tool_permission("send_customer_file", frozenset({EGRESS}))


def test_public_query_blocks_internal_data():
    query, reason = sanitize_public_query(
        "customer_id p_123 敞口金额 内部评分",
        allowed_texts=["小额贷款贴息政策"],
    )
    assert query is None
    assert "数据外泄" in reason

    allowed, reason_ok = sanitize_public_query(
        "小额贷款 贴息 政策 银行 新闻",
        allowed_texts=["小额贷款贴息政策"],
    )
    assert allowed and not reason_ok


def test_preprocess_agent_runs_without_llm(client, monkeypatch):
    """provider=mock 时退回规则，并写清「除数据外泄外全开」的权限说明。"""
    from app.domain.preprocess import upsert_preprocess

    policy_id = _make_policy()
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        record = upsert_preprocess(db, policy, use_agent=True)
        db.commit()
        db.refresh(record)
        agent = (record.extras or {}).get("agent") or {}
        assert agent["mode"] == "rules"
        assert agent["permissions"]["denied"] == ["egress"]
        assert "read" in agent["permissions"]["granted"]


def test_preprocess_agent_refines_keywords_and_business_lines(client, monkeypatch):
    from app.domain.preprocess import upsert_preprocess

    fake = _FakeProvider([
        {"action": "call_tool", "tool": "read_policy", "args": {}},
        {"action": "call_tool", "tool": "compute_percentages", "args": {"business_line_codes": ["GTB"]}},
        {
            "action": "finish",
            "plan": {
                "keywords": ["跨境结算", "出海企业"],
                "business_line_codes": ["GTB"],
                "customer_segments": [],
                "summary": "政策主要影响跨境结算与出海企业客户。",
                "notes": ["已核对原文"],
            },
        },
    ])
    monkeypatch.setattr("app.agent.runner.get_provider", lambda: fake)

    policy_id = _make_policy()
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        record = upsert_preprocess(db, policy, use_agent=True)
        db.commit()
        db.refresh(record)

        agent = (record.extras or {}).get("agent") or {}
        assert agent["mode"] == "agent"
        assert agent["model"] == "fake-model"
        assert "read_policy" in agent["tools"]
        assert "跨境结算" in record.keywords
        assert [line["code"] for line in record.affected_business] == ["GTB"]
        assert record.source.startswith("agent:")


def test_preprocess_agent_records_blocked_egress(client, monkeypatch):
    from app.domain.preprocess import upsert_preprocess

    fake = _FakeProvider([
        {
            "action": "call_tool",
            "tool": "search_public_web",
            "args": {"query": "customer_id p_123 敞口金额"},
        },
        {
            "action": "finish",
            "plan": {
                "keywords": ["贴息"],
                "business_line_codes": ["CIB"],
                "customer_segments": [],
                "summary": "按规则口径完成预处理。",
                "notes": [],
            },
        },
    ])
    monkeypatch.setattr("app.agent.runner.get_provider", lambda: fake)

    policy_id = _make_policy()
    with SessionLocal() as db:
        policy = db.get(Policy, policy_id)
        record = upsert_preprocess(db, policy, use_agent=True)
        db.commit()
        db.refresh(record)

        agent = (record.extras or {}).get("agent") or {}
        assert agent["blocked"], "内部数据检索词必须被出网策略拦截并留痕"
        assert agent["blocked"][0]["tool"] == "search_public_web"

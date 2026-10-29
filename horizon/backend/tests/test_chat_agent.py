"""Chat Agent（LLM 自主检索）的行为契约测试。

覆盖：工具白名单与角色可见性、参数 clamp、轮次上限与早停、重复调用去重、
模型不可解析时的规则回退、放宽后的分层引用语义（不得凭空造 id）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ai.provider import LLMResult
from app.ai.providers.mock import MockProvider
from app.chat.agent import run_agent
from app.chat.planner import build_plan, rule_plan
from app.chat.schemas import ChatPlan
from app.chat.service import generate_agent_chat
from app.chat.tool_registry import DEFAULT_LIMIT, clamp_limit, clamp_query, describe_tools, run_tool
from app.chat.tools import ChatTools
from app.db.models import Base, Document, Policy, ReviewTask, Source

DEFAULT_PLAN = {
    "standalone_question": "《虚拟银行监管新规》的发布机构是谁？",
    "intent": "lookup",
    "queries": ["虚拟银行监管新规", "虚拟银行 监管"],
    "needs_web": False,
}
DEFAULT_ANSWER = {
    "reply": "该政策由示例监管机构发布。",
    "answer_mode": "grounded",
    "citation_ids": [],
    "followups": ["它的生效日期是什么？"],
    "clarifying_question": None,
}


class ScriptedProvider:
    """按脚本返回 parsed。

    plan 为 None 时表示「没有 Planner」（直接调 run_agent 的场景），chat_plan 一律按
    Executor 处理；plan 非 None 时第 1 次 chat_plan 返回规划、其后返回 Executor 步骤。
    """

    def __init__(self, *, plan=None, steps=None, answer=None, fail_plan=False):
        self.name = "scripted"
        self.plan = plan
        self.steps = list(steps or [])
        self.answer = answer if answer is not None else dict(DEFAULT_ANSWER)
        self.fail_plan = fail_plan
        self.plan_calls = 0
        self.tasks: list[str] = []
        self.prompts: list[str] = []

    def _result(self, parsed: dict) -> LLMResult:
        return LLMResult(text="", parsed=parsed, model="scripted")

    def complete(self, *, system, user, schema=None, temperature=0.1, max_tokens=4096, model=None, task=""):
        return self.complete_messages(
            system=system, messages=[{"role": "user", "content": user}], schema=schema,
            temperature=temperature, max_tokens=max_tokens, model=model, task=task,
        )

    def complete_messages(self, *, system, messages, schema=None, temperature=0.1,
                          max_tokens=4096, model=None, task=""):
        self.tasks.append(task)
        self.prompts.append("\n".join(str(message.get("content") or "") for message in messages))
        if task == "chat_answer":
            return self._result(self.answer)
        if task == "chat_plan":
            self.plan_calls += 1
            if self.fail_plan:
                raise RuntimeError("planner down")
            if self.plan is not None and self.plan_calls == 1:
                return self._result(self.plan)
            return self._result(self.steps.pop(0) if self.steps else {"action": "finish"})
        return self._result({})


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_policy(db: Session, *, title: str = "虚拟银行监管新规", summary: str = "要求持牌机构建立风险管控。",
               status: str = "published") -> Policy:
    source = db.scalar(select(Source).where(Source.code == "regulator"))
    if source is None:
        source = Source(id="s_regulator", code="regulator", name="示例监管机构", org="示例监管机构",
                        jurisdiction="HK", tier=1, adapter="manual", url="https://regulator.example/",
                        config={"secret": "must-not-be-exposed"})
        db.add(source)
        db.flush()
    suffix = str(db.scalar(select(func.count(Policy.id))) or 0)
    document = Document(
        id=f"d_{suffix}", source_id=source.id, url=f"https://regulator.example/policies/{suffix}",
        canonical_url=f"https://regulator.example/policies/{suffix}", title=title,
        content_text=f"{title} 原文", content_hash=f"hash-{suffix}",
        published_at=datetime.now(timezone.utc),
    )
    policy = Policy(id=f"p_{suffix}", document=document, title=title, issuing_body="示例监管机构",
                    summary_zh=summary, status=status)
    db.add_all([document, policy])
    db.commit()
    return policy


def make_plan(question: str = "《虚拟银行监管新规》的发布机构是谁？") -> ChatPlan:
    return ChatPlan(standalone_question=question, intent="lookup", queries=[question], source="rule")


# ---------- 工具注册表 ----------


def test_tool_list_hides_privileged_tools_from_consumer():
    consumer = describe_tools("consumer")
    analyst = describe_tools("analyst")
    assert "search_reviews" not in consumer
    assert "search_business_impacts" not in consumer
    assert "search_reviews" in analyst
    assert "search_business_impacts" in analyst


def test_run_tool_rejects_unknown_and_denied_tools(db):
    add_policy(db)
    tools = ChatTools(db, "consumer")
    evidence, note = run_tool(tools, "consumer", "drop_everything", {"query": "x"})
    assert evidence == [] and "未知工具" in note

    db.add(ReviewTask(id="rt_1", policy_id="p_0", assignee="someone"))
    db.commit()
    evidence, note = run_tool(tools, "consumer", "search_reviews", {"query": "待办"})
    assert evidence == [] and "不可用" in note


def test_tool_args_are_clamped():
    assert len(clamp_query("政" * 500)) == 200
    assert clamp_query(None) == ""
    assert clamp_limit(999) == 8
    assert clamp_limit(0) == 1
    assert clamp_limit("abc") == DEFAULT_LIMIT


def test_injection_attempt_is_treated_as_text_not_sql(db):
    add_policy(db)
    tools = ChatTools(db, "analyst")
    evidence, _ = run_tool(tools, "analyst", "search_policies", {"query": "'); DROP TABLE policy; --"})
    assert evidence == []
    assert db.scalar(select(func.count(Policy.id))) == 1


# ---------- Planner ----------


def test_planner_uses_model_output_when_parsable():
    provider = ScriptedProvider(plan={"standalone_question": "虚拟银行监管新规 发布机构",
                                      "intent": "lookup", "queries": ["虚拟银行监管新规"], "needs_web": False})
    plan = build_plan(provider=provider, question="它是什么时候发的？", history=[{"role": "user", "content": "虚拟银行监管新规"}])
    assert plan.source == "llm"
    assert plan.standalone_question == "虚拟银行监管新规 发布机构"
    assert plan.queries == ["虚拟银行监管新规"]


def test_planner_falls_back_to_rule_when_model_fails():
    provider = ScriptedProvider(fail_plan=True)
    plan = build_plan(provider=provider, question="火星金融监管局发布了什么？")
    assert plan == rule_plan("火星金融监管局发布了什么？")
    assert plan.source == "rule"


def test_planner_rejects_empty_standalone_question():
    provider = ScriptedProvider(plan={"standalone_question": "", "intent": "lookup", "queries": [], "needs_web": False})
    plan = build_plan(provider=provider, question="原问题")
    assert plan.source == "rule" and plan.standalone_question == "原问题"


def test_mock_provider_never_plans():
    plan = build_plan(provider=MockProvider(), question="虚拟银行监管新规")
    assert plan.source == "rule"


# ---------- Executor 循环 ----------


def test_agent_calls_model_selected_tools_and_records_steps(db):
    policy = add_policy(db)
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "search_policies", "query": "虚拟银行监管新规", "limit": 5},
        {"action": "call_tool", "tool": "search_documents", "query": "虚拟银行 原文", "limit": 3},
        {"action": "finish", "reason": "enough"},
    ])
    run = run_agent(tools=ChatTools(db, "analyst"), provider=provider, role="analyst", plan=make_plan())
    assert [step.tool for step in run.steps] == ["search_policies", "search_documents"]
    assert run.stop_reason == "model_finish"
    assert any(item.key == f"policy:{policy.id}" for item in run.evidence)


def test_unknown_tool_observation_does_not_break_the_loop(db):
    add_policy(db)
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "not_a_tool", "query": "任意"},
        {"action": "call_tool", "tool": "search_policies", "query": "虚拟银行", "limit": 5},
        {"action": "finish"},
    ])
    run = run_agent(tools=ChatTools(db, "analyst"), provider=provider, role="analyst", plan=make_plan())
    assert run.steps[0].hits == 0 and "未知工具" in run.steps[0].note
    assert run.evidence, "遇到未知工具后应继续用合法工具拿到证据"


def test_repeated_call_is_skipped_and_stops_early(db):
    add_policy(db)
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "search_policies", "query": "虚拟银行监管新规", "limit": 5},
        {"action": "call_tool", "tool": "search_policies", "query": "虚拟银行监管新规", "limit": 5},
        {"action": "call_tool", "tool": "search_policies", "query": "虚拟银行监管新规", "limit": 5},
    ])
    run = run_agent(tools=ChatTools(db, "analyst"), provider=provider, role="analyst", plan=make_plan())
    # 同一 (tool, query) 只真正执行一次；连续两次无效后早停，不再空转。
    assert [step.hits for step in run.steps] == [1, 0, 0]
    assert "重复调用" in run.steps[-1].note
    assert len(run.evidence) == 1
    assert run.stop_reason == "repeated_calls"


def test_unparsable_steps_stop_after_budget(db, monkeypatch):
    add_policy(db)
    monkeypatch.setattr("app.chat.agent.get_settings", lambda: SimpleNamespace(
        chat_max_tool_rounds=3, chat_max_invalid_calls=2, chat_evidence_max=8,
        model_for_task=lambda task: "m",
    ))

    class BrokenProvider:
        name = "broken"

        def complete_messages(self, **kwargs):
            return LLMResult(text="not json", parsed=None, model="broken")

        def complete(self, **kwargs):
            return self.complete_messages(**kwargs)

    run = run_agent(tools=ChatTools(db, "analyst"), provider=BrokenProvider(), role="analyst", plan=make_plan())
    assert run.stop_reason == "unparsable_output"
    assert run.steps and run.steps[0].note == "fallback", "全失败时要保底检索一次而不是空手作答"


def test_evidence_budget_is_enforced(db, monkeypatch):
    for index in range(6):
        add_policy(db, title=f"政策 {index}", summary=f"摘要 {index}")
    monkeypatch.setattr("app.chat.agent.get_settings", lambda: SimpleNamespace(
        chat_max_tool_rounds=5, chat_max_invalid_calls=3, chat_evidence_max=2,
        model_for_task=lambda task: "m",
    ))
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "search_policies", "query": "政策", "limit": 8},
        {"action": "call_tool", "tool": "search_documents", "query": "政策", "limit": 8},
        {"action": "finish"},
    ])
    run = run_agent(tools=ChatTools(db, "analyst"), provider=provider, role="analyst", plan=make_plan("政策"))
    assert len(run.evidence) <= 2


def test_consumer_never_gets_review_evidence_through_agent(db):
    policy = add_policy(db)
    db.add(ReviewTask(id="rt_1", policy_id=policy.id, assignee="analyst.one"))
    db.commit()
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "search_reviews", "query": "待办", "limit": 5},
        {"action": "finish"},
    ])
    run = run_agent(tools=ChatTools(db, "consumer"), provider=provider, role="consumer", plan=make_plan("待办"))
    assert run.evidence == []
    assert "不可用" in run.steps[0].note


def test_mock_provider_uses_deterministic_retrieval(db):
    policy = add_policy(db)
    run = run_agent(tools=ChatTools(db, "analyst"), provider=MockProvider(), role="analyst", plan=make_plan())
    assert run.stop_reason == "deterministic_provider"
    assert any(item.key == f"policy:{policy.id}" for item in run.evidence)


# ---------- 端到端与引用语义 ----------


def test_agent_answer_keeps_valid_citations_and_followups(db):
    policy = add_policy(db)
    provider = ScriptedProvider(
        plan=dict(DEFAULT_PLAN),
        steps=[{"action": "call_tool", "tool": "search_policies", "query": "虚拟银行监管新规", "limit": 5},
               {"action": "finish"}],
        answer={"reply": "由示例监管机构发布。", "answer_mode": "grounded",
                "citation_ids": [f"policy:{policy.id}"], "followups": ["生效日期？"], "clarifying_question": None},
    )
    result = generate_agent_chat(tools=ChatTools(db, "analyst"), provider=provider, question="发布机构是谁？")
    assert result.no_answer is False
    assert result.answer_mode == "grounded"
    assert result.citations[0]["policy_id"] == policy.id
    assert result.followups == ["生效日期？"]
    assert result.steps and result.steps[0].hits == 1


def test_hallucinated_citation_ids_are_dropped(db):
    add_policy(db)
    provider = ScriptedProvider(answer={"reply": "据称由某机构发布。", "answer_mode": "grounded",
                                        "citation_ids": ["policy:does-not-exist"], "followups": []})
    result = generate_agent_chat(tools=ChatTools(db, "analyst"), provider=provider, question="发布机构是谁？")
    assert result.citations == []


def test_general_answer_without_evidence_is_allowed(db):
    """放宽后的关键差异：没有证据也可以回答（general），只要不编造文号/日期。"""
    provider = ScriptedProvider(plan=dict(DEFAULT_PLAN), steps=[{"action": "finish"}],
                                answer={"reply": "这是通用概念解释。", "answer_mode": "general",
                                        "citation_ids": [], "followups": []})
    result = generate_agent_chat(tools=ChatTools(db, "analyst"), provider=provider, question="什么是监管沙盒？")
    assert result.answer_mode == "general"
    assert result.citations == []
    assert result.no_answer is False


def test_answer_failure_falls_back_to_extractive_evidence(db):
    policy = add_policy(db)

    class NoAnswerProvider(ScriptedProvider):
        def complete_messages(self, *, system, messages, schema=None, temperature=0.1,
                              max_tokens=4096, model=None, task=""):
            self.tasks.append(task)
            if task == "chat_answer":
                return LLMResult(text="", parsed=None, model="scripted")
            return super().complete_messages(
                system=system, messages=messages, schema=schema, temperature=temperature,
                max_tokens=max_tokens, model=model, task=task,
            )

    provider = NoAnswerProvider(plan=dict(DEFAULT_PLAN),
                                steps=[{"action": "call_tool", "tool": "search_policies",
                                        "query": "虚拟银行监管新规", "limit": 5}, {"action": "finish"}])
    result = generate_agent_chat(tools=ChatTools(db, "analyst"), provider=provider, question="发布机构是谁？")
    assert result.model == "agent-extractive"
    assert "要求持牌机构建立风险管控" in result.reply
    assert result.citations[0]["policy_id"] == policy.id


def test_chat_endpoint_switches_between_paths(client, monkeypatch):
    """开关关闭时走冻结的 grounded 路径（无 steps），开启时走 agent 路径（有 steps）。"""
    from app.core.config import Settings, get_settings
    from app.db.models import Document, Policy, Source
    from app.db.session import SessionLocal
    from app.main import app

    with SessionLocal() as session:
        source = Source(id="s_api", code="api-regulator", name="接口示例监管机构", org="接口示例监管机构",
                        jurisdiction="HK", tier=1, adapter="manual", url="https://api.example/")
        document = Document(id="d_api", source_id="s_api", url="https://api.example/1",
                            canonical_url="https://api.example/1", title="接口政策",
                            content_text="接口政策原文", content_hash="hash-api")
        session.add_all([source, document, Policy(id="p_api", document=document, title="接口政策",
                                                  issuing_body="接口示例监管机构",
                                                  summary_zh="接口政策摘要内容。", status="published")])
        session.commit()

    agent_settings = Settings(chat_agent_enabled=True)
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: agent_settings)
    agent_response = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "接口政策"}]})
    assert agent_response.status_code == 200
    agent_body = agent_response.json()
    assert agent_body["steps"], "agent 路径必须回传检索过程"
    assert agent_body["answer_mode"] == "grounded"
    assert agent_body["citations"][0]["policy_id"] == "p_api"

    monkeypatch.delitem(app.dependency_overrides, get_settings)
    grounded_response = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "接口政策"}]})
    assert grounded_response.status_code == 200
    grounded_body = grounded_response.json()
    assert grounded_body["steps"] == []
    assert grounded_body["citations"][0]["policy_id"] == "p_api"


def test_history_is_passed_to_planner(db):
    add_policy(db)
    provider = ScriptedProvider(plan=dict(DEFAULT_PLAN), steps=[{"action": "finish"}])
    history = [{"role": "user", "content": "虚拟银行监管新规是什么？"},
               {"role": "assistant", "content": "它是一条示例政策。"},
               {"role": "user", "content": "它什么时候发布的？"}]
    plan = build_plan(provider=provider, question="它什么时候发布的？", history=history)
    assert plan.source == "llm"
    assert plan.standalone_question == DEFAULT_PLAN["standalone_question"]
    assert "它是一条示例政策。" in provider.prompts[0], "多轮历史必须进入 Planner 提示词才能消解指代"

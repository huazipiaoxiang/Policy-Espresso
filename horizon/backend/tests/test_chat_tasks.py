"""Chat 管理员任务：权限、确认闸门、确定性门禁与影响报告。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.ai.provider import LLMResult
from app.chat.agent import run_agent
from app.chat.schemas import ChatPlan
from app.chat.tool_registry import describe_tools, run_tool
from app.chat.tools import ChatTools
from app.db.models import Assessment, AuditLog, Document, Policy, Source, new_id
from app.db.session import SessionLocal

TASK_TOOLS = ("list_cleanup_candidates", "cleanup_policies", "build_impact_report")


class ScriptedProvider:
    """按脚本回放 Executor 决策；chat_answer 返回固定回答。"""

    name = "scripted"

    def __init__(self, steps: list[dict]):
        self.steps = list(steps)
        self.answer = {
            "reply": "已按你的确认完成清理。",
            "answer_mode": "grounded",
            "citation_ids": [],
            "followups": [],
            "clarifying_question": None,
        }

    def _result(self, parsed: dict) -> LLMResult:
        return LLMResult(text="", parsed=parsed, model="scripted")

    def complete_messages(self, *, system, messages, schema=None, **kwargs):  # noqa: ANN003
        if kwargs.get("task") == "chat_answer":
            return self._result(self.answer)
        return self._result(self.steps.pop(0) if self.steps else {"action": "finish"})

    def complete(self, *, system, user, schema=None, **kwargs):  # noqa: ANN003
        return self.complete_messages(system=system, messages=[{"role": "user", "content": user}], **kwargs)


def _make_policy(*, relevant: bool = False, status: str = "analyzed") -> dict[str, str]:
    with SessionLocal() as db:
        source = Source(
            code=new_id("t_chat_task"), name="t", jurisdiction="HK",
            adapter="manual", url=f"https://t/{new_id('s')}",
        )
        db.add(source)
        db.flush()
        doc = Document(
            source_id=source.id,
            url=f"https://t/{new_id('u')}",
            canonical_url=f"https://t/{new_id('c')}",
            title="境外再保险监管指引",
            content_hash=new_id("h"),
            content_text="对境外再保险机构的资本充足与信息披露作出规定，适用于再保险机构。",
        )
        db.add(doc)
        db.flush()
        policy = Policy(
            document_id=doc.id,
            title=f"再保险指引 {new_id('t')}",
            status=status,
            priority="P2" if relevant else "P3",
            jurisdiction="SG",
            published_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
        db.add(Assessment(
            policy_id=policy.id,
            scores={"relevance": 3, "compliance": 2, "differential": 1} if relevant else {},
            direction="neutral",
            score_total=45 if relevant else 4,
            priority="P2" if relevant else "P3",
            affected={"business_lines": ["CIB"] if relevant else []},
            recommended_actions=[],
            confidence=0.6,
            model="offline-rules",
        ))
        db.commit()
        return {"policy_id": policy.id, "document_id": doc.id}


def _tools(role: str, question: str = "") -> ChatTools:
    return ChatTools(SessionLocal(), role, question=question, actor=f"demo.{role}")


# ---------- 可见性 ----------


def test_task_tools_are_admin_only():
    admin = describe_tools("admin")
    for name in TASK_TOOLS:
        assert name in admin
    for role in ("consumer", "processor"):
        listing = describe_tools(role)
        assert all(name not in listing for name in TASK_TOOLS)


def test_non_admin_call_is_denied(client):
    ids = _make_policy()
    tools = _tools("processor", question="确认清理这些政策")
    try:
        evidence, note = run_tool(
            tools, "processor", "cleanup_policies",
            {"policy_ids": [ids["policy_id"]], "confirm": True},
        )
    finally:
        tools.db.close()
    assert evidence == []
    assert "不可用" in note
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


# ---------- 确认闸门 ----------


def test_cleanup_refused_without_confirm_flag(client):
    ids = _make_policy()
    tools = _tools("admin", question="确认清理这些政策")
    try:
        evidence, _ = run_tool(
            tools, "admin", "cleanup_policies", {"policy_ids": [ids["policy_id"]]},
        )
    finally:
        tools.db.close()
    assert "confirm=true" in evidence[0].text
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_refused_when_user_did_not_confirm(client):
    """模型自说自话不算确认：用户本轮没写确认语就必须拒绝。"""
    ids = _make_policy()
    tools = _tools("admin", question="帮我看看有哪些政策可以清理")
    try:
        evidence, _ = run_tool(
            tools, "admin", "cleanup_policies",
            {"policy_ids": [ids["policy_id"]], "confirm": True},
        )
    finally:
        tools.db.close()
    assert "拒绝执行" in evidence[0].text
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_refused_for_asking_about_confirmation(client):
    """「确认一下有哪些政策可以清理」是在问清单，不是授权删除。"""
    ids = _make_policy()
    tools = _tools("admin", question="确认一下有哪些政策可以清理")
    try:
        evidence, _ = run_tool(
            tools, "admin", "cleanup_policies",
            {"policy_ids": [ids["policy_id"]], "confirm": True},
        )
    finally:
        tools.db.close()
    assert "拒绝执行" in evidence[0].text
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


# ---------- 执行 ----------


def test_cleanup_executes_with_gate_and_writes_audit(client):
    ids = _make_policy()
    tools = _tools("admin", question="确认清理这些政策")
    try:
        evidence, note = run_tool(
            tools, "admin", "cleanup_policies",
            {"policy_ids": [ids["policy_id"]], "confirm": True},
        )
    finally:
        tools.db.close()
    assert note == ""
    assert "已删除 1 条" in evidence[0].text
    assert evidence[0].kind == "task"
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is None
        assert db.get(Document, ids["document_id"]) is None
        actions = set(db.scalars(
            select(AuditLog.action).where(
                AuditLog.object_id.in_([ids["policy_id"], ids["document_id"]])
            )
        ))
    assert {"delete_policy", "delete_document"} <= actions


def test_cleanup_keeps_policy_failing_deterministic_gate(client):
    ids = _make_policy(relevant=True)
    tools = _tools("admin", question="确认清理这些政策")
    try:
        evidence, _ = run_tool(
            tools, "admin", "cleanup_policies",
            {"policy_ids": [ids["policy_id"]], "confirm": True},
        )
    finally:
        tools.db.close()
    assert "保留 1 条" in evidence[0].text
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_cleanup_candidates_only_lists_gate_passed_policies(client):
    irrelevant = _make_policy()
    relevant = _make_policy(relevant=True)
    tools = _tools("admin")
    try:
        evidence, _ = run_tool(tools, "admin", "list_cleanup_candidates", {"limit": 8})
    finally:
        tools.db.close()
    text = evidence[0].text
    assert irrelevant["policy_id"] in text
    assert relevant["policy_id"] not in text


# ---------- 影响报告 ----------


def test_build_impact_report_returns_policy_numbers(client):
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    tools = _tools("admin")
    try:
        evidence, _ = run_tool(tools, "admin", "build_impact_report", {"query": title})
    finally:
        tools.db.close()
    text = evidence[0].text
    assert "已生成" in text
    assert title in text
    assert "受影响客户" in text


def test_build_impact_report_unknown_policy_asks_for_clarification(client):
    tools = _tools("admin")
    try:
        evidence, _ = run_tool(tools, "admin", "build_impact_report", {"query": "不存在的政策标题"})
    finally:
        tools.db.close()
    assert "没有找到" in evidence[0].text


# ---------- HTTP：Agent 开关关闭时也能执行任务 ----------


def _ask(client, content: str, role: str = "admin"):
    return client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": content}]},
        headers={"X-Demo-Role": role},
    )


def test_chat_lists_cleanup_candidates_for_admin(client):
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    response = _ask(client, "有哪些无关政策可以清理")
    assert response.status_code == 200
    body = response.json()
    assert title in body["reply"]
    assert "确认清理" in body["reply"]
    assert [c["type"] for c in body["citations"]] == ["task"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_requires_confirmation_before_cleanup(client):
    ids = _make_policy()
    response = _ask(client, "确认一下有哪些政策可以清理")
    assert response.status_code == 200
    assert "确认清理" in response.json()["reply"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_executes_cleanup_after_confirmation(client):
    ids = _make_policy()
    response = _ask(client, "确认清理这些无关政策")
    assert response.status_code == 200
    assert "已删除" in response.json()["reply"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is None
        assert db.get(Document, ids["document_id"]) is None


def test_chat_consumer_cannot_trigger_cleanup(client):
    ids = _make_policy()
    response = _ask(client, "确认清理这些无关政策", role="consumer")
    assert response.status_code == 200
    assert "已删除" not in response.json()["reply"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_answers_whether_any_policy_has_no_hsbc_impact(client):
    """「系统里有没有不影响汇丰的政策」应给候选清单，而不是检索两条政策。"""
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    response = _ask(client, "现在系统有不影响汇丰的政策吗？")
    assert response.status_code == 200
    body = response.json()
    assert "对汇丰完全没有影响" in body["reply"]
    assert title in body["reply"]
    assert [c["type"] for c in body["citations"]] == ["task"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_says_none_when_no_policy_is_irrelevant(client):
    response = _ask(client, "现在系统有不影响汇丰的政策吗？")
    assert response.status_code == 200
    assert "当前没有对汇丰完全没有影响的政策" in response.json()["reply"]


def test_chat_specific_policy_impact_question_is_not_hijacked(client):
    """「这条政策不影响汇丰吗」问的是具体一条，不该回全库清单。"""
    response = _ask(client, "这条政策不影响汇丰吗？")
    assert response.status_code == 200
    assert "确认清理" not in response.json()["reply"]


def test_chat_does_not_hijack_normal_policy_questions(client):
    """「删除个人数据的政策」讲的是政策内容，不该被当成清理指令。"""
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    response = _ask(client, "有没有关于删除个人数据的政策")
    assert response.status_code == 200
    assert title not in response.json()["reply"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_refuses_deleting_named_policy(client):
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    response = _ask(client, f"确认删除《{title}》政策")
    assert response.status_code == 200
    assert "不按标题直接删除" in response.json()["reply"]
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is not None


def test_chat_builds_impact_report_for_admin(client):
    ids = _make_policy()
    with SessionLocal() as db:
        title = db.get(Policy, ids["policy_id"]).title
    response = _ask(client, f"帮我生成《{title}》的影响报告")
    assert response.status_code == 200
    body = response.json()
    assert title in body["reply"]
    assert "受影响客户" in body["reply"]


# ---------- 能力探测 ----------


def test_chat_capabilities_reports_rules_mode_without_llm(client):
    response = client.get("/api/v1/chat/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "rules"
    assert body["llm_ready"] is False
    assert body["admin_tasks"] is False  # 默认 processor

    admin = client.get("/api/v1/chat/capabilities", headers={"X-Demo-Role": "admin"}).json()
    assert admin["admin_tasks"] is True
    assert admin["hint"]


# ---------- Agent 循环 ----------


def test_admin_agent_runs_cleanup_task_end_to_end(client):
    ids = _make_policy()
    provider = ScriptedProvider(steps=[
        {"action": "call_tool", "tool": "list_cleanup_candidates", "limit": 5},
        {
            "action": "call_tool", "tool": "cleanup_policies",
            "policy_ids": [ids["policy_id"]], "confirm": True,
        },
        {"action": "finish", "reason": "done"},
    ])
    tools = _tools("admin", question="确认清理这些政策")
    plan = ChatPlan(standalone_question="确认清理这些政策", intent="review_ops",
                    queries=["确认清理"], source="rule")
    try:
        run = run_agent(tools=tools, provider=provider, role="admin", plan=plan)
    finally:
        tools.db.close()

    assert [step.tool for step in run.steps] == ["list_cleanup_candidates", "cleanup_policies"]
    assert run.steps[1].hits == 1
    assert run.stop_reason == "model_finish"
    with SessionLocal() as db:
        assert db.get(Policy, ids["policy_id"]) is None

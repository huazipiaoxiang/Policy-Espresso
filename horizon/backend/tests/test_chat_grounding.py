from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ai.providers.mock import MockProvider
from app.chat.service import generate_grounded_chat
from app.chat.tools import ChatTools
from app.db.models import Assessment, Base, Document, Policy, ReviewTask, Source


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_policy(
    db: Session,
    *,
    title: str = "虚拟银行监管新规",
    summary: str = "要求持牌机构建立风险管控。",
    status: str = "published",
) -> Policy:
    source = db.scalar(select(Source).where(Source.code == "regulator"))
    if source is None:
        source = Source(
            id="s_regulator",
            code="regulator",
            name="示例监管机构",
            org="示例监管机构",
            jurisdiction="HK",
            tier=1,
            adapter="manual",
            url="https://regulator.example/",
            config={"secret": "must-not-be-exposed"},
        )
        db.add(source)
        db.flush()
    suffix = str(db.scalar(select(func.count(Policy.id))) or 0)
    document = Document(
        id=f"d_{suffix}",
        source_id=source.id,
        url=f"https://regulator.example/policies/{suffix}",
        canonical_url=f"https://regulator.example/policies/{suffix}",
        title=title,
        content_text=f"{title} 原文",
        content_hash=f"hash-{suffix}",
        published_at=datetime.now(timezone.utc),
    )
    policy = Policy(
        id=f"p_{suffix}",
        document=document,
        title=title,
        issuing_body="示例监管机构",
        summary_zh=summary,
        status=status,
    )
    db.add_all([document, policy])
    db.commit()
    return policy


def ask(db: Session, question: str, role: str = "analyst"):
    return generate_grounded_chat(
        tools=ChatTools(db, role),
        provider=MockProvider(),
        question=question,
    )


def test_extractive_answer_uses_current_db_and_structured_citations(db):
    policy = add_policy(db, summary="第一版摘要：建立风险管控。")
    first = ask(db, "请总结《虚拟银行监管新规》")
    assert "第一版摘要" in first.reply
    assert first.citations == [{
        "id": f"policy:{policy.id}",
        "type": "policy",
        "title": policy.title,
        "url": "https://regulator.example/policies/0",
        "policy_id": policy.id,
        "document_id": policy.document_id,
        "source_id": "s_regulator",
    }]

    policy.summary_zh = "第二版摘要：新增持续监测义务。"
    db.commit()
    second = ask(db, "请总结《虚拟银行监管新规》")
    assert "第二版摘要" in second.reply
    assert "第一版摘要" not in second.reply


def test_consumer_only_gets_published_policy_and_public_source_data(db):
    published = add_policy(db, title="已发布政策")
    draft = add_policy(db, title="未发布审核草案", status="pending_review")
    db.add_all([
        ReviewTask(id="rt_internal", policy_id=draft.id, assignee="internal.reviewer"),
        ReviewTask(id="rt_level_two", policy_id=draft.id, level=2, assignee="internal.approver"),
        Assessment(
            id="a_internal",
            policy_id=published.id,
            affected={"business_lines": ["confidential-business"]},
            transmission_chain=["internal-risk-chain"],
        ),
    ])
    db.commit()

    consumer = ChatTools(db, "consumer")
    assert [item.citation["policy_id"] for item in consumer.search_policies("")] == [published.id]
    assert [item.citation["document_id"] for item in consumer.search_documents("")] == [published.document_id]
    assert consumer.search_reviews("") == []
    assert consumer.search_business_impacts("") == []

    sources = consumer.search_sources("")
    assert len(sources) == 1
    assert "secret" not in sources[0].text
    assert "config" not in sources[0].citation
    assert sources[0].citation["type"] == "web_source"

    analyst = ChatTools(db, "analyst")
    assert {item.citation["policy_id"] for item in analyst.search_policies("")} == {published.id, draft.id}
    assert [item.citation["id"] for item in analyst.search_reviews("我的待办")] == ["review:rt_internal"]
    approver = ChatTools(db, "approver")
    assert [item.citation["id"] for item in approver.search_reviews("我的待办")] == ["review:rt_level_two"]
    impacts = analyst.search_business_impacts("")
    assert len(impacts) == 1
    assert "internal-risk-chain" in impacts[0].text


def test_search_text_cannot_execute_arbitrary_sql(db):
    add_policy(db)
    malicious = "'); DROP TABLE policy; --"
    result = ask(db, malicious)
    assert result.no_answer is True
    assert result.citations == []
    assert db.scalar(select(func.count(Policy.id))) == 1


def test_theme_terms_steer_policy_search(db):
    """主题词（如人民币国际化）常不在标题里；问题提到主题时必须命中对应政策而不是泛词匹配。"""
    target = add_policy(db, title="某通知", summary="一般通知内容。")
    target.themes = ["人民币国际化", "跨境支付"]
    decoy = add_policy(db, title="广东省人民政府调整最低工资通知", summary="各地级以上市人民政府执行。")
    db.commit()
    result = ask(db, "关于人民币国际化的政策有哪些？")
    assert result.no_answer is False
    assert result.citations[0]["policy_id"] == target.id
    assert f"policy:{decoy.id}" not in [citation["id"] for citation in result.citations]


def test_explicit_no_answer_when_database_has_no_reliable_evidence(db):
    add_policy(db, title="支付服务指引", summary="这是一般政策摘要，不能作为其他标题的依据。")
    result = ask(db, "请总结《完全不存在的政策》")
    assert result.no_answer is True
    assert "找不到足够的可靠资料" in result.reply
    assert result.citations == []


def test_weak_evidence_returns_explicit_no_answer(db):
    add_policy(db, title="香港金融管理局年报", summary="介绍银行业发展情况。")
    result = ask(db, "请问火星金融监管局发布了什么政策？")
    assert result.no_answer is True
    assert result.citations == []


def test_quoted_title_is_not_crowded_out_by_newer_partial_matches(db):
    target = add_policy(db, title="香港金融管理局 - 外匯基金分析帳目")
    for index in range(41):
        add_policy(db, title=f"香港金融管理局 - 其他通告 {index}")

    result = ask(db, "《香港金融管理局 - 外匯基金分析帳目》的发文机构是什么？")

    assert result.no_answer is False
    assert [citation["policy_id"] for citation in result.citations] == [target.id]
    assert "其他通告" not in result.reply


def test_provider_no_answer_does_not_fall_back_to_extractive_answer(db):
    from types import SimpleNamespace

    class NoAnswerProvider:
        name = "no-answer-test"

        def complete(self, **kwargs):
            return SimpleNamespace(
                parsed={"reply": "资料不足", "citation_ids": [], "no_answer": True},
                model="no-answer-test",
            )

    add_policy(db)
    result = generate_grounded_chat(
        tools=ChatTools(db, "analyst"), provider=NoAnswerProvider(), question="请总结《虚拟银行监管新规》",
    )
    assert result.no_answer is True
    assert result.citations == []
    assert "第一版摘要" not in result.reply
    assert "找不到足够的可靠资料" in result.reply


def test_grounded_partial_answer_with_valid_citations_is_surfaced(db):
    """LLM 找到政策但缺少细节时置 no_answer=true：有引用支撑的诚实回答应被保留。"""
    from types import SimpleNamespace

    policy = add_policy(db)

    class PartialAnswerProvider:
        name = "partial-answer-test"

        def complete(self, **kwargs):
            return SimpleNamespace(
                parsed={
                    "reply": "该政策由示例监管机构发布，但证据未包含具体条款细节。",
                    "citation_ids": [f"policy:{policy.id}"],
                    "no_answer": True,
                },
                model="partial-answer-test",
            )

    result = generate_grounded_chat(
        tools=ChatTools(db, "analyst"), provider=PartialAnswerProvider(),
        question="帮我解读《虚拟银行监管新规》",
    )
    assert result.no_answer is False
    assert result.citations[0]["policy_id"] == policy.id
    assert "具体条款" in result.reply
    assert "找不到足够的可靠资料" not in result.reply


def test_policy_search_matches_document_content_text(db):
    """原文正文中的条款（如贴息）必须可被检索命中，而不只匹配标题/摘要。

    正文匹配词按文档频率筛选（2..50 篇），故每个关键词需出现在两篇文档中。
    """
    target = add_policy(db, title="某通知", summary="一般通知内容。")
    target.document.content_text = "为支持实体经济发展，对符合条件的企业给予贷款贴息支持，年贴息率不超过1.5%。"
    loan_decoy = add_policy(db, title="贷款指引")
    loan_decoy.document.content_text = "本指引说明贷款业务的一般要求。"
    subsidy_decoy = add_policy(db, title="贴息办法")
    subsidy_decoy.document.content_text = "本文件不涉及贴息以外的内容。"
    for index in range(22):
        add_policy(db, title=f"其他政策 {index}")
    db.commit()
    result = ask(db, "贷款和贴息相关的政策有哪些？")
    assert result.no_answer is False
    assert result.citations[0]["policy_id"] == target.id
    assert "贴息" in result.reply


def test_empty_web_snippet_is_not_reliable_evidence(db, monkeypatch):
    from app.chat.tools import ChatEvidence

    monkeypatch.setattr("app.chat.service.search_web", lambda question: [ChatEvidence(
        key="web:1", kind="web_source", title="只有标题的网页", text="",
        citation={"id": "web:1", "type": "web_source", "title": "只有标题的网页", "url": "https://example.com"},
    )])
    result = ask(db, "联网查询最新监管新闻")
    assert result.no_answer is True
    assert result.citations == []


def test_pending_review_query_returns_tasks(db):
    policy = add_policy(db, title="待上线新规")
    db.add(ReviewTask(id="rt_pending", policy_id=policy.id, assignee="analyst.one", status="pending"))
    db.commit()
    result = ask(db, "我的审核待办有哪些？", role="analyst")
    assert result.no_answer is False
    assert result.citations[0]["policy_id"] == policy.id


def test_web_search_adds_verifiable_external_sources(db, monkeypatch):
    from app.chat.tools import ChatEvidence

    monkeypatch.setattr("app.chat.service.search_web", lambda question: [ChatEvidence(
        key="web:1", kind="web_source", title="监管机构最新通告",
        text="监管机构于今日发布支付服务指引。",
        citation={"id": "web:1", "type": "web_source", "title": "监管机构最新通告", "url": "https://regulator.example/latest"},
    )])
    result = ask(db, "联网查询最新支付监管新闻")
    assert "今日发布" in result.reply
    assert result.citations[0]["url"] == "https://regulator.example/latest"


def test_time_relative_listing_questions_are_recognized():
    """「今天新增的政策有哪些，帮我整理一下」应识别为列表类 + 今天入库意图。"""
    from app.chat.service import _is_generic_listing, _time_intent

    assert _is_generic_listing("今天新增的政策有哪些，帮我整理一下") is True
    assert _is_generic_listing("最近有什么新政策") is True
    assert _time_intent("今天新增的政策有哪些") == "today"
    assert _time_intent("最近有什么新政策") == "recent"
    assert _time_intent("虚拟银行监管新规是什么") == ""


def test_search_recent_policies_orders_by_fetched_at(db):
    from datetime import timedelta

    older = add_policy(db, title="五天前入库的政策")
    newer = add_policy(db, title="刚刚入库的政策")
    older.document.fetched_at = datetime.now(timezone.utc) - timedelta(days=5)
    newer.document.fetched_at = datetime.now(timezone.utc)
    db.commit()

    tools = ChatTools(db, "analyst")
    result = tools.search_recent_policies()
    assert result[0].title == "刚刚入库的政策"
    assert "入库时间" in result[0].text
    assert result[0].citation["policy_id"] == newer.id


def test_today_new_policies_are_listed_not_rejected(db):
    """「今天新增」是入库时间语义，不是政策发布日期；命中即列出，不 NO_ANSWER。"""
    add_policy(db, title="今天入库的政策")
    result = ask(db, "今天新增的政策有哪些，帮我整理一下")
    assert result.no_answer is False
    assert result.citations, "应列出新增政策而不是拒答"
    assert "找不到足够的可靠资料" not in result.reply


def test_yes_no_today_question_is_not_rejected_when_nothing_today(db):
    """「今天有新增政策吗」——今天没有入库记录时也应如实作答，而不是 NO_ANSWER。"""
    from datetime import timedelta

    policy = add_policy(db, title="昨天入库的政策")
    policy.document.fetched_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    result = ask(db, "今天有新增政策吗")
    assert result.no_answer is False
    assert "找不到足够的可靠资料" not in result.reply


def test_reference_resolution_uses_history_citations():
    from app.chat.service import _resolve_reference

    history = [
        {"role": "user", "content": "今天新增的政策有哪些"},
        {"role": "assistant", "content": "列出的政策", "citations": [
            {"id": "policy:p1", "type": "policy", "title": "政府推出新一批銀色債券"},
            {"id": "policy:p2", "type": "policy", "title": "加強規管持牌放債人"},
        ]},
    ]
    assert _resolve_reference("以上政策1如何帮到业务线", history) == "《政府推出新一批銀色債券》 以上政策1如何帮到业务线"
    assert _resolve_reference("第2条的发文机构是什么", history).startswith("《加強規管持牌放債人》")
    assert _resolve_reference("这些政策影响如何", history).startswith("《政府推出新一批銀色債券》")


def test_reference_resolution_no_history_is_noop():
    from app.chat.service import _resolve_reference

    assert _resolve_reference("以上政策1如何", None) == "以上政策1如何"
    assert _resolve_reference("虚拟银行监管新规是什么", []) == "虚拟银行监管新规是什么"


def test_reference_resolution_steers_retrieval_to_specific_policy(db):
    """「以上政策1」应精确命中上一轮第 1 条政策，而不是泛词命中的无关政策。"""
    target = add_policy(db, title="政府推出新一批銀色債券")
    add_policy(db, title="无关的另一个政策")
    history = [
        {"role": "assistant", "content": "列出的政策", "citations": [
            {"id": f"policy:{target.id}", "type": "policy", "title": "政府推出新一批銀色債券"},
        ]},
    ]
    result = generate_grounded_chat(
        tools=ChatTools(db, "analyst"),
        provider=MockProvider(),
        question="以上政策1如何帮到业务线",
        history=history,
    )
    assert result.no_answer is False
    assert result.citations[0]["policy_id"] == target.id


def test_duplicate_title_policies_are_deduplicated(db):
    """同标题定期报告（如 HKMA 月度报告，每期标题相同）只保留一条，来源列表不重复。"""
    add_policy(db, title="香港金融管理局月度报告")
    add_policy(db, title="香港金融管理局月度报告")
    result = ask(db, "《香港金融管理局月度报告》是什么")
    assert result.no_answer is False
    titles = [citation["title"] for citation in result.citations]
    assert titles.count("香港金融管理局月度报告") == 1


def test_response_citations_dedup_by_title():
    from app.api.v1.chat import _citations

    raw = [
        {"id": "policy:a", "type": "policy", "title": "同一标题"},
        {"id": "policy:b", "type": "policy", "title": "同一标题"},
        {"id": "policy:c", "type": "policy", "title": "另一标题"},
    ]
    citations = _citations(raw)
    assert len(citations) == 2
    assert [c.title for c in citations] == ["同一标题", "另一标题"]


def test_web_failure_is_explicit_and_never_fabricated(db, monkeypatch):
    from app.chat.web_search import WebSearchError

    def fail_search(question):
        raise WebSearchError("实时网页检索失败：测试网络不可用")

    monkeypatch.setattr("app.chat.service.search_web", fail_search)
    result = ask(db, "联网查询最新外部监管新闻")
    assert result.no_answer is True
    assert "测试网络不可用" in result.reply
    assert result.citations == []

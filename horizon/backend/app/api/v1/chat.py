"""Grounded AI chat with server-owned database tools and citations.

CHAT_AGENT_ENABLED=true 时走 agent 路径（模型自主检索），否则走既有 grounded 路径。
两条路径共用同一套检索工具与角色过滤；管理员在 agent 路径下另有任务型工具
（清理无关政策 / 生成影响报告），响应字段向后兼容（新增字段均有默认值）。
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.chat.agent import NON_AGENT_PROVIDERS
from app.chat.service import generate_admin_task, generate_agent_chat, generate_grounded_chat
from app.chat.tools import ChatTools
from app.core.config import Settings, get_settings
from app.core.security import get_demo_role, require_api_key
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])

_CITATION_TYPES = {"policy", "document", "web_source", "task"}


class ChatCitation(BaseModel):
    id: str
    type: Literal["policy", "document", "web_source", "task"]
    title: str
    url: str = ""
    policy_id: str | None = None
    document_id: str | None = None
    source_id: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    # assistant 消息可选携带上一轮引用的政策，用于「以上政策1 / 这条」的指代消解
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)
    context: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def limit_total_size(self):
        if sum(len(message.content) for message in self.messages) > 12000:
            raise ValueError("conversation content exceeds 12000 characters")
        if not any(message.role == "user" for message in self.messages):
            raise ValueError("at least one user message is required")
        return self


class ChatStep(BaseModel):
    """Agent 执行过程（前端折叠区渲染用）。"""

    round: int
    tool: str
    query: str
    hits: int
    note: str = ""


class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: int
    citations: list[ChatCitation] = Field(default_factory=list)
    no_answer: bool = False
    answer_mode: str = "grounded"          # grounded | mixed | general
    steps: list[ChatStep] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    clarifying_question: str = ""


def _to_citation(raw: dict[str, Any]) -> ChatCitation | None:
    """只接受已知字段与合法 type，脏数据直接丢弃而不是让响应 500。"""
    if not isinstance(raw, dict):
        return None
    citation_id = str(raw.get("id") or "")
    title = str(raw.get("title") or "")
    kind = str(raw.get("type") or "")
    if not citation_id or not title or kind not in _CITATION_TYPES:
        return None
    return ChatCitation(
        id=citation_id,
        type=kind,  # type: ignore[arg-type]
        title=title[:300],
        url=str(raw.get("url") or "")[:2000],
        policy_id=raw.get("policy_id"),
        document_id=raw.get("document_id"),
        source_id=raw.get("source_id"),
    )


def _citations(raw: list[Any]) -> list[ChatCitation]:
    items = []
    seen: set[tuple[str, str]] = set()
    for entry in raw or []:
        citation = _to_citation(entry)
        if citation is None:
            continue
        # 兜底去重：policy 证据与 impact 证据可能指向同一标题（同一定期报告的期数），
        # 来源列表只展示一次，避免「[1]~[8] 全是同一条」。
        key = (citation.type, citation.title)
        if key in seen:
            continue
        seen.add(key)
        items.append(citation)
    return items


class ChatCapabilities(BaseModel):
    """助手当前真实能力：是否接了 LLM、是否走 Agent、能否执行管理员任务。"""

    provider: str
    llm_ready: bool
    agent_enabled: bool
    agent_active: bool
    mode: Literal["agent", "grounded", "rules"]
    admin_tasks: bool
    hint: str


@router.get("/capabilities", response_model=ChatCapabilities)
def chat_capabilities(
    role: str = Depends(get_demo_role),
    settings: Settings = Depends(get_settings),
):
    """让前端如实告知用户当前模式，避免把「规则检索」误当成助手的产品形态。"""
    provider = get_provider()
    provider_name = str(getattr(provider, "name", "unknown"))
    llm_ready = provider_name not in NON_AGENT_PROVIDERS
    agent_active = bool(settings.chat_agent_enabled and llm_ready)

    if not llm_ready:
        mode: Literal["agent", "grounded", "rules"] = "rules"
        hint = (
            "当前为规则检索模式：回答由库内检索与原文摘录生成，不具备自主推理。"
            "配置 LLM_PROVIDER（dashscope 或 ollama）并提供密钥或本地模型后，自动升级为 Agent。"
        )
    elif not settings.chat_agent_enabled:
        mode = "grounded"
        hint = (
            "已接入生成式模型，但 Agent 路径关闭：单轮检索后作答。"
            "设置 CHAT_AGENT_ENABLED=true 可启用自主多轮工具调用。"
        )
    else:
        mode = "agent"
        hint = "Agent 模式：模型自主规划、多轮选择工具检索后作答。"

    return ChatCapabilities(
        provider=provider_name,
        llm_ready=llm_ready,
        agent_enabled=bool(settings.chat_agent_enabled),
        agent_active=agent_active,
        mode=mode,
        admin_tasks=role == "admin",
        hint=hint,
    )


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
    settings: Settings = Depends(get_settings),
):
    """Retrieve fresh role-scoped evidence before invoking the provider."""

    question = next(message.content for message in reversed(req.messages) if message.role == "user")
    history = [
        {
            "role": message.role,
            "content": message.content,
            "citations": [citation.model_dump() for citation in message.citations],
        }
        for message in req.messages
    ]
    # question 用于破坏性任务的「用户本人确认」校验：模型不能替用户点头
    tools = ChatTools(db, role, question=question, actor=f"demo.{role}")
    provider = get_provider()

    # 管理员任务（清理无关政策 / 生成影响报告）走确定性路由：破坏性操作不交给模型自由裁量，
    # 无论 Agent 路径是否开启都可用；未命中时返回 None，继续正常问答。
    task = generate_admin_task(tools, question)
    if task is not None:
        return ChatResponse(
            reply=task.reply,
            model=task.model,
            latency_ms=task.latency_ms,
            citations=_citations(task.citations),
            no_answer=task.no_answer,
            answer_mode="grounded",
        )

    # 未接入生成式模型（mock）时 Agent 循环无法驱动，自动回退 grounded，避免「开了开关反而更弱」
    llm_ready = str(getattr(provider, "name", "")) not in NON_AGENT_PROVIDERS
    if settings.chat_agent_enabled and llm_ready:
        result = generate_agent_chat(
            tools=tools,
            provider=provider,
            question=question,
            context=req.context,
            history=history,
        )
        return ChatResponse(
            reply=result.reply,
            model=result.model,
            latency_ms=result.latency_ms,
            citations=_citations(result.citations),
            no_answer=result.no_answer,
            answer_mode=result.answer_mode,
            steps=[ChatStep(**step.as_dict()) for step in result.steps],
            followups=result.followups,
            clarifying_question=result.clarifying_question,
        )

    grounded = generate_grounded_chat(
        tools=tools,
        provider=provider,
        question=question,
        context=req.context,
        history=history,
    )
    return ChatResponse(
        reply=grounded.reply,
        model=grounded.model,
        latency_ms=grounded.latency_ms,
        citations=_citations(grounded.citations),
        no_answer=grounded.no_answer,
        answer_mode="general" if grounded.no_answer else "grounded",
    )

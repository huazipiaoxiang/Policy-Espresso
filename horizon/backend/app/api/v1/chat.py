"""AI 对话接口（雷达页智能助手）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.provider import get_provider
from app.core.security import require_api_key

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str | None = None  # 可选：当前页面上下文（如政策标题）


class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: int


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    """简单对话：把历史 + 当前问题拼成 user prompt，走 provider.complete。"""
    provider = get_provider()

    # 构造 system prompt
    system = (
        "你是 HORIZON 政策雷达的智能助手。你可以帮助用户：\n"
        "1. 解读政策内容和影响\n"
        "2. 分析政策与汇丰业务的关联\n"
        "3. 回答关于政策库的问题\n"
        "请用简洁、专业的中文回答。"
    )

    # 拼接用户消息历史
    user_parts = []
    if req.context:
        user_parts.append(f"【当前上下文】{req.context}\n")
    for msg in req.messages:
        prefix = "用户" if msg.role == "user" else "助手"
        user_parts.append(f"{prefix}：{msg.content}")
    user_prompt = "\n".join(user_parts)

    result = provider.complete(
        system=system,
        user=user_prompt,
        schema=None,  # 文本输出，不需要结构化
        temperature=0.7,
        max_tokens=2048,
        task="chat",
    )

    return ChatResponse(
        reply=result.text,
        model=result.model,
        latency_ms=result.latency_ms,
    )

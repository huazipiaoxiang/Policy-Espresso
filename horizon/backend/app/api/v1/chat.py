"""Grounded AI chat with server-owned database tools and citations."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.chat.service import generate_grounded_chat
from app.chat.tools import ChatTools
from app.core.security import get_demo_role, require_api_key
from app.db.session import get_db

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


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


class ChatCitation(BaseModel):
    id: str
    type: Literal["policy", "document", "web_source"]
    title: str
    url: str = ""
    policy_id: str | None = None
    document_id: str | None = None
    source_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: int
    citations: list[ChatCitation] = Field(default_factory=list)
    no_answer: bool = False


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
):
    """Retrieve fresh role-scoped evidence before invoking the provider."""

    question = next(message.content for message in reversed(req.messages) if message.role == "user")
    result = generate_grounded_chat(
        tools=ChatTools(db, role),
        provider=get_provider(),
        question=question,
        context=req.context,
    )
    return ChatResponse(
        reply=result.reply,
        model=result.model,
        latency_ms=result.latency_ms,
        citations=result.citations,
        no_answer=result.no_answer,
    )

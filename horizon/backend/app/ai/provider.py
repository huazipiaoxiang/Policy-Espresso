"""LLMProvider 抽象（03 §5）。业务代码只依赖此接口，切换走 LLM_PROVIDER 环境变量。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.core.config import get_settings


@dataclass
class LLMResult:
    text: str
    parsed: dict | None  # schema 校验后的结构化结果
    usage: dict = field(default_factory=dict)  # prompt/completion tokens
    latency_ms: int = 0
    model: str = ""
    raw: dict = field(default_factory=dict)  # 原始响应，排障用


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict | None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        task: str = "",
    ) -> LLMResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def input_hash(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\n---\n{user}".encode()).hexdigest()


def get_provider() -> LLMProvider:
    """按 LLM_PROVIDER 实例化。业务代码零改动切换。"""
    settings = get_settings()
    name = settings.llm_provider.lower()
    if name == "mock":
        from app.ai.providers.mock import MockProvider

        return MockProvider()
    if name == "ollama":
        from app.ai.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    if name == "dashscope":
        from app.ai.providers.dashscope import DashScopeProvider

        return DashScopeProvider(api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url)
    raise ValueError(f"未知 LLM_PROVIDER: {settings.llm_provider}")

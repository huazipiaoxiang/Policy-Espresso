"""Ollama 本地 Provider（OpenAI 兼容端点，默认 http://localhost:11434/v1）。"""
from __future__ import annotations

from app.ai.providers.openai_compat import OpenAICompatProvider


class OllamaProvider(OpenAICompatProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, model: str):
        super().__init__(base_url=base_url, api_key="ollama", default_model=model)

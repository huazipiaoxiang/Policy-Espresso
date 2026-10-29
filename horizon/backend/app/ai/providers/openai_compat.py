"""OpenAI 兼容端点公共实现：Ollama 与 DashScope 共用，差异仅在 base_url/model。"""
from __future__ import annotations

import json
import time

import httpx

from app.ai.provider import LLMResult


class OpenAICompatProvider:
    """面向 /chat/completions 兼容端点（Ollama /v1、DashScope compatible-mode）。"""

    name = "openai_compat"

    def __init__(self, *, base_url: str, api_key: str = "", default_model: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
        task: str = "",
    ) -> LLMResult:
        return self.complete_messages(
            system=system,
            messages=[{"role": "user", "content": user}],
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            task=task,
        )

    def complete_messages(
        self,
        *,
        system: str,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
        task: str = "",
    ) -> LLMResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # 兼容端点要求首条为 system；多轮序列原样追加，保证工具观察结果按序回灌。
        payload: dict = {
            "model": model or self.default_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        resp = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        raw = resp.json()
        latency_ms = int((time.monotonic() - started) * 1000)

        text = raw["choices"][0]["message"]["content"] or ""
        parsed = None
        if schema is not None:
            from app.ai.guard import repair_json

            parsed = repair_json(text)
            if parsed is not None and schema:
                from app.ai.guard import validate_schema

                validate_schema(parsed, schema)  # 失败抛 SchemaValidationError，由 chain 层重试
        usage = raw.get("usage", {})
        return LLMResult(
            text=text,
            parsed=parsed,
            usage={"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)},
            latency_ms=latency_ms,
            model=raw.get("model", model or self.default_model),
            raw=raw,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("嵌入走独立 EmbeddingProvider（Phase 2 接入）")


def _safe_loads(text: str) -> dict | None:
    try:
        return json.loads(text)
    except Exception:
        return None

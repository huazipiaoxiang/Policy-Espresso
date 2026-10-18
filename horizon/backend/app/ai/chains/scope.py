"""P3 适用范围判定（plus 档，LLM 通道；规则通道在 domain/scope_rules）。"""
from __future__ import annotations

from app.ai.chains.base import BaseChain
from app.ai.schemas import SCOPE_SCHEMA


class ScopeChain(BaseChain):
    task = "scope"

    def run(self, *, content_text: str, rule_hint: str):  # noqa: ANN201
        return super().run(
            variables={"content": content_text, "rule_hint": rule_hint},
            content_text=content_text,
            schema=SCOPE_SCHEMA,
        )

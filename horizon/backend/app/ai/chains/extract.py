"""P2 结构化抽取（plus 档）。"""
from __future__ import annotations

from app.ai.chains.base import BaseChain
from app.ai.schemas import EXTRACT_SCHEMA


class ExtractChain(BaseChain):
    task = "extract"

    def run(self, *, content_text: str):  # noqa: ANN201
        return super().run(
            variables={"content": content_text},
            content_text=content_text,
            schema=EXTRACT_SCHEMA,
        )

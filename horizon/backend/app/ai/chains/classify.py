"""P1 相关性分类（flash 档）。"""
from __future__ import annotations

from app.ai.chains.base import BaseChain
from app.ai.schemas import CLASSIFY_SCHEMA


class ClassifyChain(BaseChain):
    task = "classify"

    def run(self, *, title: str, content_text: str):  # noqa: ANN201
        return super().run(
            variables={"content": f"{title}\n\n{content_text[:2000]}"},
            content_text=content_text,
            schema=CLASSIFY_SCHEMA,
        )

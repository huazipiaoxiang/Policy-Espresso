"""Chat Agent 的数据结构：规划、执行步骤与最终结果。

对外（/chat 响应）只暴露可观测字段，证据正文与提示词不外泄。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INTENTS = ("lookup", "compare", "interpret", "review_ops", "web_fresh", "chitchat")
ANSWER_MODES = ("grounded", "mixed", "general")

MAX_QUERIES = 3
MAX_FOLLOWUPS = 3


@dataclass
class ChatPlan:
    """Planner 输出：把依赖上下文的问法改写成可独立检索的查询。"""

    standalone_question: str
    intent: str = "lookup"
    queries: list[str] = field(default_factory=list)
    needs_web: bool = False
    source: str = "rule"  # llm | rule —— 便于日志区分是否走了回退


@dataclass
class ChatStep:
    """一次工具调用的可观测记录（前端折叠区渲染用）。"""

    round: int
    tool: str
    query: str
    hits: int
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"round": self.round, "tool": self.tool, "query": self.query,
                "hits": self.hits, "note": self.note}


@dataclass
class ChatAgentResult:
    reply: str
    model: str
    latency_ms: int
    citations: list[dict[str, Any]] = field(default_factory=list)
    answer_mode: str = "general"
    steps: list[ChatStep] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    clarifying_question: str = ""
    no_answer: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "citations": self.citations,
            "answer_mode": self.answer_mode,
            "steps": [step.as_dict() for step in self.steps],
            "followups": self.followups,
            "clarifying_question": self.clarifying_question,
            "no_answer": self.no_answer,
        }

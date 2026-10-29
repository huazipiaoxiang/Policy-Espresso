"""Chat Agent 工具注册表：把 ChatTools 的只读检索包装成可供 LLM 选择的工具。

契约（不可突破）：
- 工具只接受**文本查询**，绝不接受 SQL 或任意过滤表达式；
- 角色不可见的工具在注册表层面**不注册**（而非返回空），模型看不到就调不到；
- 参数一律 clamp（query ≤200 字，limit 1..8），未知工具返回错误观察而不是抛异常，
  让模型自行改道而不是把请求打挂。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.chat.tools import ChatEvidence, ChatTools, normalize_role
from sqlalchemy.orm import Session

from app.chat.web_search import WebSearchError, search_web
from app.core.logging import get_logger
from app.search.retriever import hybrid_search, vector_available

log = get_logger("chat.registry")

QUERY_MAX = 200
LIMIT_MIN = 1
LIMIT_MAX = 8
DEFAULT_LIMIT = 5

ALL_ROLES = frozenset({"admin", "analyst", "approver", "publisher", "consumer"})
PRIVILEGED_ROLES = frozenset({"admin", "analyst", "approver", "publisher"})

ToolHandler = Callable[[ChatTools, str, int], list[ChatEvidence]]


def clamp_query(value: object) -> str:
    """查询串 clamp：去空白后截到 200 字，避免把整篇问题塞进 LIKE。"""
    text = " ".join(str(value or "").split())
    return text[:QUERY_MAX]


def clamp_limit(value: object, default: int = DEFAULT_LIMIT) -> int:
    try:
        limit = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(LIMIT_MIN, min(LIMIT_MAX, limit))


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的元数据与执行入口。"""

    name: str
    description: str
    visible_to: frozenset[str]
    handler: ToolHandler = None  # type: ignore[assignment]

    def run(self, tools: ChatTools, args: dict[str, Any]) -> list[ChatEvidence]:
        query = clamp_query(args.get("query"))
        limit = clamp_limit(args.get("limit"))
        return self.handler(tools, query, limit)


def _search_policies(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return tools.search_policies(query)[:limit]


def _search_documents(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return tools.search_documents(query)[:limit]


def _search_semantic(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return hybrid_search(tools.db, tools, query, limit=limit)


def _search_sources(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return tools.search_sources(query)[:limit]


def _search_reviews(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return tools.search_reviews(query)[:limit]


def _search_impacts(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return tools.search_business_impacts(query)[:limit]


def _search_web(tools: ChatTools, query: str, limit: int) -> list[ChatEvidence]:
    return search_web(query, limit=max(LIMIT_MIN, min(limit, 5)))


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_policies",
        description="按政策标题/摘要/发布机构/文号检索政策条目，返回发布机构、文号、日期与摘要。适合「某政策是否存在、基本信息、最新政策列表」。",
        visible_to=ALL_ROLES,
        handler=_search_policies,
    ),
    ToolSpec(
        name="search_documents",
        description="检索原文正文段落，返回与查询相关的原文摘录。适合「原文怎么写的、条款细节、适用范围」。",
        visible_to=ALL_ROLES,
        handler=_search_documents,
    ),
    ToolSpec(
        name="search_semantic",
        description="语义/同义表述检索：主题词不在标题里、或用词与原文不同时用它补全召回。返回相关原文片段。",
        visible_to=ALL_ROLES,
        handler=_search_semantic,
    ),
    ToolSpec(
        name="search_sources",
        description="检索来源机构（名称/所属机构/地区/级别）。适合「这个政策来自哪个网站、有哪些监管来源」。",
        visible_to=ALL_ROLES,
        handler=_search_sources,
    ),
    ToolSpec(
        name="search_reviews",
        description="检索内部审核任务（政策/级别/状态/负责人）。适合「我的待办、哪些待审核、谁负责」。",
        visible_to=PRIVILEGED_ROLES,
        handler=_search_reviews,
    ),
    ToolSpec(
        name="search_business_impacts",
        description="检索业务影响评估（方向/优先级/传导链/建议动作/置信度）。适合「对我们业务有什么影响、建议怎么做」。",
        visible_to=PRIVILEGED_ROLES,
        handler=_search_impacts,
    ),
    ToolSpec(
        name="search_web",
        description="联网检索公开网页。仅在问题明显需要库外最新信息（今日新闻、库内确无记录）时使用，慢且可能失败。",
        visible_to=ALL_ROLES,
        handler=_search_web,
    ),
)


def available_tools(role: object, *, db: Session | None = None) -> list[ToolSpec]:
    """按角色返回可见工具；不可见的工具不出现在提示词里，模型无从调用。

    db 不为空时额外探测向量通道：索引为空/无 numpy/嵌入不可达时不下发 search_semantic，
    免得模型去调一个只会退化成词法检索的工具。
    """
    normalized = normalize_role(role)
    specs = [spec for spec in TOOLS if normalized in spec.visible_to]
    if db is not None and not vector_available(db):
        return [spec for spec in specs if spec.name != "search_semantic"]
    return specs


def describe_tools(role: object, *, db: Session | None = None, extra: str = "") -> str:
    """给 Planner/Executor 提示词用的工具清单。"""
    lines = [
        f"- {spec.name}：{spec.description}"
        for spec in available_tools(role, db=db)
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def run_tool(tools: ChatTools, role: object, name: str, args: dict[str, Any]) -> tuple[list[ChatEvidence], str]:
    """执行工具，返回 (证据, 观察备注)。备注为空表示正常命中。"""
    normalized = normalize_role(role)
    for spec in TOOLS:
        if spec.name == name:
            if normalized not in spec.visible_to:
                log.warning("chat_tool_denied", tool=name, role=normalized)
                return [], f"工具 {name} 对当前角色不可用，请换用其他工具。"
            try:
                evidence = spec.run(tools, args or {})
            except WebSearchError as exc:
                return [], f"{name} 失败：{exc}（可换用库内检索工具）"
            except Exception as exc:  # 工具边界：单个工具失败不该打断整个循环
                log.warning("chat_tool_failed", tool=name, error_type=type(exc).__name__)
                return [], f"{name} 执行出错，请换用其他工具或改写查询。"
            if not evidence:
                return [], f"{name} 命中 0 条，建议换工具或改写查询词。"
            return evidence, ""
    return [], f"未知工具 {name}。可用工具：{', '.join(spec.name for spec in available_tools(role))}。"

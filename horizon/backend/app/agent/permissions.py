"""AI Agent 权限模型：除「数据外泄」外全部放开。

能力标签：
- read            读取库内政策、原文、业务图谱、客户暴露（聚合口径）
- write           写入政策字段、生成/更新预处理记录
- trigger         触发分析与预处理重建任务
- publish         发布政策
- public_egress   仅携带公开信息的联网检索（政策标题/主题等），需过出网清洗
- egress          把库内任何数据发送到系统外部 —— 唯一被禁止的能力

工具只登记它需要的能力；执行前统一用 `check_tool_permission` 校验，
任何 tagged `egress` 的工具一律拒绝。
"""
from __future__ import annotations

import re

READ = "read"
WRITE = "write"
DELETE = "delete"
TRIGGER = "trigger"
PUBLISH = "publish"
PUBLIC_EGRESS = "public_egress"
EGRESS = "egress"

# Agent 被授予的能力：除 egress 外全部开放
AGENT_PERMISSIONS: frozenset[str] = frozenset({READ, WRITE, DELETE, TRIGGER, PUBLISH, PUBLIC_EGRESS})
DENIED_PERMISSIONS: frozenset[str] = frozenset({EGRESS})

CAPABILITY_LABELS: dict[str, str] = {
    READ: "读取库内政策/原文/业务图谱/客户暴露（聚合）",
    WRITE: "写入政策字段与预处理记录",
    DELETE: "删除对汇丰无影响的政策及其原文",
    TRIGGER: "触发分析与预处理任务",
    PUBLISH: "发布政策",
    PUBLIC_EGRESS: "仅公开信息的联网检索",
    EGRESS: "把库内数据发送到系统外部（禁止）",
}

# 出网清洗：查询中出现这些特征即判定为内部数据外泄
INTERNAL_MARKERS = (
    "customer_id", "cus_", "p_", "d_", "客户id", "客户编号", "内部评分", "内部批注",
    "审批意见", "工号", "@hsbc", "internal", "敞口金额", "贷款余额", "亏损",
)

# 联网检索可使用的通用公开词
PUBLIC_SAFE_WORDS = (
    "政策", "银行", "汇丰", "hsbc", "新闻", "回应", "应对", "落地", "案例",
    "实施", "解读", "通知", "公告", "监管", "措施", "细则", "指引", "办法",
)


class ToolPermissionError(RuntimeError):
    """工具所需能力不在授予范围内。"""


def check_tool_permission(name: str, required: frozenset[str]) -> None:
    """校验工具所需能力；egress 或超出授予范围一律拒绝。"""
    if required & DENIED_PERMISSIONS:
        raise ToolPermissionError(
            f"工具 {name} 需要「数据外泄」能力，已被权限策略禁止"
        )
    missing = required - AGENT_PERMISSIONS
    if missing:
        raise ToolPermissionError(
            f"工具 {name} 需要未授权能力：{'、'.join(sorted(missing))}"
        )


def _cjk_tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}", text or "")


def sanitize_public_query(
    query: str,
    *,
    allowed_texts: list[str] | None = None,
    max_chars: int = 80,
) -> tuple[str | None, str]:
    """把 Agent 的检索词收敛为「只含政策公开信息」的查询。

    返回 (query, "") 表示允许出网；(None, reason) 表示按数据外泄策略拦截：
    - 含客户/内部标识、评分、内部批注等特征 → 拦截；
    - 与政策公开文本（标题/主题/发文机构）无交集 → 拦截（防止把内部问题原样发出）。
    """
    text = " ".join(str(query or "").split())
    if not text:
        return None, "检索词为空"
    lowered = text.casefold()
    for marker in INTERNAL_MARKERS:
        if marker in lowered:
            return None, f"检索词包含内部数据特征「{marker}」，已按数据外泄策略拦截"

    allowed_blob = " ".join(allowed_texts or []).casefold()
    safe = {word.casefold() for word in PUBLIC_SAFE_WORDS}
    kept: list[str] = []
    for token in re.split(r"[\s,，、;；/]+", text):
        token = token.strip()
        if not token:
            continue
        lowered_token = token.casefold()
        matched = lowered_token in safe or (allowed_blob and lowered_token in allowed_blob)
        if not matched and allowed_blob:
            matched = any(part in allowed_blob for part in _cjk_tokens(token))
        if matched:
            kept.append(token)
    if not kept:
        return None, "检索词与政策公开信息无交集，已按数据外泄策略拦截"
    return " ".join(kept)[:max_chars], ""


def describe_permissions() -> dict:
    """给前端/接口展示的权限说明。"""
    return {
        "granted": sorted(AGENT_PERMISSIONS),
        "denied": sorted(DENIED_PERMISSIONS),
        "labels": CAPABILITY_LABELS,
        "note": "AI Agent 除「数据外泄」外权限全开：可读库内数据、写政策与预处理、触发任务、发布政策，并可检索公开信息。",
    }

"""政策/审核状态机（04 §3）。显式转移表，非法转移抛异常，禁止直接 UPDATE status。"""
from __future__ import annotations

POLICY_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"ai_checked", "pending_review", "archived"},
    "ai_checked": {"pending_review", "archived"},
    "pending_review": {"in_review", "archived"},
    "in_review": {"approved", "rejected", "needs_info"},
    "needs_info": {"pending_review", "rejected"},
    "approved": {"published", "archived"},
    "published": {"archived"},
    "rejected": {"archived", "draft"},  # 重开需新建 task 并清空旧 assessment
    "archived": set(),
}

REJECT_REASON_CODES = {"insufficient_evidence", "impact_misjudged", "scope_misjudged", "bad_wording", "duplicate", "other"}

# 双签规则：P0/P1 需两级（分析师 + 合规/业务主管），P2/P3 单签
DOUBLE_SIGN_PRIORITIES = {"P0", "P1"}


class InvalidTransitionError(ValueError):
    pass


def can_transition(current: str, target: str) -> bool:
    return target in POLICY_TRANSITIONS.get(current, set())


def transition(current: str, target: str, *, reason: str = "") -> str:
    """校验并返回目标状态；非法转移抛 InvalidTransitionError。

    调用方（service 层）负责：写 audit_log；rejected→draft 时必须带 reason 且清空旧 assessment。
    """
    if not can_transition(current, target):
        raise InvalidTransitionError(f"非法状态转移: {current} -> {target}")
    if current == "rejected" and target == "draft" and not reason:
        raise InvalidTransitionError("rejected -> draft 必须记录重开原因")
    return target


def required_review_levels(priority: str) -> int:
    """返回所需审核级数：P0/P1 双签=2，其余单签=1。"""
    return 2 if priority in DOUBLE_SIGN_PRIORITIES else 1


def can_dispatch(status: str) -> bool:
    """只有 approved 之后的 published 才能分发（04 §3）。"""
    return status == "published"

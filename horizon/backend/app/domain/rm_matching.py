"""登录用户名 ↔ 客户经理（relationship_manager）匹配。

客户经理编号在合成客户数据集里形如 `rmdemo01`~`rmdemo12`（历史上曾用 `rm.demo01`）。
匹配时统一去掉 `rm` 前缀与分隔符，因此 `rmdemo01` / `rm.demo01` / `RMDEMO01` 都能对上；
用户名匹配不上任何客户经理时由调用方走「规则 B」（直接用预处理百分比）。
"""
from __future__ import annotations

import re

from app.domain.exposure import load_customers

_RM_PREFIX = re.compile(r"^rm[.\-_]?", re.IGNORECASE)
_SEPARATORS = re.compile(r"[\s\-_.]+")


def rm_key(value: str | None) -> str:
    """归一化为短键：`rm.demo01` / `rmdemo01` / `RMDEMO01` → `demo01`。"""
    text = _SEPARATORS.sub("", (value or "").strip().lower())
    return _RM_PREFIX.sub("", text)


def customers_of(username: str | None) -> list[dict]:
    """返回该用户名名下（relationship_manager 匹配）的合成客户；无匹配返回空列表。"""
    key = rm_key(username)
    if not key:
        return []
    return [
        customer for customer in load_customers()
        if rm_key(customer.get("relationship_manager")) == key
    ]


def match_rm(username: str | None) -> str | None:
    """返回命中的客户经理编号原文（如 `rmdemo01`），未命中返回 None。"""
    customers = customers_of(username)
    if not customers:
        return None
    return str(customers[0].get("relationship_manager") or "") or None

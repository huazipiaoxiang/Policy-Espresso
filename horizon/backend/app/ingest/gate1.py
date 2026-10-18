"""gate-1 规则过滤（01 §五）：金融关键词命中即放行，否则标 ignored（仍入库备查）。

只做"是否可能是金融政策"的粗筛；精确分类是 Phase 2 的 gate-2 AI 分类。
"""
from __future__ import annotations

import re

FINANCE_KEYWORDS = (
    "銀行|银行|金融|貨幣|货币|人民幣|人民币|跨境|貸款|贷款|貼息|贴息|債券|债券|保險|保险|證券|证券|"
    "利率|存款|支付|外匯|外汇|資本|资本|監管|监管|金管局|人民銀行|人民银行|財政|财政|稅|税|"
    "理財通|理财通|CEPA|自貿|自贸|大灣區|大湾区|债券通|深港通|滬深港通|QFII|QDII|QFLP|"
    "bank|monetary|financial|securit|insurance|bond|loan|interest rate|base rate|capital|"
    "HKMA|SFC|金管局|證監會|证监会|施政報告|施政报告|預算案|预算案"
)

_RE = re.compile(FINANCE_KEYWORDS, re.IGNORECASE)


def gate1_pass(title: str, content_text: str) -> tuple[bool, list[str]]:
    """返回 (是否通过, 命中关键词列表)。检查标题 + 正文前 2000 字。"""
    haystack = f"{title}\n{(content_text or '')[:2000]}"
    hits = sorted(set(m.group(0) for m in _RE.finditer(haystack)))
    return bool(hits), hits[:10]

"""外资行相关性判定 —— 规则通道（02 §5.3，05-P3 的规则侧）。

LLM 通道在 ai/chains/scope.py；两通道冲突 → needs_review，不得自动降级。
实体清单只含 hsbc_hk 与 hsbc_cn；恒生等集团成员仅打 group_affiliate_mention。

相关性三级：
- high：明确适用于外资行，进入 AI 深度分析
- medium：可能适用，需人工快速筛选
- low：基本不适用，跳过分析但保留在库
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 适用主体表述词典（02 §5.3 规则通道）
SCOPE_PATTERNS: dict[str, str] = {
    "low": r"中资商业银行|境内法人银行|境内银行业金融机构|国有大型银行|股份制银行|城市商业银行|农村金融机构|内资银行",
    "high": r"外资银行|外商独资银行|中外合资银行|境外金融机构|外资法人银行",
    "medium": r"合资格机构|符合条件的.{0,12}(银行|机构|法人)",
    "high_generic": r"银行业金融机构|所有银行|各银行|金融机构",
}

GROUP_AFFILIATE_NAMES = ["恒生银行", "恒生", "Hang Seng Bank"]

TARGET_ENTITIES = {
    "hsbc_hk": {
        "name": "香港上海汇丰银行有限公司",
        "nature": "香港注册认可机构",
        "regime": "HKMA 认可机构口径",
    },
    "hsbc_cn": {
        "name": "汇丰银行（中国）有限公司",
        "nature": "内地注册外商独资法人银行",
        "regime": "NFRA 外资法人银行口径",
    },
}


@dataclass
class RuleHit:
    category: str  # high / medium / low / high_generic
    pattern: str
    span_start: int
    span_end: int
    quote: str


@dataclass
class RuleScopeResult:
    hits: list[RuleHit] = field(default_factory=list)
    relevance: str = "medium"  # high / medium / low / unclear
    group_affiliate_mention: dict = field(default_factory=dict)


def detect_scope(text: str) -> RuleScopeResult:
    """规则通道：词典匹配适用主体表述。

    输入：政策正文（或适用主体段落）。输出：命中列表 + 建议相关性 + 集团成员提及标记。
    失败模式：无命中 → relevance=unclear（交给 LLM 通道或人工）。
    """
    hits: list[RuleHit] = []
    for category, pattern in SCOPE_PATTERNS.items():
        for m in re.finditer(pattern, text):
            hits.append(RuleHit(category=category, pattern=pattern, span_start=m.start(), span_end=m.end(), quote=m.group()))

    mentioned = [name for name in GROUP_AFFILIATE_NAMES if name in text]
    affiliate = {
        "mentioned": bool(mentioned),
        "entities": sorted(set(mentioned)),
        "note": "原文点名集团其他成员，仅提示，不参与汇丰实体判定、不触发预警" if mentioned else "",
    }

    # 建议相关性优先级：明确排除性表述(low) > 明确包含外资(high) > 合资格限定(medium) > 泛指(high)
    categories = {h.category for h in hits}
    if "low" in categories and "high" not in categories and "high_generic" not in categories:
        relevance = "low"
    elif "high" in categories:
        relevance = "high"
    elif "medium" in categories:
        relevance = "medium"
    elif "high_generic" in categories:
        relevance = "high"
    else:
        relevance = "unclear"

    return RuleScopeResult(hits=hits, relevance=relevance, group_affiliate_mention=affiliate)


def entity_relevance_from_scope(entity_id: str, relevance: str) -> str:
    """由 relevance 推目标实体相关性（规则侧结论，供与 LLM 通道比对）。

    hsbc_hk 是境外/香港注册机构：境内主体限定政策通常为 na；
    hsbc_cn 是境内外商独资法人银行：low → low；high/high_generic → high。
    """
    if entity_id not in TARGET_ENTITIES:
        raise ValueError(f"未知目标实体: {entity_id}")
    if relevance == "unclear":
        return "not_mentioned"
    if relevance == "medium":
        return "medium"  # 需个案判断，规则不下结论
    if entity_id == "hsbc_hk":
        return "na" if relevance == "low" else "not_mentioned"
    return {"low": "low", "high": "high", "high_generic": "high"}[relevance]

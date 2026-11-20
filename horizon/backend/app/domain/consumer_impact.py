"""政策使用者视角的影响维度评分（业务损失 / 业务机会 / 声誉风险）。

三维统一输出 0–100 的程度分，口径（已确认）：
- 业务机会：以「可行动性(actionability)、差异化(differential)」为主，方向利好放大；
- 声誉风险：以「合规敏感度(compliance)、差异化(differential)」为主，命中红线不低于 60；
- 业务损失：以「受影响客户的金额额度」程度打分（贷款规模 + 他行贷款），
  有客户按所影响客户金额，无客户按所有相关用户金额。

数据基于合成客户数据集，非真实客户信息。
"""
from __future__ import annotations

from app.domain.exposure import load_customers

# 方向 → 各维度的放大/收缩因子（已确认口径）
_BUSINESS_OPPORTUNITY_FACTOR = {"positive": 1.0, "mixed": 0.85, "neutral": 0.75, "negative": 0.6}
_BUSINESS_LOSS_FACTOR = {"negative": 1.0, "mixed": 0.8, "neutral": 0.6, "positive": 0.4}

# 受影响客户金额（亿元）→ 0~100 程度分：分段线性插值，>50 亿封顶 100（已确认口径）
_AMOUNT_BREAKPOINTS = [(0.0, 0.0), (1.0, 20.0), (5.0, 40.0), (20.0, 60.0), (50.0, 80.0)]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(value))))


def _dim(scores: dict | None, key: str) -> float:
    """取四维分数（0–5），支持 {dim: score} 或 {dim: {"score": score}} 两种结构，缺失/None 按 0。"""
    if not scores:
        return 0.0
    value = scores.get(key)
    if isinstance(value, dict):
        value = value.get("score")
    if value is None:
        return 0.0
    try:
        return max(0.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _amount_to_score(amount_cny_yi: float) -> int:
    """金额额度（亿元）→ 0~100 程度分，分段线性插值，>50 亿封顶 100。"""
    if amount_cny_yi <= 0:
        return 0
    for (lo, s_lo), (hi, s_hi) in zip(_AMOUNT_BREAKPOINTS, _AMOUNT_BREAKPOINTS[1:]):
        if amount_cny_yi <= hi:
            ratio = (amount_cny_yi - lo) / (hi - lo)
            return _clamp(s_lo + (s_hi - s_lo) * ratio)
    return 100


def affected_amount_by_business_lines(
    business_lines: list[str] | None,
    customers: list[dict] | None = None,
) -> tuple[float, int]:
    """按业务线匹配合成客户，返回 (金额合计亿元, 客户数)；无匹配/无业务线时退回全量客户。"""
    customers = customers if customers is not None else load_customers()
    if not customers:
        return 0.0, 0
    lines = {line for line in (business_lines or []) if line}
    matched = [c for c in customers if c.get("business_line") in lines] if lines else []
    if not matched:
        matched = customers  # 没有客户/无匹配 → 所有相关用户
    total = sum(
        float(c.get("loan_balance_cny_yi", 0) or 0) + float(c.get("other_bank_loans_cny_yi", 0) or 0)
        for c in matched
    )
    return round(total, 2), len(matched)


def matched_customers(
    business_lines: list[str] | None,
    customers: list[dict] | None = None,
) -> list[dict]:
    """按政策业务线匹配全量合成客户（不按客户经理归属过滤）。

    政策运营专员查看使用者影响报告时需要看到「政策影响到的所有客户」，
    因此这里以合成客户数据集为准做全量匹配，按贷款规模倒序返回。
    """
    customers = customers if customers is not None else load_customers()
    lines = {line for line in (business_lines or []) if line}
    matched = [c for c in customers if not lines or c.get("business_line") in lines]
    return sorted(matched, key=lambda c: -float(c.get("loan_balance_cny_yi", 0) or 0))


def customer_impact_rows(
    customers: list[dict],
    scores: dict | None = None,
    *,
    direction: str | None = "neutral",
) -> list[dict]:
    """把合成客户记录转换成前端可直接展示的受影响客户行（含具体影响）。"""
    return [
        {
            "customer_id": c["customer_id"],
            "name_masked": c["name_masked"],
            "business_line": c["business_line"],
            "segment": c.get("segment", ""),
            "loan_balance_cny_yi": c.get("loan_balance_cny_yi", 0),
            "other_bank_loans_cny_yi": c.get("other_bank_loans_cny_yi", 0),
            "overseas_business": c.get("overseas_business", []),
            "impact": compute_customer_impact(c, scores, direction=direction),
        }
        for c in customers
    ]


def has_no_direct_impact(scores: dict | None) -> bool:
    """规则/模型是否明确判定「本行不在适用范围内且无红线、无差异化条款」。

    相关度为 0 表示政策原文未提及汇丰两个目标实体，此时若也没有合规红线与
    外资行差异条款，就不存在可评估的直接冲击：金额档位分档不应再凭空算出
    业务损失（否则所有无关政策会共享同一组分数）。
    """
    return (
        _dim(scores, "relevance") <= 0
        and _dim(scores, "compliance") <= 0
        and _dim(scores, "differential") <= 0
    )


def compute_consumer_impact(
    scores: dict | None = None,
    *,
    direction: str | None = "neutral",
    affected_amount_cny_yi: float = 0.0,
    affected_customer_count: int = 0,
) -> dict:
    """计算三个影响维度评分（0–100 程度分）与综合影响分。

    scores：四维 {exposure, actionability, differential, compliance}（0–5 或 None）。
    direction：positive/negative/mixed/neutral。
    """
    direction = direction or "neutral"
    if has_no_direct_impact(scores):
        # 本行不在适用范围内：三维度归零，而不是按金额档位给出同一档"损失"
        return {
            "business_loss": 0,
            "business_opportunity": 0,
            "reputation_risk": 0,
            "impact_total": 0,
            "affected_customer_count": int(affected_customer_count or 0),
            "no_direct_impact": True,
        }
    actionability = _dim(scores, "actionability")
    differential = _dim(scores, "differential")
    compliance = _dim(scores, "compliance")

    business_opportunity = _clamp(
        (actionability * 0.6 + differential * 0.4) / 5 * 100
        * _BUSINESS_OPPORTUNITY_FACTOR.get(direction, 0.75)
    )

    reputation_risk = _clamp((compliance * 0.6 + differential * 0.4) / 5 * 100)
    if compliance >= 4:
        reputation_risk = max(reputation_risk, 60)

    business_loss = _clamp(
        _amount_to_score(affected_amount_cny_yi)
        * _BUSINESS_LOSS_FACTOR.get(direction, 0.6)
    )

    impact_total = _clamp((business_loss + business_opportunity + reputation_risk) / 3)

    return {
        "business_loss": business_loss,
        "business_opportunity": business_opportunity,
        "reputation_risk": reputation_risk,
        "impact_total": impact_total,
        "affected_customer_count": int(affected_customer_count or 0),
    }


def compute_customer_impact(
    customer: dict,
    scores: dict | None = None,
    *,
    direction: str | None = "neutral",
) -> dict:
    """单个客户的具体影响：影响内容、三维度、可能收益或损失。"""
    direction = direction or "neutral"
    loan = float(customer.get("loan_balance_cny_yi", 0) or 0)
    other = float(customer.get("other_bank_loans_cny_yi", 0) or 0)
    overseas = customer.get("overseas_business") or []
    total_exposure = loan + other

    # 业务损失按该客户金额额度分档；业务机会/声誉风险继承政策级四维结论
    business_loss = _clamp(_amount_to_score(total_exposure) * _BUSINESS_LOSS_FACTOR.get(direction, 0.6))
    actionability = _dim(scores, "actionability")
    differential = _dim(scores, "differential")
    compliance = _dim(scores, "compliance")
    business_opportunity = _clamp(
        (actionability * 0.6 + differential * 0.4) / 5 * 100
        * _BUSINESS_OPPORTUNITY_FACTOR.get(direction, 0.75)
    )
    reputation_risk = _clamp((compliance * 0.6 + differential * 0.4) / 5 * 100)
    if compliance >= 4:
        reputation_risk = max(reputation_risk, 60)

    if direction == "positive":
        outcome = f"潜在业务机会约 {business_opportunity} 分（满分 100）"
    elif direction == "negative":
        outcome = f"潜在业务损失约 {business_loss} 分（满分 100）"
    else:
        outcome = "影响中性，需结合具体业务评估"

    impact_content = (
        f"贷款规模 {loan} 亿元、他行贷款 {other} 亿元"
        + (f"，涉及{'、'.join(overseas)}等海外业务" if overseas else "")
    )

    return {
        "impact_content": impact_content,
        "business_loss": business_loss,
        "business_opportunity": business_opportunity,
        "reputation_risk": reputation_risk,
        "outcome": outcome,
    }

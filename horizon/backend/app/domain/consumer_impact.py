"""政策使用者视角的影响维度评分（金钱损失 / 业务机会 / 声誉损失）。

基于政策影响方向 + 客户经理所管理客户的合成数据聚合（贷款规模、他行贷款、
海外业务类型），给出 0–100 的三个影响维度分与一个综合影响分。
"""
from __future__ import annotations

from app.domain.exposure import load_customers

# 方向 → (金钱损失系数, 业务机会系数, 声誉损失系数)
_DIRECTION_COEFF = {
    "positive": (0.4, 1.0, 0.3),
    "negative": (1.0, 0.3, 1.0),
    "mixed": (0.6, 0.6, 0.6),
    "neutral": (0.3, 0.3, 0.3),
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(value))))


def compute_consumer_impact(direction: str | None) -> dict:
    """计算三个影响维度评分。数据基于合成客户数据集，非真实客户信息。"""
    customers = load_customers()
    if not customers:
        return {
            "money_loss": 0, "business_opportunity": 0, "reputation_loss": 0,
            "impact_total": 0, "affected_customer_count": 0,
        }

    total_loan = sum(float(c.get("loan_balance_cny_yi", 0) or 0) for c in customers)
    total_other = sum(float(c.get("other_bank_loans_cny_yi", 0) or 0) for c in customers)
    overseas_count = sum(1 for c in customers if c.get("overseas_business"))

    coeff = _DIRECTION_COEFF.get(direction or "neutral", _DIRECTION_COEFF["neutral"])

    # 金钱损失：贷款规模（本行 + 他行）归一化（满量程 100 亿）× 方向系数
    money_loss = _clamp(min(total_loan + total_other, 100) * coeff[0])
    # 业务机会：有海外业务的客户占比 × 方向系数
    business_opportunity = _clamp(overseas_count / len(customers) * 100 * coeff[1])
    # 声誉损失：固定基础 40 × 方向系数
    reputation_loss = _clamp(40 * coeff[2])
    impact_total = _clamp((money_loss + business_opportunity + reputation_loss) / 3)

    return {
        "money_loss": money_loss,
        "business_opportunity": business_opportunity,
        "reputation_loss": reputation_loss,
        "impact_total": impact_total,
        "affected_customer_count": len(customers),
    }


def compute_customer_impact(customer: dict, direction: str | None) -> dict:
    """单个客户的具体影响：影响内容、影响维度、可能收益或损失。"""
    coeff = _DIRECTION_COEFF.get(direction or "neutral", _DIRECTION_COEFF["neutral"])
    loan = float(customer.get("loan_balance_cny_yi", 0) or 0)
    other = float(customer.get("other_bank_loans_cny_yi", 0) or 0)
    overseas = customer.get("overseas_business") or []

    total_exposure = loan + other
    money_loss = round(total_exposure * coeff[0], 2)
    business_opportunity = round(total_exposure * coeff[1] * (1.5 if overseas else 1.0), 2)
    reputation_loss = _clamp(40 * coeff[2])

    if direction == "positive":
        outcome = f"潜在业务机会约 {business_opportunity} 亿元"
    elif direction == "negative":
        outcome = f"潜在金钱损失约 {money_loss} 亿元"
    else:
        outcome = "影响中性，需结合具体业务评估"

    impact_content = (
        f"贷款规模 {loan} 亿元、他行贷款 {other} 亿元"
        + (f"，涉及{'、'.join(overseas)}等海外业务" if overseas else "")
    )

    return {
        "impact_content": impact_content,
        "money_loss": money_loss,
        "business_opportunity": business_opportunity,
        "reputation_loss": reputation_loss,
        "outcome": outcome,
    }

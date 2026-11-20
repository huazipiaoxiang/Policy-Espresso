"""政策影响的确定性口径：客户统计、政策卡片与使用者报告汇总。

被 HTTP 接口（政策详情/跟进邮件）与 Chat 管理员任务（生成影响报告）共用，
避免同一口径在两处各写一遍导致数字打架。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assessment, ConsumerReport, Document, Policy
from app.domain.consumer_impact import customer_impact_rows, matched_customers
from app.domain.exposure import load_customers


def affected_customer_stats(db: Session, policy: Policy) -> dict:
    """政策影响到的全部客户统计（客户库全量口径，与使用者客户归属无关）。"""
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    scores = assessment.scores if assessment else None
    direction = assessment.direction if assessment else None
    business_lines = (assessment.affected.get("business_lines", []) if assessment else []) or []
    rows = customer_impact_rows(
        matched_customers(business_lines, load_customers()), scores, direction=direction
    )

    by_line: dict[str, dict] = {}
    by_segment: dict[str, dict] = {}
    loan_total = 0.0
    other_total = 0.0
    overseas_count = 0
    for row in rows:
        line = row["business_line"] or "未标注"
        line_bucket = by_line.setdefault(
            line, {"business_line": line, "customers": 0, "loan_balance_cny_yi": 0.0}
        )
        line_bucket["customers"] += 1
        segment = row.get("segment") or "未标注客群"
        segment_bucket = by_segment.setdefault(
            segment, {"segment": segment, "customers": 0, "loan_balance_cny_yi": 0.0}
        )
        segment_bucket["customers"] += 1
        loan = float(row.get("loan_balance_cny_yi") or 0)
        other = float(row.get("other_bank_loans_cny_yi") or 0)
        loan_total += loan
        other_total += other
        line_bucket["loan_balance_cny_yi"] = round(line_bucket["loan_balance_cny_yi"] + loan, 2)
        segment_bucket["loan_balance_cny_yi"] = round(segment_bucket["loan_balance_cny_yi"] + loan, 2)
        if row.get("overseas_business"):
            overseas_count += 1

    sorted_lines = sorted(by_line.values(), key=lambda item: -item["loan_balance_cny_yi"])
    sorted_segments = sorted(by_segment.values(), key=lambda item: -item["loan_balance_cny_yi"])

    return {
        "direction": direction,
        "business_lines": sorted(business_lines),
        "match_rule": (
            f"按政策受影响业务线（{'、'.join(sorted(business_lines))}）匹配客户库全部客户"
            if business_lines else "政策未标注业务线，按客户库全部客户统计"
        ),
        "total_customers": len(rows),
        "loan_balance_total_cny_yi": round(loan_total, 2),
        "other_bank_loans_total_cny_yi": round(other_total, 2),
        "overseas_customers": overseas_count,
        "by_business_line": sorted_lines,
        "by_segment": sorted_segments,
        # 概况表先给前 10 户（按贷款规模），完整名单在 customers 里
        "top_customers": rows[:10],
        "customers": rows,
        "source": "seed/synthetic_customers.json（合成演示数据，非真实客户）",
    }


def followup_policy_card(db: Session, policy: Policy) -> dict:
    """交给跟进 Agent 的政策卡片：只包含政策字段与 AI 分析结论。"""
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    document = db.get(Document, policy.document_id)
    return {
        "id": policy.id,
        "title": policy.title,
        "doc_number": policy.doc_number,
        "issuing_body": policy.issuing_body,
        "jurisdiction": policy.jurisdiction,
        "policy_type": policy.policy_type,
        "priority": policy.priority,
        "score_total": policy.score_total,
        "confidence": policy.confidence,
        "summary_zh": policy.summary_zh,
        "themes": policy.themes,
        "published_at": policy.published_at.date().isoformat() if policy.published_at else "",
        "effective_at": policy.effective_at.date().isoformat() if policy.effective_at else "",
        "url": document.url if document else "",
        "direction": assessment.direction if assessment else "",
        "transmission_chain": assessment.transmission_chain if assessment else [],
        "recommended_actions": assessment.recommended_actions if assessment else [],
        "affected": assessment.affected if assessment else {},
    }


def followup_report_summary(db: Session, policy_id: str) -> dict:
    """使用者影响报告汇总（份数 / 待跟进 / 涉及客户），供跟进 Agent 组织结论。"""
    reports = db.scalars(
        select(ConsumerReport)
        .where(ConsumerReport.policy_id == policy_id)
        .order_by(ConsumerReport.created_at.desc())
    ).all()
    customer_ids: set[str] = set()
    for report in reports:
        for customer in (report.report or {}).get("affected_customers") or []:
            if isinstance(customer, dict) and customer.get("customer_id"):
                customer_ids.add(str(customer["customer_id"]))
    return {
        "count": len(reports),
        "pending": sum(1 for report in reports if report.status != "processed"),
        "processed": sum(1 for report in reports if report.status == "processed"),
        "customers": len(customer_ids),
        "latest_at": reports[0].created_at.isoformat() if reports else None,
    }

#!/usr/bin/env python3
"""把 mock 样例应答写出的政策内容，就地改为按原文派生的离线规则结果。

背景：LLM_PROVIDER=mock 时，MockProvider 对任意输入返回同一份样例应答
（tests/fixtures/mock_responses/*.json 的 `__default__`），于是抓取到的每篇文档
都被写成《关于做好中小微企业贷款贴息工作的通知》、同一份金额/期限/市场。
本脚本用 app.domain.offline_fallback（与 LLM_OFFLINE_RULES=true 的管线同一套规则）
重算内容字段，并保持审核流程不动：状态、优先级、影响分、审核任务与发布记录全部原样保留。

用法：
    python deploy/scripts/repair_mock_fixture_policies.py [--db ../backend/horizon.db] [--dry-run] [--limit N]

只处理 prompt_version 仍为 mock 链路（classify@v1+extract@v1+scope@v1）的政策，可重复执行。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(BACKEND_DIR / "horizon.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条（抽样核对用）")
    parser.add_argument("--rederive", action="store_true",
                        help="同时重算已修复过的政策（prompt_version 以 offline-rules 开头），用于调整规则后刷新")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"数据库不存在：{db_path}")
        return 2
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import delete, or_, select

    from app.ai.evidence import locate_quote
    from app.db.models import (
        Alert, Assessment, AuditLog, Document, Evidence, Policy, ScopeJudgement,
    )
    from app.db.session import SessionLocal
    from app.domain import offline_fallback
    from app.domain.case_match import match_cases
    from app.domain.scoring import DIMENSIONS
    from app.domain.scope_rules import detect_scope

    mock_prompt_version = "classify@v1+extract@v1+scope@v1"

    def rule_evidence(policy_id: str, doc: Document, rule) -> list[Evidence]:
        rows = []
        for hit in rule.hits[:5]:
            span = locate_quote(doc.content_text or "", hit.quote)
            if not span:
                continue
            rows.append(Evidence(
                policy_id=policy_id, document_id=doc.id, span_start=span[0], span_end=span[1],
                quote=hit.quote, field_name=f"scope.rule.{hit.category}",
            ))
        return rows

    def repair(policy: Policy, doc: Document, *, reset_assessment: bool) -> None:
        source = doc.source
        org = getattr(source, "org", "") or getattr(source, "name", "") or ""
        jurisdiction = (getattr(source, "jurisdiction", "") or "") or policy.jurisdiction

        e = offline_fallback.offline_extract(
            doc_title=doc.title or "", content_text=doc.content_text or "",
            source_name=org, jurisdiction=jurisdiction,
        )
        rule = detect_scope(doc.content_text or "")
        s = offline_fallback.offline_scope(rule)
        relevance = {r["entity_id"]: r["relevance"] for r in s["results"]}

        policy.title = e["title"] or doc.title or policy.title
        policy.issuing_body = ", ".join(e["issuing_bodies"])
        policy.jurisdiction = jurisdiction
        policy.policy_type = e["policy_type"]
        policy.themes = e["themes"]
        policy.summary_zh = e["summary_zh"]
        policy.applicable_scope = "unclear"
        policy.applicable_entities_text = ""
        policy.doc_number = None
        policy.published_at = doc.published_at
        policy.effective_at = None
        policy.expiry_at = None
        policy.amounts, policy.deadlines, policy.obligations, policy.incentives = [], [], [], []
        policy.confidence = 0.0
        kept = f"（状态、优先级 {policy.priority} 与影响分 {policy.score_total} 保持不变）"
        policy.prompt_version = f"offline-rules@v1{kept}" if not reset_assessment else "offline-rules@v1"
        policy.foreign_bank_differential = bool(s["foreign_bank_differential"])
        policy.group_affiliate_mention = s["group_affiliate_mention"]
        primary = "hsbc_hk" if jurisdiction in ("HK", "MO") else "hsbc_cn"
        policy.target_entity_status = relevance.get(primary, "not_mentioned")

        judgement = db.scalar(select(ScopeJudgement).where(
            ScopeJudgement.policy_id == policy.id, ScopeJudgement.entity_id == primary))
        if judgement:
            judgement.result = policy.target_entity_status
            judgement.rule_hits = [{"category": h.category, "quote": h.quote,
                                    "span_start": h.span_start, "span_end": h.span_end} for h in rule.hits[:5]]
            judgement.llm_reason = "未接入 AI 分析；适用范围取自规则通道"
            judgement.conflict = False

        db.execute(delete(Evidence).where(Evidence.policy_id == policy.id))
        for row in rule_evidence(policy.id, doc, rule):
            db.add(row)

        assessment = db.scalar(select(Assessment).where(Assessment.policy_id == policy.id))
        if assessment:
            hits = match_cases(db, themes=policy.themes, text=doc.content_text or "")
            assessment.case_links = [
                {"case_id": h.case_id, "similarity": h.similarity,
                 "takeaway": "；".join(h.lessons[:2]) or "同类先例"}
                for h in hits[:3]
            ]
            assessment.model = "offline-rules"
            assessment.prompt_version = "offline@v1"
            if reset_assessment and policy.status != "published":
                # mock 打分从未由人工确认，直接归零：缺证据维度置 None → 综合分 0 / P3
                assessment.scores = {dim: {"score": None, "reason": "未接入 AI 分析，需人工评定",
                                           "evidence_ids": []} for dim in DIMENSIONS}
                assessment.direction = "neutral"
                assessment.score_total = 0.0
                assessment.priority = "P3"
                assessment.transmission_chain = []
                assessment.recommended_actions = []
                assessment.affected = {
                    "business_lines": offline_fallback.affected_business_lines(policy.themes),
                    "segments": [],
                    "exposure_range": None,
                }
                assessment.confidence = 0.0
                policy.score_total = 0.0
                policy.priority = "P3"
            else:
                # 影响分保持原值，但逐维理由改为"未经 AI 评定"，避免被当作模型结论
                previous = assessment.scores or {}
                assessment.scores = {
                    dim: {"score": (previous.get(dim) or {}).get("score"),
                          "reason": "未接入 AI 分析，需人工评定", "evidence_ids": []}
                    for dim in DIMENSIONS
                }
            alert = db.scalar(select(Alert).where(Alert.assessment_id == assessment.id))
            if alert:
                alert.title = f"政策预警草稿 · {policy.title}"
                alert.body_md = offline_fallback.offline_alert(policy, relevance)
                if reset_assessment and policy.status != "published":
                    alert.status = "draft"

        db.add(AuditLog(
            actor="system.horizon", action="repair_fixture_content", object_type="policy",
            object_id=policy.id, before={"prompt_version": mock_prompt_version},
            after={"title": policy.title, "jurisdiction": policy.jurisdiction, "themes": policy.themes},
            reason="mock 样例内容替换为按原文派生的离线规则结果；状态、优先级与评分保持不变",
        ))

    with SessionLocal() as db:
        version_filter = (Policy.prompt_version == mock_prompt_version) if not args.rederive else or_(
            Policy.prompt_version == mock_prompt_version,
            Policy.prompt_version.like("offline-rules@v1%"),
        )
        stmt = select(Policy, Document).join(Document, Policy.document_id == Document.id).where(version_filter)
        if args.limit:
            stmt = stmt.limit(args.limit)
        rows = db.execute(stmt).all()
        print(f"待修复政策：{len(rows)} 条（rederive={args.rederive}）")
        for policy, doc in rows[:5]:
            print(f"  原文《{(doc.title or '')[:34]}》 现标题《{policy.title[:34]}》 "
                  f"市场 {policy.jurisdiction} 状态 {policy.status}")
        if args.dry_run:
            print("dry-run：不写库")
            return 0
        for policy, doc in rows:
            repair(policy, doc, reset_assessment=bool(args.rederive and policy.status != "published"))
        db.add(AuditLog(
            actor="system.horizon", action="repair_fixture_content_batch", object_type="system",
            object_id="policy", before={}, after={"repaired": len(rows)},
            reason=f"批量修复完成于 {datetime.now(timezone.utc).isoformat()}"))
        db.commit()
        print(f"已修复 {len(rows)} 条；状态、优先级、评分、审核与发布记录未改动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

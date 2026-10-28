#!/usr/bin/env python3
"""就地重算"八维评分卡"为占位理由的政策评估（发布状态与审核记录保持不变）。

背景：repair_mock_fixture_policies.py 修复 mock 样例政策时，为保持"状态、优先级与
影响分不变"，把已发布政策的评分维度理由统一替换为"未接入 AI 分析，需人工评定"，
分数仍是 mock 样例应答的旧值（与原文无关）。本脚本用当前离线规则
（app.domain.offline_fallback，与 LLM_OFFLINE_RULES=true 管线同一套规则）重算
评分卡分数、理由、影响分、优先级、传导路径、建议动作与预警草稿，
并同步相关性判定（ScopeJudgement）与 Policy.score_total/priority/confidence，
不动 published 状态、审核任务与审核决定，只补一条审计记录。

只处理每个维度理由均为占位文本的评估，可重复执行（刷新后不再命中）。

用法：
    python deploy/scripts/refresh_published_scorecards.py [--db ../backend/horizon.db] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

PLACEHOLDER = "未接入 AI 分析，需人工评定"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(BACKEND_DIR / "horizon.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"数据库不存在：{db_path}")
        return 2
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy import select

    from app.db.models import Alert, Assessment, AuditLog, Document, Policy, ScopeJudgement
    from app.db.session import SessionLocal
    from app.domain import offline_fallback, scoring
    from app.domain.case_match import match_cases
    from app.domain.exposure import aggregate_exposure
    from app.domain.scope_rules import detect_scope

    with SessionLocal() as db:
        candidates = []
        for assessment in db.scalars(select(Assessment)).all():
            reasons = [v.get("reason", "") for v in (assessment.scores or {}).values()]
            if reasons and all(r == PLACEHOLDER for r in reasons):
                candidates.append(assessment)
        print(f"占位评分卡评估：{len(candidates)} 条")
        for assessment in candidates:
            policy = db.get(Policy, assessment.policy_id)
            print(f"  {policy.id} 状态 {policy.status} 影响分 {policy.score_total} "
                  f"优先级 {policy.priority}《{(policy.title or '')[:30]}》")
        if args.dry_run:
            print("dry-run：不写库")
            return 0

        refreshed = 0
        for assessment in candidates:
            policy = db.get(Policy, assessment.policy_id)
            doc = db.get(Document, policy.document_id)
            if doc is None:
                print(f"跳过（无原文）：{policy.id}")
                continue

            rule = detect_scope(doc.content_text or "")
            s = offline_fallback.offline_scope(rule)
            entity_relevance = {
                r["entity_id"]: r["relevance"]
                for r in s["results"]
                if r.get("entity_id") in ("hsbc_hk", "hsbc_cn")
            }

            # 同步相关性判定（analyze_job 离线模式同款：result 取规则通道结论，冲突恒为 False）
            for entity_id in ("hsbc_hk", "hsbc_cn"):
                llm_r = next((r for r in s["results"] if r.get("entity_id") == entity_id), {})
                judgement = db.scalar(select(ScopeJudgement).where(
                    ScopeJudgement.policy_id == policy.id, ScopeJudgement.entity_id == entity_id))
                if judgement:
                    judgement.result = llm_r.get("relevance", "not_mentioned")
                    judgement.rule_hits = [{"category": h.category, "quote": h.quote,
                                            "span_start": h.span_start, "span_end": h.span_end}
                                           for h in rule.hits[:5]]
                    judgement.llm_reason = llm_r.get("reason", "")
                    judgement.conflict = False

            e = offline_fallback.offline_extract(
                doc_title=doc.title or "", content_text=doc.content_text or "",
                source_name=getattr(doc.source, "org", "") or getattr(doc.source, "name", "") or "",
                jurisdiction=policy.jurisdiction or "",
            )
            exposure = aggregate_exposure(
                policy.themes,
                [t.get("name", "") for t in (e.get("targets") or []) if isinstance(t, dict)],
            )
            impact = offline_fallback.offline_impact(
                policy.themes,
                relevance_by_entity=entity_relevance,
                policy_type=policy.policy_type,
                effective_at=policy.effective_at,
                foreign_bank_differential=bool(policy.foreign_bank_differential),
                differential_quotes=[h.quote for h in rule.hits if h.category == "low"],
                exposure=exposure,
            )

            raw_scores = impact.get("scores") or {}
            dim_scores = {dim: (raw_scores.get(dim) or {}).get("score") for dim in scoring.DIMENSIONS}
            if policy.policy_type == "consultation" and dim_scores.get("certainty") is not None:
                dim_scores["certainty"] = min(dim_scores["certainty"], 3)
            result = scoring.compute_score(dim_scores, direction=impact.get("direction", "neutral"))

            hits = match_cases(db, themes=policy.themes, text=doc.content_text or "")
            similar_cases = [
                {"case_id": h.case_id, "title": h.title, "similarity": h.similarity,
                 "themes": h.themes, "lessons": h.lessons}
                for h in hits
            ]
            valid_ids = {c["case_id"] for c in similar_cases}
            case_links = [cl for cl in (impact.get("case_links") or []) if cl.get("case_id") in valid_ids]
            if not case_links and similar_cases:
                case_links = [{"case_id": similar_cases[0]["case_id"],
                               "similarity": similar_cases[0]["similarity"],
                               "takeaway": "；".join(similar_cases[0]["lessons"][:2]) or "同类先例"}]

            affected = dict(impact.get("affected") or {})
            affected["exposure_range"] = affected.get("exposure_range") or exposure

            null_dims = [d for d, v in dim_scores.items() if v is None]
            confidence = float(impact.get("confidence", 0.0))
            if len(null_dims) >= 5:
                confidence = min(confidence, 0.3)

            before = {
                "score_total": policy.score_total, "priority": policy.priority,
                "confidence": policy.confidence,
                "assessment_score_total": assessment.score_total,
                "assessment_priority": assessment.priority,
            }
            assessment.scores = {
                dim: {"score": dim_scores[dim],
                      "reason": (raw_scores.get(dim) or {}).get("reason", ""),
                      "evidence_ids": []}
                for dim in scoring.DIMENSIONS
            }
            assessment.direction = impact.get("direction", "neutral")
            assessment.score_total = result.score_total
            assessment.priority = result.priority
            assessment.transmission_chain = impact.get("transmission_chain") or []
            assessment.affected = affected
            assessment.recommended_actions = impact.get("recommended_actions") or []
            assessment.case_links = case_links
            assessment.confidence = confidence
            assessment.model = "offline-rules"
            assessment.prompt_version = "offline@v1"

            policy.score_total = result.score_total
            policy.priority = result.priority
            policy.confidence = confidence  # 与 analyze_job 离线回写一致
            policy.prompt_version = "offline-rules@v1"

            alert = db.scalar(select(Alert).where(Alert.assessment_id == assessment.id))
            if alert:
                alert.title = f"政策预警草稿 · {policy.title}"
                alert.body_md = offline_fallback.offline_alert(policy, entity_relevance)

            db.add(AuditLog(
                actor="system.horizon", action="refresh_scorecard", object_type="policy",
                object_id=policy.id, before=before,
                after={"score_total": policy.score_total, "priority": policy.priority,
                       "confidence": policy.confidence},
                reason="按当前离线规则重算八维评分卡（分数、理由、影响分与优先级）；发布状态与审核记录保持不变",
            ))
            refreshed += 1
            print(f"刷新 {policy.id}：{before['score_total']}/{before['priority']} → "
                  f"{policy.score_total}/{policy.priority}，置信度 {confidence}")
        db.commit()
        print(f"完成：刷新 {refreshed} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

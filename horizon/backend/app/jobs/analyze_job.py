"""分析任务（01 §五 Phase 2 段）：

document(status=new, 非重复, 有正文)
 → P1 分类（非金融/低置信 → processed 跳过）
 → P2 抽取 → Policy + Evidence（证据 span 全部可定位）
 → P3 适用范围（规则 + LLM 双通道，冲突记 needs_review）
 → 案例匹配 + 业务图谱 + 暴露聚合 → P4 影响分析（8 维 + 评分卡）
 → P5 预警草稿 → Alert(draft)
 → policy → pending_review + ReviewTask（SLA 按优先级）

幂等：同 document 重复分析先清旧 assessment/evidence/task 再重建（重跑分析语义）。
失败模式：Provider/链路异常 → document.status=failed。
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chains.alert import AlertChain, validate_alert_md
from app.ai.chains.classify import ClassifyChain
from app.ai.chains.extract import ExtractChain
from app.ai.chains.impact import ImpactChain
from app.ai.chains.scope import ScopeChain
from app.ai.evidence import locate_quote
from app.core.logging import get_logger
from app.db.models import (
    Alert, Assessment, AuditLog, Document, Evidence, LLMCallLog, Policy,
    ReviewTask, ScopeJudgement,
)
from app.domain import scoring, state_machine
from app.domain.business_map import slice_for_themes
from app.domain.case_match import match_cases
from app.domain.exposure import aggregate_exposure
from app.domain.scope_rules import detect_scope, entity_relevance_from_scope

log = get_logger("jobs.analyze")

SLA_HOURS = {"P0": 4, "P1": 24, "P2": 72, "P3": 72}
HK_OFFSET = timedelta(hours=8)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m:
        return None
    try:
        return datetime.combine(
            datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date(),
            time.min, tzinfo=timezone(HK_OFFSET),
        ).astimezone(timezone.utc)
    except ValueError:
        return None


def _log_llm(db: Session, result, provider_name: str) -> None:
    db.add(LLMCallLog(
        provider=provider_name, model=result.model, task=result.task,
        prompt_version=result.prompt_version, input_hash=result.input_hash,
        tokens_in=int((result.usage or {}).get("prompt_tokens", 0)),
        tokens_out=int((result.usage or {}).get("completion_tokens", 0)),
        latency_ms=result.latency_ms, status="ok",
    ))


def _audit(db: Session, action: str, obj_type: str, obj_id: str, before: dict, after: dict, reason: str = "") -> None:
    db.add(AuditLog(actor="system.horizon", action=action, object_type=obj_type, object_id=obj_id,
                    before=before, after=after, reason=reason))


def analyze_document(db: Session, doc: Document) -> Policy | None:
    """分析单篇文档。返回 Policy 或 None（非金融/低置信/无正文）。"""
    from app.ai.provider import get_provider

    provider = get_provider()
    provider_name = provider.name

    if not doc.content_text or len(doc.content_text.strip()) < 50:
        doc.status = "needs_full_text"  # T1-N4：付费墙/仅标题，进待补资料
        db.commit()
        log.info("needs_full_text", doc_id=doc.id)
        return None

    # ---- P1 分类 ----
    classify = ClassifyChain(provider).run(title=doc.title, content_text=doc.content_text)
    _log_llm(db, classify, provider_name)
    db.commit()
    c = classify.parsed
    if not c.get("is_financial_policy") or float(c.get("confidence", 0)) < 0.6:
        doc.status = "processed"
        db.commit()
        log.info("not_financial_or_low_confidence", doc_id=doc.id, confidence=c.get("confidence"))
        return None

    # ---- P2 抽取 ----
    extract = ExtractChain(provider).run(content_text=doc.content_text)
    _log_llm(db, extract, provider_name)
    db.commit()
    e = extract.parsed

    # ---- P3 适用范围（规则 + LLM 双通道）----
    rule = detect_scope(doc.content_text)
    rule_hint = f"规则通道建议：{rule.relevance}；命中：{[h.quote for h in rule.hits[:5]]}"
    scope = ScopeChain(provider).run(content_text=doc.content_text, rule_hint=rule_hint)
    _log_llm(db, scope, provider_name)
    db.commit()
    s = scope.parsed

    jurisdiction = (c.get("jurisdictions") or [doc.source.jurisdiction if doc.source else ""])[0] or ""

    # 幂等：清旧分析产物
    existing = db.scalar(select(Policy).where(Policy.document_id == doc.id))
    if existing:
        db.query(Evidence).filter(Evidence.policy_id == existing.id).delete()
        db.query(Assessment).filter(Assessment.policy_id == existing.id).delete()
        db.query(ScopeJudgement).filter(ScopeJudgement.policy_id == existing.id).delete()
        db.query(ReviewTask).filter(ReviewTask.policy_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    policy = Policy(
        document_id=doc.id,
        title=e.get("title") or doc.title,
        issuing_body=", ".join(e.get("issuing_bodies") or []),
        doc_number=e.get("doc_number"),
        published_at=_parse_date(e.get("published_at")) or doc.published_at,
        effective_at=_parse_date(e.get("effective_at")),
        expiry_at=_parse_date(e.get("expiry_at")),
        jurisdiction=jurisdiction,
        policy_type=c.get("policy_type", "other"),
        themes=e.get("themes") or [],
        applicable_entities_text=e.get("applicable_entities_text") or "",
        applicable_scope=e.get("applicable_scope", "unclear"),
        amounts=e.get("amounts") or [],
        deadlines=e.get("deadlines") or [],
        obligations=e.get("obligations") or [],
        incentives=e.get("incentives") or [],
        summary_zh=e.get("summary_zh") or "",
        confidence=float(e.get("confidence", 0.0)),
        status="draft",
        priority="P3",
        prompt_version=f"{classify.prompt_version}+{extract.prompt_version}+{scope.prompt_version}",
    )
    db.add(policy)
    db.flush()  # policy.id 至此可用

    # 证据入库（span 已在链路内校验可定位）
    for item in extract.evidence:
        db.add(Evidence(
            policy_id=policy.id, document_id=doc.id, span_start=item["span_start"],
            span_end=item["span_end"], quote=item["quote"], field_name=item.get("field", ""),
        ))

    # 适用范围判定入库（每实体一行；规则/LLM 冲突记 conflict）
    entity_relevance: dict[str, str] = {}
    llm_by_entity = {r["entity_id"]: r for r in s.get("results", []) if r.get("entity_id") in ("hsbc_hk", "hsbc_cn")}
    for entity_id in ("hsbc_hk", "hsbc_cn"):
        llm_r = llm_by_entity.get(entity_id)
        llm_relevance = (llm_r or {}).get("relevance", "not_mentioned")
        rule_relevance = entity_relevance_from_scope(entity_id, rule.relevance)
        conflict = bool(rule.hits) and llm_relevance != rule_relevance
        db.add(ScopeJudgement(
            policy_id=policy.id, entity_id=entity_id, result=llm_relevance,
            rule_hits=[{"category": h.category, "quote": h.quote,
                        "span_start": h.span_start, "span_end": h.span_end} for h in rule.hits],
            llm_reason=(llm_r or {}).get("reason", ""), conflict=conflict,
        ))
        entity_relevance[entity_id] = llm_relevance

    # scope 链路证据入库（field=scope.{entity}）
    for r in s.get("results", []):
        for ev_item in r.get("evidence", []):
            span = locate_quote(doc.content_text, ev_item.get("quote", ""))
            if span:
                db.add(Evidence(
                    policy_id=policy.id, document_id=doc.id, span_start=span[0], span_end=span[1],
                    quote=ev_item["quote"], field_name=f"scope.{r.get('entity_id', '')}",
                ))

    primary = "hsbc_hk" if jurisdiction in ("HK", "MO") else "hsbc_cn"
    policy.target_entity_status = entity_relevance.get(primary, "not_mentioned")
    policy.foreign_bank_differential = bool(s.get("foreign_bank_differential"))
    policy.group_affiliate_mention = s.get("group_affiliate_mention") or rule.group_affiliate_mention

    # ---- P4 影响分析 ----
    hits = match_cases(db, themes=policy.themes, text=doc.content_text)
    similar_cases = [
        {"case_id": h.case_id, "title": h.title, "similarity": h.similarity,
         "themes": h.themes, "lessons": h.lessons}
        for h in hits
    ]
    exposure = aggregate_exposure(policy.themes, [t.get("name", "") for t in (e.get("targets") or []) if isinstance(t, dict)])
    policy_card = {
        "title": policy.title, "issuing_body": policy.issuing_body, "doc_number": policy.doc_number,
        "jurisdiction": policy.jurisdiction, "policy_type": policy.policy_type, "themes": policy.themes,
        "applicable_scope": policy.applicable_scope, "applicable_entities_text": policy.applicable_entities_text,
        "effective_at": policy.effective_at.date().isoformat() if policy.effective_at else None,
        "expiry_at": policy.expiry_at.date().isoformat() if policy.expiry_at else None,
        "amounts": policy.amounts, "deadlines": policy.deadlines, "obligations": policy.obligations,
        "incentives": policy.incentives, "summary_zh": policy.summary_zh,
    }
    scope_judgement = {
        "entity_relevance": entity_relevance,
        "foreign_bank_differential": policy.foreign_bank_differential,
        "differential_note": s.get("differential_note", ""),
        "group_affiliate_mention": policy.group_affiliate_mention,
        "ambiguity": s.get("ambiguity", []),
    }
    impact = ImpactChain(provider).run(
        content_text=doc.content_text, policy_card=policy_card, scope_judgement=scope_judgement,
        similar_cases=similar_cases, business_map_slice=slice_for_themes(policy.themes),
        exposure_context={"synthetic_exposure": exposure},
    )
    _log_llm(db, impact, provider_name)
    db.commit()
    i = impact.parsed

    raw_scores = i.get("scores") or {}
    dim_scores = {dim: (raw_scores.get(dim) or {}).get("score") for dim in scoring.DIMENSIONS}
    # 征求意见稿：certainty ≤3（T1-N3）
    if policy.policy_type == "consultation" and dim_scores.get("certainty") is not None:
        dim_scores["certainty"] = min(dim_scores["certainty"], 3)
    score_result = scoring.compute_score(dim_scores, direction=i.get("direction", "neutral"))

    # 案例链接校验：只保留库内存在且相似度 ≥0.6 的；匹配器命中而 LLM 漏引时补入
    valid_ids = {c["case_id"] for c in similar_cases}
    case_links = [cl for cl in (i.get("case_links") or []) if cl.get("case_id") in valid_ids]
    if not case_links and similar_cases:
        case_links = [{"case_id": similar_cases[0]["case_id"], "similarity": similar_cases[0]["similarity"],
                       "takeaway": "；".join(similar_cases[0]["lessons"][:2]) or "同类先例"}]

    affected = dict(i.get("affected") or {})
    exposure_range = affected.get("exposure_range") or exposure
    affected["exposure_range"] = exposure_range

    null_dims = [d for d, v in dim_scores.items() if v is None]
    assessment = Assessment(
        policy_id=policy.id,
        scores={dim: {"score": dim_scores[dim],
                      "reason": (raw_scores.get(dim) or {}).get("reason", ""),
                      "evidence_ids": []} for dim in scoring.DIMENSIONS},
        direction=i.get("direction", "neutral"),
        score_total=score_result.score_total,
        priority=score_result.priority,
        transmission_chain=i.get("transmission_chain") or [],
        affected=affected,
        recommended_actions=i.get("recommended_actions") or [],
        case_links=case_links,
        confidence=float(i.get("confidence", 0.0)),
        model=impact.model,
        prompt_version=impact.prompt_version,
    )
    if len(null_dims) >= 5:
        assessment.confidence = min(assessment.confidence, 0.3)  # low_confidence，不进审核队列
        log.info("assessment_low_confidence", policy_id=policy.id, null_dims=null_dims)
    db.add(assessment)

    policy.score_total = score_result.score_total
    policy.priority = score_result.priority
    policy.status = state_machine.transition(policy.status, "ai_checked")
    _audit(db, "ai_analyze", "policy", policy.id, {},
           {"status": policy.status, "score_total": policy.score_total, "priority": policy.priority},
           reason="AI 分析完成")
    db.flush()

    # ---- P5 预警草稿 ----
    assessment_view = {
        "scores": assessment.scores, "direction": assessment.direction,
        "score_total": assessment.score_total, "priority": assessment.priority,
        "transmission_chain": assessment.transmission_chain, "affected": assessment.affected,
        "recommended_actions": assessment.recommended_actions, "case_links": assessment.case_links,
        "unknowns": i.get("unknowns", []), "confidence": assessment.confidence,
    }
    alert_chain = AlertChain(provider).run(policy_card=policy_card, assessment=assessment_view)
    _log_llm(db, alert_chain, provider_name)
    errors = validate_alert_md(alert_chain.text)
    if errors:
        log.warning("alert_invalid", policy_id=policy.id, errors=errors)
    db.add(Alert(assessment_id=assessment.id, title=f"政策预警草稿 · {policy.title}",
                 body_md=alert_chain.text, channel_scope={"default": "inapp"}, status="draft"))

    # ---- 进审核队列（恒生仅点名等场景不产生预警/不进队列）----
    relevant = any(v in ("covered", "excluded") for v in entity_status.values())
    if relevant and assessment.confidence > 0.3:
        policy.status = state_machine.transition(policy.status, "pending_review")
        _audit(db, "submit_review", "policy", policy.id, {"status": "ai_checked"}, {"status": "pending_review"})
        db.add(ReviewTask(
            policy_id=policy.id, level=1, assignee="analyst.default",
            sla_due_at=datetime.now(timezone.utc) + timedelta(hours=SLA_HOURS[score_result.priority]),
            status="pending",
        ))
    else:
        _audit(db, "skip_review", "policy", policy.id, {"status": "ai_checked"},
               {"status": policy.status, "reason": "非覆盖/排除场景或低置信"},
               reason="不满足预警触发条件")

    doc.status = "processed"
    db.commit()
    log.info("analyzed", doc_id=doc.id, policy_id=policy.id, priority=policy.priority,
             score=policy.score_total, entity_status=entity_status)
    return policy


def analyze_pending(db: Session, *, limit: int = 10) -> dict:
    """处理待分析文档（scheduler analyze_pending 每 5 分钟）。"""
    docs = db.scalars(
        select(Document).where(Document.status == "new", Document.duplicate_of.is_(None)).limit(limit)
    ).all()
    stats = {"analyzed": 0, "skipped": 0, "failed": 0}
    for doc in docs:
        try:
            policy = analyze_document(db, doc)
            stats["analyzed" if policy else "skipped"] += 1
        except Exception as e:
            stats["failed"] += 1
            doc.status = "failed"
            db.commit()
            log.error("analyze_failed", doc_id=doc.id, error=f"{type(e).__name__}: {e}")
    return stats


def main() -> None:
    from app.core.logging import configure_logging
    from app.db.models import Base
    from app.db.session import SessionLocal, engine

    configure_logging()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = analyze_pending(db)
        print(f"分析完成：{stats}")


if __name__ == "__main__":
    main()

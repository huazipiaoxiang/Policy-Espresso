"""政策列表/详情/分发拦截。完整实现随 Phase 2/3 补齐；分发 409 硬规则已在此生效。"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.api.v1.schemas import Page, PolicyOut
from app.core.errors import ApiError, not_found, not_approved
from app.core.logging import get_logger
from app.core.security import get_demo_role, require_api_key, require_roles
from app.db.models import Alert, Assessment, ConsumerReport, Dispatch, Document, Evidence, Feedback, LLMCallLog, Policy, ReviewTask, ScopeJudgement
from app.db.session import get_db
from app.domain import state_machine
from app.domain.consumer_impact import (
    affected_amount_by_business_lines,
    compute_consumer_impact,
    customer_impact_rows,
)
from app.domain.policy_admin import delete_policy
from app.domain.policy_impact import (
    affected_customer_stats,
    followup_policy_card,
    followup_report_summary,
)

log = get_logger("policies")

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_api_key)])


class DigestBody(BaseModel):
    period: str = "week"  # week | month
    policy_ids: list[str] = []


class RecallBody(BaseModel):
    note: str = ""


class FeedbackBody(BaseModel):
    content: str


class ReportBody(BaseModel):
    feedback_id: str


def _policy_filters(
    stmt,
    *,
    q: str | None,
    status: str | None,
    status_not: str | None,
    priority: str | None,
    jurisdiction: str | None,
    theme: str | None,
    scope: str | None,
    fetched: str | None,
    published_on: str | None,
    role: str,
    review_level: int | None,
    irrelevant: bool | None = None,
):
    if q:
        search_pattern = f"%{q}%"
        stmt = stmt.where(
            (Policy.title.ilike(search_pattern)) |
            (Policy.issuing_body.ilike(search_pattern)) |
            (Policy.summary_zh.ilike(search_pattern))
        )
    if role == "consumer":
        stmt = stmt.where(Policy.status == "published")
    if status:
        statuses = [value.strip() for value in status.split(",") if value.strip()]
        stmt = stmt.where(Policy.status.in_(statuses))
    if status_not:
        excludes = [value.strip() for value in status_not.split(",") if value.strip()]
        stmt = stmt.where(Policy.status.notin_(excludes))
    if priority:
        priorities = [value.strip() for value in priority.split(",") if value.strip()]
        stmt = stmt.where(Policy.priority.in_(priorities))
    if jurisdiction:
        stmt = stmt.where(Policy.jurisdiction == jurisdiction)
    if theme:
        # themes 以 JSON 文本存储，中文可能被序列化成 \uXXXX 转义，两种写法都要匹配
        column = cast(Policy.themes, Text)
        escaped = json.dumps(theme, ensure_ascii=True)[1:-1]
        stmt = stmt.where(or_(column.like(f"%{theme}%"), column.like(f"%{escaped}%")))
    if scope:
        stmt = stmt.where(Policy.target_entity_status == scope)
    if fetched == "today":
        today_start = datetime.now(ZoneInfo("Asia/Hong_Kong")).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).astimezone(timezone.utc)
        stmt = stmt.join(Document, Policy.document_id == Document.id).where(Document.fetched_at >= today_start)
    if published_on:
        # 按「系统发布动作时间」（Dispatch.sent_at）过滤，而非政策官方发布日期：
        # 「今日已发布」的用户预期是今天执行了发布操作的政策。
        stmt = stmt.where(
            exists(
                select(Dispatch.id)
                .join(Alert, Alert.id == Dispatch.alert_id)
                .join(Assessment, Assessment.id == Alert.assessment_id)
                .where(
                    Assessment.policy_id == Policy.id,
                    func.date(Dispatch.sent_at) == published_on,
                )
            )
        )
    if review_level is not None:
        # 仅返回存在「该级别且待处理/已领取」审核任务的政策（用于审核员按级别看自己的待办）
        stmt = stmt.where(
            exists(
                select(ReviewTask.id).where(
                    ReviewTask.policy_id == Policy.id,
                    ReviewTask.level == review_level,
                    ReviewTask.status.in_(["pending", "claimed"]),
                )
            )
        )
    if irrelevant is not None:
        # 跟进中心：AI 判定「疑似完全无影响」待复核的政策
        stmt = stmt.where(Policy.irrelevant_flagged.is_(irrelevant))
    return stmt


def _policy_view(db: Session, policy: Policy) -> dict:
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    dispatched_at = db.scalar(
        select(func.max(Dispatch.sent_at))
        .join(Alert, Alert.id == Dispatch.alert_id)
        .join(Assessment, Assessment.id == Alert.assessment_id)
        .where(Assessment.policy_id == policy.id)
    )
    scores = assessment.scores if assessment else None
    direction = assessment.direction if assessment else None
    business_lines = [
        str(line)
        for line in (assessment.affected.get("business_lines", []) if assessment else [])
        if line
    ]
    if not business_lines:
        # 评估未标注业务线时按主题/关键词推断，避免政策库「影响 Domain」长期空白
        from app.domain.preprocess import infer_business_lines

        business_lines = infer_business_lines(policy)
    amount, count = affected_amount_by_business_lines(business_lines)
    return {
        **PolicyOut.model_validate(policy).model_dump(),
        "impacted_domains": business_lines,
        "dispatched_at": (dispatched_at.isoformat() if dispatched_at else None),
        "direction": direction,
        "followup": bool(policy.followup),
        "irrelevant_flagged": bool(policy.irrelevant_flagged),
        "impact_dimensions": compute_consumer_impact(
            scores, direction=direction,
            affected_amount_cny_yi=amount, affected_customer_count=count,
        ),
    }


@router.post("/digest")
def policy_digest(body: DigestBody, db: Session = Depends(get_db), role: str = Depends(get_demo_role)):
    """本周/本月与你相关的政策动态 AI 聚合（政策使用者首页）。

    输入按订阅偏好匹配出的政策清单，输出一段中文聚合速览；
    LLM 不可用时降级为规则拼接，不阻塞页面。
    """
    from app.ai.provider import get_provider

    stmt = select(Policy).where(Policy.status == "published")
    if body.policy_ids:
        stmt = stmt.where(Policy.id.in_(body.policy_ids[:50]))
    policies = db.scalars(stmt.order_by(Policy.published_at.desc().nullslast()).limit(30)).all()
    period_label = "本周" if body.period == "week" else "本月"
    if not policies:
        return {"digest_md": "", "policy_count": 0, "period": body.period}

    lines = []
    for policy in policies:
        date = policy.published_at.strftime("%Y-%m-%d") if policy.published_at else "日期未注明"
        summary = (policy.summary_zh or "").replace("\n", " ")[:120]
        lines.append(f"- {policy.title}（{policy.jurisdiction or '未注明'} · {date}）：{summary}")
    listing = "\n".join(lines)
    system = (
        "你是面向银行政策使用者的监管政策情报助理。基于给定的已发布政策清单，"
        "写一段简明中文聚合速览：先 2-3 句概括总体动态，再以『- 』列出 3-5 条要点，"
        "每条一句话并点出对银行业务最相关的影响。不要编造清单之外的信息，不要使用 markdown 标题。"
    )
    user = f"周期：{period_label}\n政策清单（{len(policies)} 条）：\n{listing}"
    model_name = ""
    try:
        result = get_provider().complete(system=system, user=user, schema=None, task="digest", max_tokens=700)
        digest = (result.text or "").strip()
        model_name = result.model or ""
    except Exception:
        digest = ""
    if not digest:
        digest = "AI 聚合暂时不可用，以下是本期与你相关的政策：\n" + "\n".join(
            f"- {policy.title}" for policy in policies[:5]
        )
        model_name = "规则兜底"
    return {"digest_md": digest, "policy_count": len(policies), "period": body.period, "model": model_name}


@router.get("", response_model=Page[PolicyOut])
def list_policies(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    status: str | None = None,
    status_not: str | None = None,
    priority: str | None = None,
    jurisdiction: str | None = None,
    theme: str | None = None,
    scope: str | None = None,
    fetched: str | None = None,
    published_on: str | None = None,
    review_level: int | None = None,
    irrelevant: bool | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
):
    filters = {
        "q": q, "status": status, "status_not": status_not, "priority": priority,
        "jurisdiction": jurisdiction, "theme": theme, "scope": scope, "fetched": fetched,
        "published_on": published_on, "role": role, "review_level": review_level,
        "irrelevant": irrelevant,
    }
    stmt = _policy_filters(select(Policy), **filters).order_by(Policy.published_at.desc().nullslast())
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    count_stmt = _policy_filters(select(func.count(Policy.id)), **filters)
    total = db.execute(count_stmt).scalar() or 0
    return Page(
        items=[_policy_view(db, policy) for policy in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/for-you")
def for_you(
    username: str | None = None,
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
) -> dict:
    """「为你推荐」：按政策预处理表格的三维分数降序返回本周新入库政策。

    规则 A：登录用户名匹配到客户经理（relationship_manager）→ 用其名下客户的敞口
            重算业务损失维度，其余维度沿用预处理结果；
    规则 B：未匹配（含没有客户的政策使用者）→ 直接使用预处理表格里的百分比，
            因此推荐不会因为缺少客户画像而为空。

    时间口径：与预处理表格「本周新入库」一致，取 PolicyPreprocess.created_at；
             本周没有新入库的已发布政策时，回退展示最近入库的已发布政策
             （window="all"），保证推荐列表不为空。
    """
    from app.db.models import PolicyPreprocess
    from app.domain.preprocess import normalize_research_items, percentages
    from app.domain.rm_matching import customers_of, match_rm

    hk = ZoneInfo("Asia/Hong_Kong")
    hk_now = datetime.now(hk)
    week_start_date = (hk_now - timedelta(days=7)).date()
    week_start = week_start_date.isoformat()
    week_end = hk_now.date().isoformat()
    # 时间列在 PG/SQLite 中均为 naive UTC（UTCDateTime 只在读回时补时区），
    # 查询条件也必须用 naive UTC，否则 PG 会按 session TimeZone 解释而偏移 8 小时。
    week_start_utc = datetime.combine(
        week_start_date, datetime.min.time(), tzinfo=hk
    ).astimezone(timezone.utc).replace(tzinfo=None)

    customers = customers_of(username)
    match_mode = "rm_matched" if customers else "fallback"
    rm = match_rm(username)
    assessment_map = {a.policy_id: a for a in db.scalars(select(Assessment)).all()}

    def _date_of(value) -> str:  # noqa: ANN001
        if not value:
            return ""
        return value[:10] if isinstance(value, str) else value.date().isoformat()

    def _load_rows(since: datetime | None, limit: int) -> list:
        """取已发布政策的预处理记录；since 为空表示不限入库时间。"""
        stmt = (
            select(PolicyPreprocess, Policy)
            .join(Policy, Policy.id == PolicyPreprocess.policy_id)
            .where(Policy.status == "published")
        )
        if since is not None:
            stmt = stmt.where(PolicyPreprocess.created_at >= since)
        order = (
            PolicyPreprocess.created_at.desc()
            if since is not None
            else PolicyPreprocess.impact_total.desc()
        )
        return list(db.execute(stmt.order_by(order).limit(limit)).all())

    rows = _load_rows(week_start_utc, 200)
    window = "week"
    if not rows:  # 本周没有新入库：回退最近入库，避免推荐空着
        rows = _load_rows(None, 100)
        window = "all"

    items: list[dict] = []
    for record, policy in rows:
        view = _policy_view(db, policy)
        matched: list[dict] = []
        if customers:
            lines = {b.get("code") for b in (record.affected_business or []) if b.get("code")}
            matched = [c for c in customers if not lines or c.get("business_line") in lines]
            amount = round(sum(
                float(c.get("loan_balance_cny_yi", 0) or 0) + float(c.get("other_bank_loans_cny_yi", 0) or 0)
                for c in matched
            ), 2)
            assessment = assessment_map.get(policy.id)
            pct = percentages(
                assessment.scores if assessment else None,
                record.direction,
                affected_amount_cny_yi=amount,
                affected_customer_count=len(matched),
            )
        else:
            # 规则 B：三维分数直接取预处理表格百分比，不受客户画像影响
            pct = {
                "loss_pct": record.loss_pct,
                "profit_pct": record.profit_pct,
                "reputation_pct": record.reputation_pct,
                "opportunity_pct": record.opportunity_pct,
                "impact_total": record.impact_total,
                "business_loss": round(float(record.loss_pct or 0)),
                "business_opportunity": round(float(record.opportunity_pct or 0)),
                "reputation_risk": round(float(record.reputation_pct or 0)),
            }

        items.append({
            **view,
            "impact_dimensions": {
                "business_loss": pct["business_loss"],
                "business_opportunity": pct["business_opportunity"],
                "reputation_risk": pct["reputation_risk"],
                "impact_total": pct["impact_total"],
                "affected_customer_count": len(matched) if customers else
                int((record.extras or {}).get("affected_customer_count", 0) or 0),
            },
            "preprocess": {
                "id": record.id,
                "keywords": record.keywords or [],
                "affected_business": record.affected_business or [],
                "customer_segments": record.customer_segments or [],
                "loss_pct": pct["loss_pct"],
                "profit_pct": pct["profit_pct"],
                "reputation_pct": pct["reputation_pct"],
                "opportunity_pct": pct["opportunity_pct"],
                "hsbc_response": normalize_research_items(record.hsbc_response),
                "peer_bank_response": normalize_research_items(record.peer_bank_response),
                "market_applications": normalize_research_items(record.market_applications),
                "source": record.source,
            },
            "match_mode": match_mode,
            "matched_customers": [
                {
                    "customer_id": c.get("customer_id"),
                    "name_masked": c.get("name_masked"),
                    "business_line": c.get("business_line"),
                    "loan_balance_cny_yi": c.get("loan_balance_cny_yi", 0),
                }
                for c in matched[:5]
            ],
            "unassessed": False,
        })

    def _triple_total(item: dict) -> float:
        dims = item.get("impact_dimensions") or {}
        return (
            float(dims.get("business_loss") or 0)
            + float(dims.get("business_opportunity") or 0)
            + float(dims.get("reputation_risk") or 0)
        )

    # 按三维分数（业务损失 + 业务机会 + 声誉风险）由高到低
    items.sort(key=lambda item: (
        -_triple_total(item),
        -float((item.get("impact_dimensions") or {}).get("impact_total") or 0),
        -float(_date_of(item.get("published_at")).replace("-", "") or 0),
    ))
    # 「相关度 0 且无红线/差异条款」的政策对本行没有直接冲击（多为地方金融组织
    # 设立/注销类公告），不进入推荐列表，否则整张表会被同一组 0 分刷屏。
    def _has_impact(item: dict) -> bool:
        dims = item.get("impact_dimensions") or {}
        return any(
            float(dims.get(key) or 0) > 0
            for key in ("business_loss", "business_opportunity", "reputation_risk")
        )

    impactful = [item for item in items if _has_impact(item)]
    hidden_no_impact = len(items) - len(impactful)
    if impactful:
        items = impactful
    else:
        hidden_no_impact = 0  # 全部无直接冲击时保留原列表，避免推荐页空白
    return {
        "items": items,
        "total": len(items),
        "hidden_no_impact": hidden_no_impact,
        "match_mode": match_mode,
        "rm": rm,
        "matched_customer_count": len(customers),
        "scores_source": "customer_exposure" if customers else "preprocess_percent",
        "window": window,
        "period": {"start": week_start, "end": week_end},
    }


_APPLICABLE_SCOPE_LABELS = {
    "all": "面向所有主体",
    "domestic_only": "仅限境内主体",
    "foreign_included": "含外资主体",
    "qualified_only": "仅限符合特定资质的主体",
    "unclear": "适用范围不明确",
}
_ENTITY_STATUS_LABELS = {
    "high": "高相关",
    "medium": "中相关",
    "low": "低相关",
    "not_mentioned": "未提及",
    "na": "不适用",
}
_DIFF_ENTITY_LABELS = {"hsbc_hk": "香港汇丰", "hsbc_cn": "汇丰（中国）"}


def _differential_note(policy: Policy, db: Session) -> dict:
    """外资银行相关影响提示：由 AI 依据「是否影响外资行 / 是否对汇丰适用 / 关注程度」动态生成。

    触发条件（满足其一即调用 AI）：
    - 规则命中差异条款（foreign_bank_differential=True，外资被排除/区别对待）；
    - 适用范围明确含外资（applicable_scope=foreign_included）；
    - 目标实体高相关（target_entity_status=high，汇丰作为外资银行直接适用）。

    AI 调用成功后以 AI 结论为准（AI 判断无差异且不适用时 note 留空，前端不展示该块）；
    仅当 AI 调用真正失败时，才退回中性兜底文案并标记 source=fallback。
    """
    differential = bool(policy.foreign_bank_differential)
    includes_foreign = (policy.applicable_scope or "") == "foreign_included"
    hsbc_high = (policy.target_entity_status or "") == "high"
    if not (differential or includes_foreign or hsbc_high):
        return {
            "foreign_bank_differential": False,
            "applies_to_hsbc": None,
            "attention_level": "none",
            "note": "",
            "reason": "",
        }
    from app.ai.chains.base import load_prompt
    from app.ai.provider import get_provider
    from app.ai.schemas import DIFFERENTIAL_SCHEMA

    # 输入只给自然语言，不给内部枚举值/空标签，避免 AI 把 domestic_only、<scope_judgement> 等字眼写进结论。
    policy_card = json.dumps(
        {
            "title": policy.title,
            "issuing_body": policy.issuing_body,
            "summary_zh": policy.summary_zh or "",
            "applicable_scope": _APPLICABLE_SCOPE_LABELS.get(policy.applicable_scope, "适用范围不明确"),
            "target_entity_status": _ENTITY_STATUS_LABELS.get(policy.target_entity_status, "未提及"),
        },
        ensure_ascii=False,
    )
    scope_rows = db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == policy.id)).all()
    if scope_rows:
        scope = json.dumps(
            [
                {
                    "entity": _DIFF_ENTITY_LABELS.get(j.entity_id, j.entity_id),
                    "result": _ENTITY_STATUS_LABELS.get(j.result, j.result),
                    "reason": j.llm_reason or "",
                }
                for j in scope_rows
            ],
            ensure_ascii=False,
        )
    else:
        scope = "无（规则通道暂未给出目标实体适用性判定）"
    _, system, user_tpl = load_prompt("p9_differential")
    user = user_tpl.replace("{policy_card}", policy_card).replace("{scope_judgement}", scope)
    try:
        result = get_provider().complete(
            system=system, user=user, schema=DIFFERENTIAL_SCHEMA, task="differential", max_tokens=700,
        )
        parsed = result.parsed or {}
        ai_ok = True
    except Exception as exc:
        log.warning("differential_llm_failed policy_id=%s: %s: %s", policy.id, type(exc).__name__, exc)
        parsed = {}
        ai_ok = False

    note = (parsed.get("note") or "").strip()
    reason = (parsed.get("reason") or "").strip()
    applies_to_hsbc = parsed.get("applies_to_hsbc")
    attention_level = parsed.get("attention_level") or ""
    ai_differential = parsed.get("foreign_bank_differential")

    if not ai_ok:
        # AI 真正不可用才兜底：措辞中性，不替用户下「重点关注」结论
        return {
            "foreign_bank_differential": True,
            "applies_to_hsbc": None,
            "attention_level": "watch",
            "note": "该政策可能涉及外资银行差异条款，建议人工复核其对汇丰的适用与影响。",
            "reason": "",
            "source": "fallback",
        }

    if ai_differential is False:
        # AI 判断实际无差异条款：尊重结论，note 留空，前端不展示该块
        return {
            "foreign_bank_differential": False,
            "applies_to_hsbc": applies_to_hsbc,
            "attention_level": attention_level or "none",
            "note": note,
            "reason": reason,
            "source": "ai",
        }

    return {
        "foreign_bank_differential": True,
        "applies_to_hsbc": applies_to_hsbc,
        "attention_level": attention_level or "watch",
        "note": note,
        "reason": reason,
        "source": "ai",
    }


@router.get("/{policy_id}")
def get_policy(policy_id: str, db: Session = Depends(get_db), role: str = Depends(get_demo_role)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if role == "consumer" and policy.status != "published":
        raise not_found("政策", policy_id)
    review_tasks = [] if role == "consumer" else db.scalars(
        select(ReviewTask).where(ReviewTask.policy_id == policy.id).order_by(ReviewTask.created_at)
    ).all()
    return {
        **_policy_view(db, policy),
        "differential": _differential_note(policy, db),
        "review_tasks": [
            {
                "id": task.id,
                "level": task.level,
                "assignee": task.assignee,
                "status": task.status,
                "sla_due_at": task.sla_due_at,
                "created_at": task.created_at,
                "decisions": [
                    {
                        "actor": decision.actor,
                        "action": decision.action,
                        "reason_code": decision.reason_code,
                        "note": decision.note,
                        "created_at": decision.created_at,
                    }
                    for decision in task.decisions
                ],
            }
            for task in review_tasks
        ],
        "assessments": [
            {
                "id": a.id,
                "scores": a.scores,
                "direction": a.direction,
                "score_total": a.score_total,
                "priority": a.priority,
                "transmission_chain": a.transmission_chain,
                "affected": a.affected,
                "recommended_actions": a.recommended_actions,
                "case_links": a.case_links,
                "confidence": a.confidence,
                "model": a.model,
                "prompt_version": a.prompt_version,
            }
            for a in policy.assessments
        ],
        "evidence": [
            {
                "id": e.id,
                "document_id": e.document_id,
                "span_start": e.span_start,
                "span_end": e.span_end,
                "quote": e.quote,
                "field_name": e.field_name,
            }
            for e in policy.evidence_items
        ],
        "scope_judgements": [
            {
                "entity_id": j.entity_id,
                "result": j.result,
                "rule_hits": j.rule_hits,
                "llm_reason": j.llm_reason,
                "conflict": j.conflict,
            }
            for j in db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == policy.id)).all()
        ],
        "document": (
            {
                "id": doc.id,
                "title": doc.title,
                "url": doc.url,
                "lang": doc.lang,
                "published_at": doc.published_at,
                "content_text": doc.content_text,
                "attachments": doc.attachments,
            }
            if (doc := db.get(Document, policy.document_id))
            else None
        ),
        "url": (db.get(Document, policy.document_id).url if db.get(Document, policy.document_id) else ""),
    }


def _foreign_bank_note(policy: Policy) -> str:
    """政策有无纳入外资银行 + 对汇丰影响简述（政策解读大页面第一句）。"""
    if policy.foreign_bank_differential:
        return "本政策涉及外资银行差异条款，对汇丰的适用存在区别对待，影响需重点关注。"
    if policy.target_entity_status in ("high", "medium"):
        return "本政策纳入外资银行（汇丰）适用范围，需关注其对汇丰业务的影响。"
    return "本政策未明确是否纳入外资银行，需人工复核适用主体范围。"


def _topic_columns(db: Session, topic: str) -> dict:
    """按重点话题关键词检索内部库与网络，生成三栏解读（离线模板，不调用 LLM）。

    与政策预处理表格口径一致：每栏只返回「简述 + 原文链接」，
    没有可核查来源时返回空数组，由前端显示占位。
    """
    from app.chat.tools import ChatTools
    from app.chat.web_search import search_web
    from app.domain.preprocess import normalize_research_items

    tools = ChatTools(db, "consumer")
    internal_evidence = [
        e for e in (tools.search_policies(topic) + tools.search_documents(topic)) if e.text
    ][:3]
    hsbc = normalize_research_items([
        {
            "summary": (e.text or "").strip()[:200],
            "url": (e.citation or {}).get("url", ""),
        }
        for e in internal_evidence
    ])

    web: list = []
    try:
        web = search_web(topic, limit=3)
    except Exception:
        web = []
    web_links = normalize_research_items([
        {
            "summary": ((e.text or "").strip() or e.title)[:200],
            "url": (e.citation or {}).get("url", ""),
        }
        for e in web[:3]
    ])
    return {"hsbc": hsbc, "industry": web_links, "market": web_links}


def _consumer_advice(policy: Policy, assessment, matched: list) -> dict:
    """AI 分析政策对当前用户的影响 + 客户经理跟进建议（自然语言，不含评分数字）。

    AI 不可用时降级为规则文案；降级文案同样不出现「业务损失 X 分」等数字。
    """
    from app.ai.chains.base import load_prompt
    from app.ai.provider import get_provider
    from app.ai.schemas import FOLLOWUP_ADVICE_SCHEMA

    policy_card = json.dumps(
        {
            "title": policy.title,
            "summary_zh": policy.summary_zh or "",
            "themes": policy.themes or [],
            "applicable_scope": policy.applicable_scope,
            "direction": assessment.direction if assessment else "neutral",
        },
        ensure_ascii=False,
    )
    user_profile = json.dumps(
        {
            "customer_count": len(matched),
            "business_lines": sorted({c.get("business_line") for c in matched if c.get("business_line")}),
            "segments": sorted({c.get("segment") for c in matched if c.get("segment")}),
            "total_loan_cny_yi": round(sum(float(c.get("loan_balance_cny_yi", 0) or 0) for c in matched), 2),
        },
        ensure_ascii=False,
    )
    business_map = json.dumps(
        {"business_lines": sorted({c.get("business_line") for c in matched if c.get("business_line")})},
        ensure_ascii=False,
    )
    _, system, user_tpl = load_prompt("p10_followup_advice")
    user = (
        user_tpl.replace("{policy_card}", policy_card)
        .replace("{user_profile}", user_profile)
        .replace("{business_map}", business_map)
    )
    parsed: dict = {}
    try:
        result = get_provider().complete(
            system=system, user=user, schema=FOLLOWUP_ADVICE_SCHEMA, task="followup_advice", max_tokens=900,
        )
        parsed = result.parsed or {}
    except Exception:
        parsed = {}
    direction_label = {"positive": "利好", "negative": "利空", "mixed": "利弊并存", "neutral": "中性"}.get(
        assessment.direction if assessment else "neutral", "中性",
    )
    fallback_impact = (
        f"该政策整体呈{direction_label}方向，涉及您所管理客户合计 {len(matched)} 户。"
        "建议结合各客户业务线与政策主题，评估其融资成本、合规要求与业务机会的具体变化。"
    )
    fallback_advice = (
        "建议客户经理逐户核对受影响客户的贷款定价与业务结构，主动沟通政策变化，"
        "并优先关注有跨境结算、贸易融资或跨境理财需求的客户，把握政策窗口。"
    )
    return {
        "impact_on_user": (parsed.get("impact_on_user") or "").strip() or fallback_impact,
        "followup_advice": (parsed.get("followup_advice") or "").strip() or fallback_advice,
        "cross_border_angle": parsed.get("cross_border_angle"),
    }


def _consumer_view(db: Session, policy: Policy, username: str | None = None) -> dict:
    """政策使用者视角的政策解读：外资银行句、重点话题三栏解读、原文简化版、影响概述、受影响客户。

    受影响客户只对「名下有客户」的使用者展示：没有客户的政策使用者看不到
    「对所管理用户的影响概述」与客户名单，避免凭空展示与本人无关的合成客户。
    """
    from app.domain.rm_matching import customers_of

    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    scores = assessment.scores if assessment else None
    direction = assessment.direction if assessment else None
    business_lines = (assessment.affected.get("business_lines", []) if assessment else [])

    # 三维影响评分（业务损失按受影响客户金额额度分档；无匹配时按所有相关用户）
    amount, count = affected_amount_by_business_lines(business_lines)
    dimensions = compute_consumer_impact(
        scores, direction=direction,
        affected_amount_cny_yi=amount, affected_customer_count=count,
    )
    direction_label = {"positive": "利好", "negative": "利空", "mixed": "利弊并存", "neutral": "中性"}.get(direction, "中性")

    # 重点话题（政策主题）列表；三栏解读按需懒加载（见 /{policy_id}/topic/{topic} 接口），
    # 避免在详情接口里串行联网检索（search_web）导致页面长时间 loading。
    topics = [{"topic": topic} for topic in (policy.themes or [])[:5]]

    # 受影响客户：只取该使用者名下客户，再按政策业务线过滤；没有客户 → 不返回客户列表
    managed = customers_of(username)
    lines = {line for line in business_lines if line}
    matched = [c for c in managed if not lines or c.get("business_line") in lines]
    sorted_matched = sorted(matched, key=lambda c: -float(c.get("loan_balance_cny_yi", 0) or 0))
    affected = customer_impact_rows(sorted_matched[:30], scores, direction=direction)

    if matched:
        advice = _consumer_advice(policy, assessment, matched)
        impact_overview = advice["impact_on_user"]
        followup_advice = advice["followup_advice"]
        match_basis = {
            "rule": ("按名下客户 × 政策业务线匹配" if lines else "名下客户（政策未标注业务线）"),
            "business_lines": sorted(lines),
            "total_matched": len(matched),
            "shown": min(len(sorted_matched), 30),
            "source": "seed/synthetic_customers.json（合成演示数据，非真实客户）",
        }
        benefit_loss = ""
    else:
        # 没有客户：不给影响概述与客户名单留空壳，前端据此整块隐藏
        impact_overview = ""
        followup_advice = ""
        match_basis = {
            "rule": "未匹配到客户经理或名下暂无客户",
            "business_lines": sorted(lines),
            "total_matched": 0,
            "shown": 0,
            "source": "seed/synthetic_customers.json（合成演示数据，非真实客户）",
        }
        benefit_loss = ""

    # 外部公开反应：只输出「简述 + 原文链接」，避免把标题/来源等冗余字段带到使用者页面
    from app.domain.preprocess import normalize_research_items

    record = policy.preprocess
    research = {
        "hsbc_response": normalize_research_items(record.hsbc_response if record else None),
        "peer_bank_response": normalize_research_items(record.peer_bank_response if record else None),
        "market_applications": normalize_research_items(record.market_applications if record else None),
    }

    return {
        "foreign_bank_note": _foreign_bank_note(policy),
        "topics": topics,
        "simplified_summary": policy.summary_zh or "尚未生成摘要",
        "research": research,
        "impact_overview": impact_overview,
        "followup_advice": followup_advice,
        "dimensions": dimensions,
        "benefit_loss": benefit_loss,
        "match_basis": match_basis,
        "affected_customers": affected,
    }


@router.get("/{policy_id}/consumer-view")
def policy_consumer_view(
    policy_id: str,
    username: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("consumer")),
):
    """政策使用者视角的政策解读；username 用于判断该使用者名下是否有客户。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    return _consumer_view(db, policy, username)


@router.get("/{policy_id}/affected-customers")
def policy_affected_customers(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor", "admin")),
):
    """政策影响到的全部客户统计（政策运营专员视角）。

    口径为合成客户库全量：按政策受影响业务线匹配所有客户后聚合，
    与「发来影响报告的使用者名下是否有客户」无关。
    """
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    return {"policy_id": policy_id, **affected_customer_stats(db, policy)}


@router.post("/{policy_id}/affected-customers/analysis")
def policy_affected_customers_analysis(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor", "admin")),
):
    """由跟进 Agent 动态分析受影响客户，返回实时统计 + AI 概况结论。

    Agent 未接入或调用失败时退回数据驱动归纳，接口始终返回可用内容。
    """
    from app.ai.followup import affected_customer_brief

    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    stats = affected_customer_stats(db, policy)
    reports = followup_report_summary(db, policy_id)
    brief = affected_customer_brief(followup_policy_card(db, policy), stats, reports)
    return {
        "policy_id": policy_id,
        "stats": stats,
        "brief": brief,
        "reports": reports,
    }


@router.post("/{policy_id}/agent/cleanup")
def agent_cleanup_policy(
    policy_id: str,
    dry_run: bool = Query(default=False, description="只判定，不执行删除"),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor", "admin")),
):
    """Agent Skill「irrelevant_policy_cleanup」：判定政策对汇丰是否完全没有影响。

    - dry_run=true 只返回判定结论（verdict / keep_reasons / signals）；
    - 执行时命中确定性门禁才删除政策及其原文，并写审计。
    """
    from app.agent.cleanup import assess_hsbc_impact, cleanup_policy_if_irrelevant

    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if dry_run:
        return {"policy_id": policy_id, "dry_run": True, **assess_hsbc_impact(db, policy)}
    result = cleanup_policy_if_irrelevant(db, policy)
    return {"policy_id": policy_id, "dry_run": False, **result}


@router.post("/{policy_id}/tracking-email")
def policy_tracking_email(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor", "admin")),
):
    """由跟进 Agent 生成政策跟踪报告邮件（主题 + 正文）。"""
    from app.ai.followup import tracking_email

    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    stats = affected_customer_stats(db, policy)
    reports = followup_report_summary(db, policy_id)
    email = tracking_email(followup_policy_card(db, policy), stats, reports)
    return {"policy_id": policy_id, **email}


@router.get("/{policy_id}/topic/{topic}")
def policy_topic_columns(
    policy_id: str,
    topic: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("consumer")),
):
    """按需懒加载单个重点话题的三栏解读（内部库 + 网络检索）。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    return {"topic": topic, "columns": _topic_columns(db, topic)}


@router.post("/{policy_id}/consumer-view/send-review", status_code=201)
def send_consumer_report(
    policy_id: str,
    username: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("consumer")),
):
    """consumer 把影响报告发送给政策运营专员 review。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    report = ConsumerReport(policy_id=policy_id, actor="consumer", report=_consumer_view(db, policy, username))
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "policy_id": policy_id, "status": report.status, "created_at": report.created_at}


@router.get("/{policy_id}/analysis")
def policy_analysis(policy_id: str, db: Session = Depends(get_db), role: str = Depends(get_demo_role)):
    """AI 分析过程拆解：把五步链路（分类→抽取→适用性→影响→预警）的结论与 LLM 调用明细按步骤返回。

    历史数据（2026-11-14 之前分析的）llm_call_log 无 policy_id 关联，对应步骤 llm 为 null。
    """
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if role == "consumer":
        raise not_found("政策", policy_id)
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first()
    judgements = db.scalars(select(ScopeJudgement).where(ScopeJudgement.policy_id == policy_id)).all()
    evidence_count = db.query(Evidence).filter(Evidence.policy_id == policy_id).count()
    calls = db.scalars(
        select(LLMCallLog).where(LLMCallLog.policy_id == policy_id).order_by(LLMCallLog.at.asc())
    ).all()
    call_by_task: dict[str, LLMCallLog] = {}
    for call in calls:
        call_by_task[call.task] = call  # 升序遍历后写覆盖 → 每链路保留最近一次

    def llm_view(task: str):
        call = call_by_task.get(task)
        if not call:
            return None
        return {
            "model": call.model, "provider": call.provider, "prompt_version": call.prompt_version,
            "tokens_in": call.tokens_in, "tokens_out": call.tokens_out,
            "latency_ms": call.latency_ms, "status": call.status, "error": call.error,
            "at": call.at.isoformat(),
        }

    alert = None
    if assessment:
        alert = db.scalars(select(Alert).where(Alert.assessment_id == assessment.id)).first()

    steps = [
        {
            "key": "classify",
            "title": "分类打标",
            "description": "判断是否金融政策，标注政策类型、辖区与主题",
            "items": [
                {"label": "是否金融政策", "value": "是"},
                {"label": "政策类型", "value": policy.policy_type or "—"},
                {"label": "辖区", "value": policy.jurisdiction or "—"},
                {"label": "主题标签", "value": "、".join(policy.themes) or "—"},
            ],
            "llm": llm_view("classify"),
        },
        {
            "key": "extract",
            "title": "结构化抽取",
            "description": "从原文抽取文号、日期、适用主体、金额与义务，并为结论定位原文证据",
            "items": [
                {"label": "适用主体", "value": policy.applicable_entities_text or "原文未明确"},
                {"label": "义务条款", "value": f"{len(policy.obligations)} 条"},
                {"label": "截止日期", "value": f"{len(policy.deadlines)} 条"},
                {"label": "金额信息", "value": f"{len(policy.amounts)} 条"},
                {"label": "激励措施", "value": f"{len(policy.incentives)} 条"},
                {"label": "证据片段", "value": f"{evidence_count} 条"},
            ],
            "llm": llm_view("extract"),
        },
        {
            "key": "scope",
            "title": "适用性判定（规则 + AI 双通道）",
            "description": "规则关键词通道与 LLM 通道分别判定汇丰香港 / 汇丰中国的相关性，结论冲突时需人工复核",
            "items": [
                {"label": j.entity_id, "value": j.result, "note": j.llm_reason or "", "conflict": j.conflict}
                for j in judgements
            ],
            "llm": llm_view("scope"),
        },
        {
            "key": "impact",
            "title": "影响分析",
            "description": "结合八维评分卡、传导链与相似案例给出影响方向与优先级",
            "items": (
                [
                    {"label": "影响方向", "value": assessment.direction},
                    {"label": "综合影响分", "value": assessment.score_total},
                    {"label": "优先级", "value": assessment.priority},
                    {"label": "分析置信度", "value": assessment.confidence},
                    {"label": "相似案例", "value": f"{len(assessment.case_links)} 条"},
                    {"label": "建议动作", "value": f"{len(assessment.recommended_actions)} 条"},
                ]
                if assessment
                else []
            ),
            "llm": llm_view("impact"),
        },
        {
            "key": "alert",
            "title": "预警草稿",
            "description": "面向内部通知渠道生成六段式预警草稿，随政策进入审核队列",
            "items": [{"label": "草稿状态", "value": "已生成" if alert else "未生成"}],
            "body_md": alert.body_md if alert else "",
            "llm": llm_view("alert"),
        },
    ]
    return {"policy_id": policy_id, "prompt_version": policy.prompt_version, "steps": steps}


@router.post("/{policy_id}/analyze", status_code=202)
def analyze_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
):
    """触发/重跑 AI 分析（同步执行；MVP 单机可接受，Phase 5 改异步任务）。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    from app.jobs.analyze_job import analyze_document

    doc = db.get(Document, policy.document_id)
    if not doc:
        raise ApiError("DOC_MISSING", "政策关联文档缺失", 500)
    try:
        refreshed = analyze_document(db, doc)
    except ApiError:
        raise
    except Exception as exc:
        db.rollback()
        raise ApiError("ANALYZE_FAILED", f"重新分析失败：{type(exc).__name__}: {exc}", 500)
    if refreshed is None:
        raise ApiError("ANALYZE_SKIPPED", "该文档不再满足分析条件（非金融政策/无正文）", 422)
    return {"status": "ok", "policy_id": refreshed.id, "priority": refreshed.priority,
            "score_total": refreshed.score_total, "policy_status": refreshed.status}


@router.post("/{policy_id}/dispatch")
def dispatch_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("processor", "admin")),
):
    """发布：已分析（ai_checked）或已审核通过（approved）的政策均可直接发布。"""
    from app.domain import review as review_domain

    return review_domain.dispatch_policy(db, policy_id, actor=actor)


@router.post("/{policy_id}/recall")
def recall_policy(
    policy_id: str,
    body: RecallBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
):
    """用户反馈打回审核：已发布政策回到人工审核队列（published → pending_review）。"""
    from app.domain import review as review_domain

    return review_domain.recall_to_review(db, policy_id, actor=actor, note=body.note)


@router.post("/{policy_id}/feedback", status_code=201)
def submit_feedback(
    policy_id: str,
    body: FeedbackBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
):
    """用户对已发布政策提交反馈意见（反馈至平台管理员）。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    content = body.content.strip()
    if not content:
        raise ApiError("EMPTY_FEEDBACK", "反馈内容不能为空", 422)
    feedback = Feedback(policy_id=policy_id, actor=actor, content=content)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"id": feedback.id, "policy_id": policy_id, "created_at": feedback.created_at}


@router.get("/{policy_id}/feedbacks")
def list_feedbacks(policy_id: str, db: Session = Depends(get_db), role: str = Depends(get_demo_role)):
    """列出某政策的用户反馈。"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    items = db.scalars(
        select(Feedback).where(Feedback.policy_id == policy_id).order_by(Feedback.created_at.desc())
    ).all()
    return {
        "items": [
            {"id": f.id, "actor": f.actor, "content": f.content, "created_at": f.created_at}
            for f in items
        ]
    }


@router.post("/{policy_id}/feedback-report")
def generate_feedback_report(
    policy_id: str,
    body: ReportBody,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("processor", "admin")),
):
    """审核员为某条反馈生成分析报告（结合公司内部政策）。"""
    from app.ai.chains.feedback_report import FeedbackReportChain

    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    feedback = db.get(Feedback, body.feedback_id)
    if not feedback or feedback.policy_id != policy_id:
        raise not_found("反馈", body.feedback_id)
    policy_card = {
        "title": policy.title,
        "issuing_body": policy.issuing_body,
        "doc_number": policy.doc_number,
        "summary_zh": policy.summary_zh,
        "applicable_entities_text": policy.applicable_entities_text,
        "themes": policy.themes,
    }
    try:
        result = FeedbackReportChain().run(policy_card=policy_card, feedback=feedback.content)
    except Exception as exc:
        raise ApiError("REPORT_FAILED", f"报告生成失败：{exc}", 500)
    return {"feedback_id": feedback.id, "report": result.parsed, "model": result.model}


class FollowupDecisionBody(BaseModel):
    action: str  # keep | delete


@router.post("/{policy_id}/followup-decide")
def followup_decide(
    policy_id: str,
    body: FollowupDecisionBody,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin", "processor")),
):
    """跟进专员对「AI 判定疑似完全无影响」的政策做保留/删除决定。

    - keep：置 followup=True（永久保留，豁免 5 年清理），清除疑似标记；
    - delete：删除政策及原文（走现有清理逻辑 + 审计）。
    """
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if body.action == "keep":
        policy.followup = True
        policy.irrelevant_flagged = False
        db.commit()
        return {"status": "ok", "action": "keep", "policy_id": policy_id, "followup": True}
    if body.action == "delete":
        from app.agent.cleanup import delete_policy_and_document

        document_id = policy.document_id
        delete_policy_and_document(
            db, policy,
            reason="跟进专员判定对汇丰完全无影响，删除政策与原文",
            actor=actor,
        )
        db.commit()
        return {"status": "ok", "action": "delete", "policy_id": policy_id, "document_id": document_id}
    raise ApiError("INVALID_INPUT", "action 必须为 keep 或 delete", 422)


@router.delete("/{policy_id}")
def remove_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin")),
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    document_id = policy.document_id
    try:
        delete_policy(db, policy, actor=actor)
    except Exception as e:  # noqa: BLE001 — 删除失败时回滚并返回可定位的具体原因
        db.rollback()
        raise ApiError("DELETE_FAILED", f"删除政策失败：{type(e).__name__}: {e}", 500) from e
    return {"status": "ok", "policy_id": policy_id, "document_id": document_id, "document_retained": True}


@router.post("/{policy_id}/restore")
def restore_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin", "processor")),
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    if policy.target_entity_status != "low":
        raise ApiError("NOT_LOW", "该政策非低相关性", 422)
    if not state_machine.can_transition(policy.status, "pending_review"):
        raise ApiError(
            "INVALID_TRANSITION", f"政策当前状态为 {policy.status}，不能恢复为待审核", 409,
            {"from": policy.status, "to": "pending_review"},
        )
    from app.domain import review as review_domain

    policy.target_entity_status = "high"
    review_domain.submit_review(
        db, policy_id, level=1, assignee="analyst.default", actor=actor, note="恢复低相关政策",
    )
    return {"status": "ok", "policy_id": policy.id, "target_entity_status": policy.target_entity_status, "policy_status": policy.status}

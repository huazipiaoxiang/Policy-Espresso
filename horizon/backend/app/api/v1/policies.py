"""政策列表/详情/分发拦截。完整实现随 Phase 2/3 补齐；分发 409 硬规则已在此生效。"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.api.v1.schemas import Page, PolicyOut
from app.core.errors import ApiError, not_found, not_approved
from app.core.security import get_demo_role, require_api_key, require_roles
from app.db.models import Alert, Assessment, Dispatch, Document, Evidence, Feedback, LLMCallLog, Policy, ReviewTask, ScopeJudgement
from app.db.session import get_db
from app.domain import state_machine
from app.domain.consumer_impact import compute_consumer_impact, compute_customer_impact
from app.domain.policy_admin import delete_policy

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
    return stmt


def _policy_view(db: Session, policy: Policy) -> dict:
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    dispatched_at = db.scalar(
        select(func.max(Dispatch.sent_at))
        .join(Alert, Alert.id == Dispatch.alert_id)
        .join(Assessment, Assessment.id == Alert.assessment_id)
        .where(Assessment.policy_id == policy.id)
    )
    return {
        **PolicyOut.model_validate(policy).model_dump(),
        "impacted_domains": (assessment.affected.get("business_lines", []) if assessment else []),
        "dispatched_at": (dispatched_at.isoformat() if dispatched_at else None),
        "direction": (assessment.direction if assessment else None),
        "impact_dimensions": compute_consumer_impact(assessment.direction if assessment else None),
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
    db: Session = Depends(get_db),
    role: str = Depends(get_demo_role),
):
    filters = {
        "q": q, "status": status, "status_not": status_not, "priority": priority,
        "jurisdiction": jurisdiction, "theme": theme, "scope": scope, "fetched": fetched,
        "published_on": published_on, "role": role, "review_level": review_level,
    }
    stmt = _policy_filters(select(Policy), **filters).order_by(Policy.published_at.desc().nullslast())
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    count_stmt = _policy_filters(select(func.count(Policy.id)), **filters)
    total = db.execute(count_stmt).scalar() or 0
    return Page(
        items=[_policy_view(db, policy) for policy in items],
        total=total, page=page, page_size=page_size,
    )


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


@router.get("/{policy_id}/consumer-view")
def policy_consumer_view(policy_id: str, db: Session = Depends(get_db), _: str = Depends(require_roles("consumer"))):
    """政策使用者视角的政策解读：简化版、影响概述、受影响客户、收益/损失。"""
    from app.domain.exposure import load_customers

    policy = db.get(Policy, policy_id)
    if not policy:
        raise not_found("政策", policy_id)
    assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy_id)).first()
    direction = assessment.direction if assessment else None

    customers = load_customers()
    sorted_customers = sorted(customers, key=lambda c: -float(c.get("loan_balance_cny_yi", 0) or 0))
    affected = [
        {
            "customer_id": c["customer_id"],
            "name_masked": c["name_masked"],
            "business_line": c["business_line"],
            "segment": c.get("segment", ""),
            "loan_balance_cny_yi": c.get("loan_balance_cny_yi", 0),
            "other_bank_loans_cny_yi": c.get("other_bank_loans_cny_yi", 0),
            "overseas_business": c.get("overseas_business", []),
            "impact": compute_customer_impact(c, direction),
        }
        for c in sorted_customers[:30]
    ]

    dimensions = compute_consumer_impact(direction)
    direction_label = {"positive": "利好", "negative": "利空", "mixed": "利弊并存", "neutral": "中性"}.get(direction, "中性")

    impact_overview = (
        f"该政策整体呈{direction_label}方向，影响客户经理所管理客户合计 {len(customers)} 户；"
        f"金钱损失维度 {dimensions['money_loss']} 分、业务机会维度 {dimensions['business_opportunity']} 分、"
        f"声誉损失维度 {dimensions['reputation_loss']} 分。"
    )

    return {
        "simplified_summary": policy.summary_zh or "尚未生成摘要",
        "impact_overview": impact_overview,
        "dimensions": dimensions,
        "benefit_loss": f"综合影响分 {dimensions['impact_total']} 分，详见各受影响客户的具体影响。",
        "affected_customers": affected,
    }


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
    _: str = Depends(require_roles("processor")),
):
    """人工分发：仅 AI 不明确转入人审并 approved 的政策走此路径（免审核直发已在分析阶段完成）。"""
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
    """用户对已发布政策提交反馈意见（反馈至审核员）。"""
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
    delete_policy(db, policy, actor=actor)
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

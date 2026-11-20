"""政策预处理表格接口：列表 / 详情 / 重建（仅管理员可重建，只读为主）。

数据来自 policy_preprocess 表（政策抓取入库并完成分析后自动生成）。
预处理信息供「为你推荐」三维评分、政策详情、管理端查看消费。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.security import require_api_key, require_roles
from app.db.models import Policy, PolicyPreprocess
from app.db.session import get_db
from app.domain.preprocess import normalize_research_items, upsert_preprocess

router = APIRouter(
    prefix="/preprocess", tags=["preprocess"], dependencies=[Depends(require_api_key)]
)

_HK = ZoneInfo("Asia/Hong_Kong")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _view(record: PolicyPreprocess, policy: Policy) -> dict:
    fetched_at = getattr(policy.document, "fetched_at", None) if policy.document else None
    return {
        "id": record.id,
        "policy_id": policy.id,
        "title": policy.title,
        "issuing_body": policy.issuing_body,
        "jurisdiction": policy.jurisdiction,
        "policy_type": policy.policy_type,
        "themes": policy.themes or [],
        "status": policy.status,
        "priority": policy.priority,
        "published_at": _iso(policy.published_at),
        "fetched_at": _iso(fetched_at),
        "preprocessed_at": _iso(record.created_at),
        # 预处理字段
        "keywords": record.keywords or [],
        "affected_business": record.affected_business or [],
        "customer_segments": record.customer_segments or [],
        "loss_pct": record.loss_pct,
        "profit_pct": record.profit_pct,
        "reputation_pct": record.reputation_pct,
        "opportunity_pct": record.opportunity_pct,
        "impact_total": record.impact_total,
        "direction": record.direction,
        # 外部检索只对外输出「简述 + 原文链接」，兼容历史四字段结构
        "hsbc_response": normalize_research_items(record.hsbc_response),
        "peer_bank_response": normalize_research_items(record.peer_bank_response),
        "market_applications": normalize_research_items(record.market_applications),
        "extras": record.extras or {},
        # 预处理 Agent 轨迹（模式/模型/工具/被拦截的出网请求/权限说明）
        "agent": (record.extras or {}).get("agent"),
        "source": record.source,
        "confidence": record.confidence,
    }


def _week_window() -> tuple[datetime, datetime]:
    now = datetime.now(_HK)
    start = datetime.combine((now - timedelta(days=7)).date(), datetime.min.time(), tzinfo=_HK)
    return start.astimezone(timezone.utc), now.astimezone(timezone.utc)


@router.get("/overview")
def preprocess_overview(db: Session = Depends(get_db), _: str = Depends(require_roles("admin", "processor"))) -> dict:
    """预处理表格概览：总数、本周新增、已检索外部反应的条数、平均综合分。"""
    total = db.scalar(select(func.count(PolicyPreprocess.id))) or 0
    start, _end = _week_window()
    week_new = db.scalar(
        select(func.count(PolicyPreprocess.id)).where(PolicyPreprocess.created_at >= start)
    ) or 0
    avg_total = db.scalar(select(func.avg(PolicyPreprocess.impact_total))) or 0
    with_research = db.scalar(
        select(func.count(PolicyPreprocess.id)).where(
            func.json_array_length(PolicyPreprocess.hsbc_response) > 0
        )
    )
    if with_research is None:  # SQLite 版本差异时回退为逐条判断
        with_research = len(
            [r for r in db.scalars(select(PolicyPreprocess)).all() if (r.hsbc_response or [])]
        )
    return {
        "total": total,
        "week_new": week_new,
        "avg_impact_total": round(float(avg_total), 1),
        "with_external_research": with_research,
    }


@router.get("")
def list_preprocess(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    direction: str | None = None,
    only_week: bool = Query(default=False, description="仅看本周新入库"),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin", "processor")),
):
    """政策预处理表格（分页）。"""
    stmt = select(PolicyPreprocess, Policy).join(Policy, Policy.id == PolicyPreprocess.policy_id)
    count_stmt = select(func.count(PolicyPreprocess.id)).join(
        Policy, Policy.id == PolicyPreprocess.policy_id
    )
    if q:
        like = f"%{q.strip()}%"
        condition = (Policy.title.like(like)) | (Policy.issuing_body.like(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if direction:
        stmt = stmt.where(PolicyPreprocess.direction == direction)
        count_stmt = count_stmt.where(PolicyPreprocess.direction == direction)
    if only_week:
        start, _end = _week_window()
        stmt = stmt.where(PolicyPreprocess.created_at >= start)
        count_stmt = count_stmt.where(PolicyPreprocess.created_at >= start)
    rows = db.execute(
        stmt.order_by(PolicyPreprocess.impact_total.desc(), PolicyPreprocess.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_view(record, policy) for record, policy in rows]
    total = db.scalar(count_stmt) or 0
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{policy_id}")
def get_preprocess(
    policy_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin", "processor")),
) -> dict:
    record = db.scalars(
        select(PolicyPreprocess).where(PolicyPreprocess.policy_id == policy_id)
    ).first()
    policy = db.get(Policy, policy_id)
    if record is None or policy is None:
        raise not_found("政策预处理", policy_id)
    return _view(record, policy)


@router.post("/{policy_id}/rebuild")
def rebuild_preprocess(
    policy_id: str,
    research: bool | None = Query(default=None, description="是否联网检索；留空跟随 PREPROCESS_WEB_RESEARCH"),
    agent: bool | None = Query(default=None, description="是否由 AI Agent 复核（默认跟随 PREPROCESS_AGENT_ENABLED）"),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
) -> dict:
    """按当前政策与评估结果重建预处理记录（管理员专用）。"""
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise not_found("政策", policy_id)
    record = upsert_preprocess(db, policy, research=research, use_agent=agent)
    db.commit()
    db.refresh(record)
    return _view(record, policy)


@router.get("/agent/permissions")
def agent_permissions(
    _: str = Depends(require_roles("admin", "processor")),
) -> dict:
    """政策流水线 Agent 的能力清单与工具集（除数据外泄外全部开放）。"""
    from app.agent.permissions import describe_permissions
    from app.agent.skills import describe_skills
    from app.agent.tools import available_tools
    from app.core.config import get_settings

    return {
        **describe_permissions(),
        "enabled": bool(get_settings().preprocess_agent_enabled),
        "max_rounds": int(get_settings().preprocess_agent_max_rounds),
        "skills": describe_skills(),
        "irrelevant_cleanup_enabled": bool(get_settings().irrelevant_cleanup_enabled),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "permissions": sorted(spec.permissions),
            }
            for spec in available_tools()
        ],
    }

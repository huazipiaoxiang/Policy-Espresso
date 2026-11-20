"""seed 导入：数据源清单 / 主题词表 / 目标实体 / 历史案例 / 合成客户。

用法：make seed（或 python -m app.jobs.seed_job）。幂等：按 code/名称去重。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Assessment, Case, Document, Policy, PolicyPreprocess, Source, User
from app.db.session import SessionLocal

log = get_logger("jobs.seed")

SEED_DIR = Path(os.environ.get("SEED_DIR", Path(__file__).resolve().parents[3] / "seed"))


def seed_sources(db) -> int:  # noqa: ANN001
    """幂等 upsert：按 code 去重；已存在的源同步 url/adapter/config 等字段（seed 文件为准）。"""
    path = SEED_DIR / "sources.json"
    if not path.exists():
        log.warning("seed_file_missing", path=str(path))
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for row in rows:
        existing = db.scalar(select(Source).where(Source.code == row["code"]))
        if existing is None:
            db.add(Source(**row))
            created += 1
            continue
        for field, value in row.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
    db.commit()
    return created


def seed_cases(db) -> int:  # noqa: ANN001
    path = SEED_DIR / "cases.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for row in rows:
        if db.scalar(select(Case).where(Case.title == row["title"])):
            continue
        db.add(Case(**row))
        created += 1
    db.commit()
    return created


def seed_demo_subsidy_policy(db) -> int:  # noqa: ANN001
    """幂等插入一条「贴息」演示政策（高业务损失评分），供 consumer「为你推荐」展示。"""
    title = "中小企业贷款利息补贴（贴息）政策实施细则（合成演示数据）"
    if db.scalar(select(Policy).where(Policy.title == title)):
        return 0

    # 内部政策源（幂等：不存在才创建）
    source = db.scalar(select(Source).where(Source.code == "internal"))
    if source is None:
        source = Source(
            code="internal",
            name="内部政策（合成演示）",
            org="Policy Espresso",
            jurisdiction="CN",
            tier=1,
            adapter="manual",
            url="internal://demo",
            lang="zh-CN",
        )
        db.add(source)
        db.flush()

    hk_tz = timezone(timedelta(hours=8))
    now_hk = datetime.now(hk_tz)
    content_text = (
        "为加大对中小微企业的融资支持，对符合条件的制造业中小微企业贷款给予利息补贴（贴息），"
        "贴息范围包括流动资金贷款、技术改造贷款等，贴息比例最高不超过贷款利息的 50%。"
        "（本文件为合成演示数据，仅用于系统演示，不代表任何真实政策。）"
    )

    document = Document(
        source_id=source.id,
        url="internal://subsidy-demo",
        canonical_url="internal://subsidy-demo",
        title=title,
        lang="zh-CN",
        published_at=now_hk,
        content_text=content_text,
        content_hash=hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
        doc_type="internal",
        status="processed",
    )
    db.add(document)
    db.flush()

    policy = Policy(
        document_id=document.id,
        title=title,
        issuing_body="中华人民共和国财政部",
        jurisdiction="CN",
        policy_type="regulation",
        themes=["贷款与贴息"],
        published_at=now_hk,
        summary_zh="对符合条件的制造业中小微企业贷款给予利息补贴，降低企业融资成本，但对银行存量贷款定价形成下调压力。",
        status="published",
        priority="P1",
        score_total=92.0,
        confidence=0.9,
        target_entity_status="high",
        applicable_entities_text="符合条件的制造业中小微企业",
        applicable_scope="direct",
    )
    db.add(policy)
    db.flush()

    assessment = Assessment(
        policy_id=policy.id,
        scores={
            "relevance": {"score": 5, "reason": "直接涉及贷款贴息，与本行信贷业务高度相关", "evidence_ids": []},
            "exposure": {"score": 5, "reason": "贴息影响存量贷款定价，暴露规模大", "evidence_ids": []},
            "urgency": {"score": 4, "reason": "政策已发布，需尽快评估影响", "evidence_ids": []},
            "certainty": {"score": 4, "reason": "政策条款明确，影响方向清晰", "evidence_ids": []},
            "actionability": {"score": 5, "reason": "需调整信贷定价与客户沟通策略", "evidence_ids": []},
            "differential": {"score": 3, "reason": "对存量贴息客户与新增客户影响不同", "evidence_ids": []},
            "compliance": {"score": 4, "reason": "需关注贴息资金合规使用", "evidence_ids": []},
        },
        direction="negative",
        score_total=92.0,
        priority="P1",
        transmission_chain=[
            "贴息政策降低企业融资成本",
            "银行存量贷款面临定价下调压力",
            "利息收入减少，业务损失评分上升",
        ],
        affected={
            "business_lines": ["CIB", "GTB", "WPB"],
            "segments": ["制造业中小微企业", "有贴息资格客户"],
        },
        recommended_actions=[
            {"action": "评估存量贷款贴息影响，测算利息收入损失", "owner": "信贷管理", "deadline": "本周内"},
            {"action": "向受影响客户主动沟通贴息政策变化", "owner": "客户经理", "deadline": "两周内"},
        ],
        confidence=0.9,
        model="seed-demo",
    )
    db.add(assessment)
    db.commit()
    return 1


def _parse_dt(value):  # noqa: ANN001
    """把 seed JSON 里的时间字符串解析为 naive datetime（与 UTCDateTime 列存储一致）。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value).strip()
    for candidate in (s, s.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def seed_known_policies(db) -> int:  # noqa: ANN001
    """幂等导入「已知政策」快照（香港五年规划 + 广东贴息），上云空库启动时确保这两条政策存在。

    这两条是存量已知政策，不依赖每日抓取发现：香港规划门户页只有导言且过不了 gate1，
    广东贴息已被挤出列表前 3 页。故把它们的原文全文 + 分析结果固化为种子，保证上云可复现。
    """
    path = SEED_DIR / "known_policies.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for row in rows:
        title = (row.get("policy") or {}).get("title", "")
        if db.scalar(select(Policy).where(Policy.title == title)):
            continue  # 已存在，跳过（幂等）

        # 1) 确保 source 存在（seed 自包含：广东贴息源不在 sources.json 也会在此建立）
        src = dict(row.get("source") or {})
        source = db.scalar(select(Source).where(Source.code == src.get("code")))
        if source is None:
            source = Source(**src)
            db.add(source)
            db.flush()

        # 2) Document（含原文全文）
        doc_data = dict(row.get("document") or {})
        doc_data["source_id"] = source.id
        doc_data["published_at"] = _parse_dt(doc_data.get("published_at"))
        doc_data["fetched_at"] = datetime.now(timezone.utc)
        document = Document(**doc_data)
        db.add(document)
        db.flush()

        # 3) Policy
        pol_data = dict(row.get("policy") or {})
        for key in ("published_at", "effective_at", "expiry_at"):
            pol_data[key] = _parse_dt(pol_data.get(key))
        pol_data["document_id"] = document.id
        policy = Policy(**pol_data)
        db.add(policy)
        db.flush()

        # 4) Assessment（8 维 scores + 影响方向）
        a_data = dict(row.get("assessment") or {})
        db.add(Assessment(policy_id=policy.id, **a_data))
        created += 1
    db.commit()
    return created


def seed_rm_users(db) -> int:  # noqa: ANN001
    """建立 12 位合成客户经理的演示登录账号（rmdemo01~rmdemo12 / 密码 demo1234）。

    只有登录用户名与客户表 relationship_manager 匹配上，才会触发「为你推荐」规则 A。
    """
    password_hash = hashlib.sha256("demo1234".encode("utf-8")).hexdigest()
    created = 0
    for index in range(1, 13):
        username = f"rmdemo{index:02d}"
        if db.scalar(select(User).where(User.username == username)):
            continue
        db.add(User(username=username, password_hash=password_hash, role="consumer", onboarded=True))
        created += 1
    db.commit()
    return created


def seed_preprocess(db) -> int:  # noqa: ANN001
    """为存量政策补齐预处理记录（幂等：已存在则跳过）。"""
    from app.domain.preprocess import upsert_preprocess

    created = 0
    for policy in db.scalars(select(Policy)).all():
        if db.scalar(select(PolicyPreprocess).where(PolicyPreprocess.policy_id == policy.id)):
            continue
        upsert_preprocess(db, policy)
        created += 1
    db.commit()
    return created


def main() -> None:
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)  # 本地直跑兜底；docker 走 alembic
    with SessionLocal() as db:
        n_src = seed_sources(db)
        n_case = seed_cases(db)
        n_policy = seed_demo_subsidy_policy(db)
        n_known = seed_known_policies(db)
        n_rm = seed_rm_users(db)
        n_pre = seed_preprocess(db)
    print(
        f"seed 完成：新增数据源 {n_src}，案例 {n_case}，贴息演示政策 {n_policy}，"
        f"已知政策 {n_known}，客户经理账号 {n_rm}，预处理记录 {n_pre}"
    )


if __name__ == "__main__":
    main()

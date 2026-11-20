"""政策预处理表构建（抓取入库 + AI 分析后自动生成）。

一政策一条 PolicyPreprocess，字段服务于网站各页消费：关键词、影响业务、客户类型、
损失/盈利/信誉/机会百分比、汇丰与他行反应链接、市场实际应用等。

百分比口径**复用** domain/consumer_impact.compute_consumer_impact（不另起公式）：
- 损失 = business_loss（按受影响客户金额分档 + 方向因子）
- 信誉 = reputation_risk
- 机会 = business_opportunity
- 盈利 = 机会按影响方向折算（正向全额、利弊并存 60%、中性 30%、利空 0）
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Assessment, Policy, PolicyPreprocess
from app.domain.consumer_impact import affected_amount_by_business_lines, compute_consumer_impact
from app.domain.exposure import load_customers

log = get_logger("preprocess")

# 影响方向 → 盈利百分比折算因子（机会分本身已含方向因子，这里只表达"净盈利可能性"）
_PROFIT_FACTOR = {"positive": 1.0, "mixed": 0.6, "neutral": 0.3, "negative": 0.0}

# 机会维度的降级估算因子：与 consumer_impact 的方向因子保持同源口径
_OPPORTUNITY_FACTOR = {"positive": 1.0, "mixed": 0.85, "neutral": 0.75, "negative": 0.6}

# 合规/处罚类表述：影响声誉风险降级估算的上浮项
_RED_LINE_WORDS = ("处罚", "违规", "红线", "反洗钱", "制裁", "吊销", "清退", "风险提示")


def _dedup(values: list[Any], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


def _keywords(policy: Policy, corpus: str = "") -> tuple[list[str], list[str]]:
    """关键词：政策主题 + 主题拆词 + 发文机构 + 规则通道词表 + 联网检索语料中的业务词。

    返回 (全部关键词, 其中来自联网检索的关键词)，后者用于在页面上标注来源。
    """
    parts: list[str] = []
    for theme in policy.themes or []:
        parts.append(theme)
        parts.extend(re.split(r"[与和及、/\s]+", str(theme)))
    if policy.issuing_body:
        parts.append(policy.issuing_body)
    try:
        from app.ingest.gate1 import gate1_pass

        _, hits = gate1_pass(policy.title, policy.summary_zh or "")
        parts.extend(hits)
    except Exception:  # 关键词是增强项，失败不影响预处理落库
        log.warning("preprocess_keyword_failed", policy_id=policy.id)

    web_keywords: list[str] = []
    if corpus:
        web_keywords = _dedup(
            [keyword for keywords, _codes in _BUSINESS_KEYWORDS for keyword in keywords if keyword in corpus],
            6,
        )
        parts.extend(web_keywords)
    return _dedup(parts, 12), web_keywords


# 主题缺失/未命中业务图谱时的兜底：按标题与摘要里的业务关键词推断受影响业务线
_BUSINESS_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("小额贷款", "小贷", "贷款", "信贷", "贴息", "融资", "担保", "保理", "典当", "农信", "农商"),
     ("CIB", "GTB")),
    (("跨境", "贸易", "结算", "外汇", "自贸", "CEPA", "进出口"), ("GTB", "CIB")),
    (("理财", "零售", "个人", "存款", "按揭", "信用卡", "财富管理"), ("WPB",)),
    (("保险", "再保险"), ("Insurance", "WPB")),
    (("证券", "基金", "债券", "上市", "资管", "信托", "资产管理"), ("CIB", "WPB")),
    (("监管", "资质", "牌照", "处罚", "注销", "备案", "许可", "检查"), ("CIB",)),
)


def _line_by_code(code: str) -> dict | None:
    from app.domain.business_map import load_business_map

    for line in load_business_map():
        if line.code == code:
            return {
                "code": line.code, "name": line.name, "sensitive_themes": {},
                "segments": line.segments, "products": line.products,
            }
    return None


def _fallback_lines(policy: Policy, corpus: str = "", limit: int = 2) -> list[dict]:
    """主题未命中时，用业务关键词兜底推断业务线（联网语料也参与判定）。"""
    haystack = f"{policy.title or ''}\n{policy.summary_zh or ''}\n{corpus}"
    for keywords, codes in _BUSINESS_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            lines = [line for line in (_line_by_code(code) for code in codes) if line]
            if lines:
                return lines[:limit]
    default = _line_by_code("CIB")  # 兜底：按对公业务口径
    return [default] if default else []


def _business_slice(policy: Policy, corpus: str = "") -> tuple[list[dict], str]:
    """返回 (业务线切片, 口径说明)。主题缺失时先派生主题，再按关键词兜底。

    `corpus` 为联网检索到的公开报道语料，参与业务关键词兜底，提升地方性政策
    （标题里没有标准业务术语）的识别率。
    """
    themes = [str(t) for t in (policy.themes or []) if t]
    if not themes:
        try:
            from app.domain.offline_fallback import detect_themes

            themes = detect_themes(policy.title or "", policy.summary_zh or "")
        except Exception:
            log.warning("preprocess_theme_derive_failed", policy_id=policy.id)
    try:
        from app.domain.business_map import slice_for_themes

        lines = list(slice_for_themes(themes).get("business_lines") or [])
    except Exception:
        log.warning("preprocess_business_map_failed", policy_id=policy.id)
        lines = []
    if lines:
        basis = "主题命中业务图谱" if policy.themes else "标题/摘要派生主题后命中业务图谱"
        return lines, basis
    basis = "主题未命中业务图谱，按业务关键词规则推断"
    if corpus:
        corpus_words = [
            keyword for keywords, _codes in _BUSINESS_KEYWORDS
            for keyword in keywords if keyword in corpus
        ]
        if corpus_words:
            basis = f"主题未命中业务图谱，结合联网检索结果（{'、'.join(_dedup(corpus_words, 2))}）按业务关键词推断"
    return _fallback_lines(policy, corpus), basis


def infer_business_lines(policy: Policy, corpus: str = "") -> list[str]:
    """政策影响业务线兜底推断：主题命中业务图谱 → 业务关键词规则 → 默认对公（CIB）。

    入库分析与列表展示共用同一口径，避免「影响 Domain」为空。
    """
    lines, _basis = _business_slice(policy, corpus)
    return [str(line["code"]) for line in lines if line.get("code")]


# 政策文本命中某类业务时，按客群名收窄（避免同类政策客群一律铺满，看不出差异）
_SEGMENT_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("个人", "零售", "理财", "存款", "按揭", "信用卡"),
     ("个人", "零售", "理财", "财富")),
    (("跨境", "外贸", "进出口", "结算", "外汇", "自贸"),
     ("跨境", "外贸", "进出口", "跨境电商")),
    (("小微", "小贷", "小额贷款", "制造业", "贴息", "融资", "担保"),
     ("中小", "小微", "制造业")),
    (("保险",), ("保险",)),
)


def _customer_segments(lines: list[dict], policy: Policy | None = None, corpus: str = "") -> list[str]:
    """客户类型：业务图谱的客群 + 合成客户表里同业务线实际出现的客群。

    再按政策文本里的业务类别做一次收窄：命中「个人/跨境/小微/保险」等词时，
    只保留对应类别的客群；收窄后为空则保留全量，保证不会变成空列。
    """
    segments: list[str] = []
    codes = {line.get("code") for line in lines if line.get("code")}
    for line in lines:
        segments.extend(line.get("segments") or [])
    if codes:
        segments.extend(
            c.get("segment", "")
            for c in load_customers()
            if c.get("business_line") in codes
        )
    segments = _dedup(segments, 8)
    if not segments or policy is None:
        return segments

    haystack = f"{policy.title or ''}{policy.summary_zh or ''}{corpus}"
    for triggers, keywords in _SEGMENT_HINTS:
        if any(trigger in haystack for trigger in triggers):
            narrowed = [s for s in segments if any(keyword in s for keyword in keywords)]
            if narrowed:
                return narrowed[:6]
    return segments


def _score_of(scores: dict | None, key: str) -> float | None:
    """取某一维评分（兼容 {dim: 4.0} 与 {dim: {"score": 4.0}}）；缺失返回 None（≠0）。"""
    if not scores:
        return None
    value = scores.get(key)
    if isinstance(value, dict):
        value = value.get("score")
    if value is None:
        return None
    try:
        return max(0.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        return None


def percentages(
    scores: dict | None,
    direction: str | None,
    *,
    affected_amount_cny_yi: float = 0.0,
    affected_customer_count: int = 0,
    red_line: bool = False,
    relevance_floor: float = 0.0,
) -> dict:
    """四维分 → 四个业务百分比（0–100）+ 综合分。

    优先走 compute_consumer_impact 的既定口径；当「行动性/差异化」维度缺失或为 0
    （离线规则只能判相关度/紧迫度/确定性时）用同源维度做**降级估算**，
    并在 estimated 中标注，避免整列展示默认值 0。
    `relevance_floor` 仅在降级估算时生效：政策命中业务关键词说明确有业务关联，
    按中位相关度兜底，避免"主题未识别"被当成"零影响"。
    """
    dims = compute_consumer_impact(
        scores, direction=direction,
        affected_amount_cny_yi=affected_amount_cny_yi,
        affected_customer_count=affected_customer_count,
    )
    if dims.get("no_direct_impact"):
        # 未提及本行且无红线/差异条款：不做降级估算，避免所有无关政策
        # 被同一套"相关度兜底 + 金额档位"算成完全相同的四个百分比。
        return {
            "loss_pct": 0.0, "profit_pct": 0.0, "reputation_pct": 0.0,
            "opportunity_pct": 0.0, "impact_total": 0.0,
            "business_loss": 0, "business_opportunity": 0, "reputation_risk": 0,
            "estimated": [],
            "basis": "规则/模型判定本行不在适用范围内（相关度为 0），不做影响估算",
        }
    loss = float(dims["business_loss"])
    opportunity = float(dims["business_opportunity"])
    reputation = float(dims["reputation_risk"])
    estimated: list[str] = []

    relevance = _score_of(scores, "relevance") or 0.0
    urgency = _score_of(scores, "urgency") or 0.0
    certainty = _score_of(scores, "certainty") or 0.0

    actionability = _score_of(scores, "actionability")
    differential = _score_of(scores, "differential")
    weak_opportunity = actionability in (None, 0.0) and differential in (None, 0.0)
    if weak_opportunity:
        base = (max(relevance, relevance_floor) * 0.5 + urgency * 0.3 + certainty * 0.2) / 5 * 100
        opportunity = round(min(100.0, base * _OPPORTUNITY_FACTOR.get(direction or "neutral", 0.75)), 1)
        estimated.append("business_opportunity")
    compliance = _score_of(scores, "compliance")
    if compliance in (None, 0.0):
        base_relevance = max(relevance, relevance_floor)
        reputation = round(min(100.0, base_relevance / 5 * 55 + (25 if red_line else 0)), 1)
        estimated.append("reputation_risk")

    factor = _PROFIT_FACTOR.get(direction or "neutral", 0.3)
    return {
        "loss_pct": round(loss, 1),
        "profit_pct": round(opportunity * factor, 1),
        "reputation_pct": round(reputation, 1),
        "opportunity_pct": round(opportunity, 1),
        "impact_total": round((loss + opportunity + reputation) / 3, 1),
        "business_loss": int(loss),
        "business_opportunity": int(opportunity),
        "reputation_risk": int(reputation),
        "estimated": estimated,
    }


def percentages_for(
    policy: Policy | None,
    assessment: Assessment | None,
    lines: list[dict] | None = None,
) -> dict:
    """对外统一的百分比口径（预处理 Agent 覆写业务线后也用它重算，不允许模型自造百分比）。"""
    if assessment is None:
        return {
            "loss_pct": 0.0, "profit_pct": 0.0,
            "reputation_pct": 0.0, "opportunity_pct": 0.0,
            "impact_total": 0.0, "direction": "neutral",
            "affected_amount_cny_yi": 0.0, "affected_customer_count": 0,
            "estimated": [],
        }
    # 敞口口径：评估里给了业务线优先用它；评估没给（主题未识别）用预处理推断的业务线，
    # 避免退回"全量客户"导致损失虚高、客户数=122。
    business_lines = (assessment.affected or {}).get("business_lines") or []
    if not business_lines and lines:
        business_lines = [line.get("code") for line in lines if line.get("code")]
    amount, count = affected_amount_by_business_lines(business_lines) if business_lines else (0.0, 0)

    text = f"{policy.title or ''}{policy.summary_zh or ''}" if policy else ""
    red_line = any(word in text for word in _RED_LINE_WORDS)
    return {
        **percentages(
            assessment.scores, assessment.direction,
            affected_amount_cny_yi=amount, affected_customer_count=count, red_line=red_line,
            relevance_floor=2.0 if lines else 1.0,
        ),
        "direction": assessment.direction or "neutral",
        "affected_amount_cny_yi": amount,
        "affected_customer_count": count,
    }


def _topic_terms(policy: Policy) -> list[str]:
    """检索主题词：政策主题优先；无主题时从标题/摘要里抽取业务关键词。

    只使用公开信息（政策主题、标题、业务词），确保出网内容不含任何非公开数据。
    """
    terms: list[str] = []
    for theme in policy.themes or []:
        terms.append(str(theme))
        terms.extend(re.split(r"[与和及、/\s]+", str(theme)))
    if not terms:
        text = f"{policy.title or ''}{policy.summary_zh or ''}"
        for keywords, _codes in _BUSINESS_KEYWORDS:
            terms.extend(keyword for keyword in keywords if keyword in text)
    return _dedup([term for term in terms if len(term) >= 2], 4)


def _main_term(terms: list[str]) -> str:
    """检索主词：复合主题取最后一段（如「贷款与贴息」→「贴息」），更具体、少噪声。"""
    for term in terms:
        if any(sep in term for sep in "与和及、/"):
            parts = [p for p in re.split(r"[与和及、/\s]+", term) if len(p) >= 2]
            if parts:
                return parts[-1]
    return terms[0] if terms else ""


# 与"政策反应/落地案例"无关的结果特征：机构首页、百科、产品申请页、考试/政务服务入口
_NOISE_TITLE_WORDS = (
    "官网", "网站", "百科", "首页", "信用卡", "理财", "开户", "在线申请", "公务员",
    "政务服务", "个人金融", "个人贷款", "易贷", "贷款网", "产品介绍",
)
_NOISE_HOST_WORDS = (
    "baike.baidu.com", "wikipedia.org", "zhihu.com", "ggfw.", "gwyks",
    "weibo.com", "hstong.com", "jiededao.cn",
)
# 更像"回应/落地"的信号词，用于排序加权
_NEWS_HINTS = ("回应", "新闻", "公告", "通知", "发布", "政策", "实施", "落地", "措施", "解读")


def _rank_by_relevance(
    items: list, terms: list[str], must_words: tuple[str, ...], min_hits: int = 2,
) -> list[dict]:
    """按命中政策主题词的数量排序，并要求命中目标实体词（汇丰/银行）。

    宁可少给，也不把官网首页、百科、贷款产品页当成"政策反应"塞给用户。
    `min_hits` 为至少命中的主题词数（主题词少时自动取较小值）。
    """
    ranked: list[tuple[int, dict]] = []
    need = max(1, min(min_hits, len(terms))) if terms else 0
    for item in items:
        url = (item.citation or {}).get("url", "")
        blob = f"{item.title} {(item.text or '')}"
        if any(word in item.title for word in _NOISE_TITLE_WORDS):
            continue
        if any(word in url for word in _NOISE_HOST_WORDS):
            continue
        if must_words and not any(word.lower() in blob.lower() for word in must_words):
            continue
        hits = sum(1 for term in terms if term.lower() in blob.lower())
        if terms and hits < need:
            continue
        # 必须是新闻/政策类内容，纯产品页与栏目页不算"反应/落地"
        if not any(hint in blob for hint in _NEWS_HINTS):
            continue
        score = hits * 2 + sum(1 for hint in _NEWS_HINTS if hint in blob)
        summary = (item.text or "").strip()[:200] or (item.title or "").strip()
        ranked.append((score, {"summary": summary, "url": url}))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _score, item in ranked]


def normalize_research_items(items: list | None) -> list[dict]:
    """把外部检索结果统一为「简述 + 原文链接」两项。

    兼容历史结构 {title, url, source, snippet}：简述优先取 snippet，其次 title；
    同时按 url 去重、丢弃空链接，保证前端只处理 summary/url 两种字段。
    """
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        summary = str(
            item.get("summary") or item.get("snippet") or item.get("title") or ""
        ).strip()
        seen.add(url)
        normalized.append({"summary": summary[:200], "url": url})
    return normalized


def _research(policy: Policy) -> dict:
    """联网检索汇丰/他行反应与市场应用；失败或无网络一律降级为空数组 + 说明。

    出网边界：query 只包含政策主题/标题与公开关键词（汇丰、银行、案例），
    不发送客户数据、内部评分、内部批注。
    """
    empty = {"hsbc_response": [], "peer_bank_response": [], "market_applications": []}
    try:
        from app.chat.web_search import WebSearchError, search_web

        terms = _topic_terms(policy)
        main_term = _main_term(terms) or (policy.title or "")[:16]
        queries = {
            "hsbc_response": f"汇丰 {main_term} 政策 回应 新闻",
            "peer_bank_response": f"{main_term} 政策 银行 应对 新闻",
            "market_applications": f"{main_term} 政策 落地 案例 新闻",
        }
        must_words = {
            "hsbc_response": ("汇丰", "HSBC"),
            "peer_bank_response": ("银行",),
            "market_applications": (),
        }
        result = {}
        for key, query in queries.items():
            try:
                found = search_web(query, limit=6)
            except WebSearchError as exc:
                result[key] = []
                result.setdefault("research_note", f"{key} 检索失败：{exc}")
                continue
            # 这三类内容在中文公开网络上本就稀疏：主题词命中门槛取 1，
            # 靠 must_words（汇丰/银行）与新闻信号词保证不跑偏。
            result[key] = _rank_by_relevance(found, terms, must_words[key], min_hits=1)[:3]
        # 同一链接不在多个类别重复出现（优先保留汇丰/他行，市场类去重）
        used_urls = {
            item["url"]
            for key in ("hsbc_response", "peer_bank_response")
            for item in result.get(key, [])
        }
        result["market_applications"] = [
            item for item in result.get("market_applications", []) if item["url"] not in used_urls
        ]
        all_items = [
            item for key in ("hsbc_response", "peer_bank_response", "market_applications")
            for item in result.get(key, [])
        ]
        # 联网语料：供关键词、业务线、客户类型判定复用，避免"联网只为填三个链接"
        corpus = " ".join(item["summary"] for item in all_items)[:4000]
        return {**empty, **result, "corpus": corpus, "total": len(all_items)}
    except Exception as exc:  # 预处理不应因联网失败而中断
        log.warning("preprocess_research_failed", policy_id=policy.id, error=f"{type(exc).__name__}: {exc}")
        return {**empty, "research_note": f"联网检索不可用：{type(exc).__name__}"}


def build_payload(
    policy: Policy,
    assessment: Assessment | None,
    *,
    research: bool = False,
    provider_name: str = "offline-rules",
) -> dict:
    # 先联网（默认开启），再用检索到的公开语料参与关键词/业务线/客户类型的提取
    from app.core.config import get_settings

    do_research = research or get_settings().preprocess_web_research
    found = _research(policy) if do_research else {}
    corpus = found.get("corpus", "")

    lines, business_basis = _business_slice(policy, corpus)
    pct = percentages_for(policy, assessment, lines)
    keywords, web_keywords = _keywords(policy, corpus)
    payload = {
        "keywords": keywords,
        "affected_business": [
            {"code": line.get("code"), "name": line.get("name", "")} for line in lines if line.get("code")
        ],
        "customer_segments": _customer_segments(lines, policy, corpus),
        "loss_pct": pct["loss_pct"],
        "profit_pct": pct["profit_pct"],
        "reputation_pct": pct["reputation_pct"],
        "opportunity_pct": pct["opportunity_pct"],
        "impact_total": pct["impact_total"],
        "direction": pct["direction"],
        "extras": {
            "amounts": policy.amounts or [],
            "deadlines": policy.deadlines or [],
            "obligations": policy.obligations or [],
            "incentives": policy.incentives or [],
            "affected_amount_cny_yi": pct["affected_amount_cny_yi"],
            "affected_customer_count": pct["affected_customer_count"],
            "business_basis": business_basis,
            "estimated_dimensions": pct.get("estimated", []),
            "percentage_basis": (
                "四维评分含降级估算（相关度/紧迫度/确定性推导，非模型判断）"
                if pct.get("estimated") else "影响分析四维评分直接换算"
            ),
            "exposure_basis": "seed/synthetic_customers.json（合成演示数据，非真实客户）",
            "web_research": bool(do_research),
            "web_evidence_count": int(found.get("total", 0)),
            "web_keywords": web_keywords,
            "research_note": (
                "未检索公开网络（PREPROCESS_WEB_RESEARCH 已关闭）"
                if not do_research else "公开网络未检索到直接相关结果"
            ),
        },
        "source": provider_name,
        "prompt_version": (assessment.prompt_version if assessment else "") or "",
        "confidence": float(assessment.confidence) if assessment else 0.0,
    }

    if do_research:
        payload["hsbc_response"] = found.get("hsbc_response", [])
        payload["peer_bank_response"] = found.get("peer_bank_response", [])
        payload["market_applications"] = found.get("market_applications", [])
        total = int(found.get("total", 0))
        if found.get("research_note"):
            payload["extras"]["research_note"] = found["research_note"]
        elif total:
            payload["extras"]["research_note"] = (
                f"已联网检索到 {total} 条公开结果，其中 {len(web_keywords)} 个业务词已用于关键词与业务判定"
            )
        else:
            payload["extras"]["research_note"] = "公开网络未检索到直接相关结果"
    return payload


def upsert_preprocess(
    db: Session,
    policy: Policy,
    *,
    assessment: Assessment | None = None,
    research: bool = False,
    provider_name: str | None = None,
    use_agent: bool | None = None,
) -> PolicyPreprocess:
    """生成/更新政策预处理记录（幂等：同政策只保留一条）。

    `use_agent`：默认跟随 PREPROCESS_AGENT_ENABLED。
    开启时由政策流水线 Agent 在规则结果之上复核/补全（读原文、业务图谱、客户暴露、公开检索），
    Agent 不可用或调用失败时自动退回规则结果。
    """
    if assessment is None:
        assessment = db.scalars(select(Assessment).where(Assessment.policy_id == policy.id)).first()
    record = db.scalars(select(PolicyPreprocess).where(PolicyPreprocess.policy_id == policy.id)).first()
    if record is None:
        record = PolicyPreprocess(policy_id=policy.id)
        db.add(record)
    payload = build_payload(
        policy, assessment, research=research,
        provider_name=provider_name or (assessment.model if assessment and assessment.model else "offline-rules"),
    )
    from app.core.config import get_settings

    if use_agent is not False and get_settings().preprocess_agent_enabled:
        from app.agent.preprocess_agent import refine_preprocess_payload

        payload = refine_preprocess_payload(db, policy, assessment, payload)
    for key, value in payload.items():
        setattr(record, key, value)
    db.flush()
    return record

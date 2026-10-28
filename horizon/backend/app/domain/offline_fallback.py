"""离线规则兜底：未接入真实 LLM 时，从政策原文派生结构化字段。

MockProvider 的样例应答对任意输入都返回同一条政策（tests/fixtures/mock_responses/*.json
的 `__default__`），会把抓取到的每篇文档写成同一份标题/摘要/金额。本模块提供一条
不依赖 LLM 的确定性路径：字段全部来自原文与规则通道，宁可信息少，也不写与原文无关的内容。

由 settings.llm_offline_rules 开关控制（默认关闭，保证既有管线测试的确定性）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 主题受控词表（seed/themes.yaml）→ 原文关键词；命中即打标，不猜测词表外的主题。
# 关键词只取"主题本身的说法"，不放"债券/基金/监管"这类金融通稿高频词，否则每篇文档都会被打满标签。
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "跨境支付": ("跨境支付", "支付系統", "支付系统", "快速支付系統", "转数快", "跨境匯款", "跨境汇款"),
    "人民币国际化": ("離岸人民幣", "离岸人民币", "人民幣債券", "人民币债券", "人民幣國債", "人民币国债",
                 "債務工具中央結算", "债务工具中央结算", "人民幣業務", "人民币业务"),
    "贷款与贴息": ("貸款貼息", "贷款贴息", "貼息", "贴息", "信貸投放", "信贷投放", "貸款市場報價利率", "贷款市场报价利率"),
    "跨境理财通": ("跨境理財通", "跨境理财通", "理財通", "理财通", "財富管理聯動"),
    "债券与资本市场": ("債券投標", "债券投标", "票據投標", "票据投标", "承銷", "承销", "首次公開招股",
                  "上市規則", "上市规则", "交易所買賣基金", "结构性票据"),
    "保险与再保险": ("保險業", "保险业", "再保險", "再保险", "虛擬銀行保險", "保險公司", "保险公司"),
    "资产管理": ("資產管理", "资产管理", "家族辦公室", "家族办公室", "私人銀行", "私人银行", "基金管理公司", "信託", "信托"),
    "税务与优惠": ("徵收稅項", "税收优惠", "稅務安排", "税务安排", "豁免稅項", "預算案", "预算案", "印花稅", "印花税"),
    "数据跨境": ("數據跨境", "数据跨境", "個人信息跨境", "跨境資料", "數據出境", "数据出境", "保障資料", "保障数据"),
    "绿色与转型金融": ("綠色金融", "绿色金融", "可持續發展", "可持续发展", "轉型金融", "转型金融", "綠色債券", "绿色债券"),
    "金融科技与虚拟资产": ("穩定幣", "稳定币", "虛擬資產", "虚拟资产", "加密資產", "加密资产", "生成式人工智能"),
    "专业资格互认": ("專業資格", "专业资格", "資格互認", "资格互认", "專業人士互認"),
    "市场准入与牌照": ("牌照", "發牌", "发牌", "准入", "認可機構", "认可机构", "試點", "试点"),
    "资本与流动性要求": ("資本充足", "资本充足", "流動資金", "流动资金", "流動性覆蓋率", "流动性覆盖率",
                    "淨穩定資金", "净稳定资金", "監管儲備", "监管储备"),
    "消费者保护": ("消費者保障", "消费者保障", "客戶投訴", "客户投诉", "理財產權", "销售安排", "銷售安排", "披露安排"),
    "反洗钱与制裁": ("洗錢", "洗钱", "恐怖資金", "恐怖资金", "制裁", "可疑交易", "打擊金融罪案"),
}

_NOISE = re.compile(r"^[|\-—•\s]*$")
_DATE_ONLY = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$")
_TABLE_CELL = re.compile(r"^\s*\|?.*\|\s*$")

# 只在标题中出现才计入主题：这类词在新闻汇总页正文里一条标题就能命中整页，
# 但出现在标题中说明文档本身讲的就是这个主题。
TITLE_ONLY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "金融科技与虚拟资产": ("人工智能", "金融科技", "數碼轉型", "数码转型"),
}


def _plain_lines(content_text: str) -> list[str]:
    """取正文中可用的叙述行：跳过表格、日期行、导航残留与过短片段。"""
    lines: list[str] = []
    for raw in (content_text or "").splitlines():
        line = raw.strip()
        if not line or _NOISE.match(line) or _DATE_ONLY.match(line):
            continue
        if "|" in line or "\t" in line:
            continue
        if len(line) < 24:
            continue
        lines.append(line)
    return lines


def detect_themes(title: str, content_text: str) -> list[str]:
    haystack = f"{title}\n{content_text or ''}"
    doc_title = title or ""
    matched = {theme for theme, keywords in THEME_KEYWORDS.items()
               if any(keyword and keyword in haystack for keyword in keywords)}
    matched |= {theme for theme, keywords in TITLE_ONLY_KEYWORDS.items()
                if any(keyword and keyword in doc_title for keyword in keywords)}
    return [theme for theme in THEME_KEYWORDS if theme in matched]


def derive_summary(title: str, content_text: str, issuing_body: str, limit: int = 180) -> str:
    lines = _plain_lines(content_text)
    body = ""
    for line in lines:
        if title and line.startswith(title[:8]):
            continue
        body = line
        break
    if not body:
        return ""
    if len(body) > limit:
        body = body[:limit].rstrip("，,、；;。 ") + "……"
    prefix = f"{issuing_body}发布《{title}》。" if issuing_body and issuing_body not in body else ""
    return f"{prefix}{body}"[: limit + 40]


def detect_policy_type(title: str, content_text: str) -> str:
    head = f"{title}\n{(content_text or '')[:600]}"
    if any(k in head for k in ("征求意見", "征求意见", "諮詢文件", "咨询文件", "consultation")):
        return "consultation"
    if any(k in head for k in ("新聞稿", "新闻稿", "公關稿", "媒体回应", "press release", "投標結果", "结果")):
        return "press_release"
    if any(k in head for k in ("通知", "通告", "指引", "規例", "规例", "守則", "守则")):
        return "circular"
    return "other"


def offline_extract(*, doc_title: str, content_text: str, source_name: str,
                    jurisdiction: str) -> dict:
    """P2 抽取的离线替代：只填原文可支撑的字段，其余留空。"""
    title = (doc_title or "").strip()
    issuing_body = (source_name or "").strip()
    themes = detect_themes(title, content_text)
    return {
        "title": title,
        "issuing_bodies": [issuing_body] if issuing_body else [],
        "doc_number": None,
        "published_at": None,
        "effective_at": None,
        "expiry_at": None,
        "themes": themes,
        "summary_zh": derive_summary(title, content_text, issuing_body),
        "applicable_entities_text": "",
        "applicable_scope": "unclear",
        "amounts": [],
        "deadlines": [],
        "obligations": [],
        "incentives": [],
        "confidence": 0.0,
        "policy_type": detect_policy_type(title, content_text),
        "jurisdictions": [jurisdiction] if jurisdiction else [],
        "targets": [],
    }


def offline_scope(rule) -> dict:
    """P3 的离线替代：完全采用规则通道结论，不声称模型判过相关性。"""
    from app.domain.scope_rules import entity_relevance_from_scope

    hit = rule.hits[0] if rule.hits else None
    reason = (
        f"规则通道：{hit.category} 命中“{hit.quote}”" if hit
        else "规则通道未命中适用主体表述，需人工判断"
    )
    results = [{
        "entity_id": entity_id,
        "relevance": entity_relevance_from_scope(entity_id, rule.relevance),
        "reason": reason,
        "evidence": [],
    } for entity_id in ("hsbc_hk", "hsbc_cn")]
    return {
        "results": results,
        "foreign_bank_differential": any(h.category == "low" for h in rule.hits),
        "group_affiliate_mention": rule.group_affiliate_mention or {"mentioned": False, "entities": [], "note": ""},
        "differential_note": "",
        "ambiguity": ["未接入 AI 分析，适用范围仅由规则通道给出"],
    }


def affected_business_lines(themes: list[str]) -> list[str]:
    """按主题命中的高敏感业务线（规则切片，非模型判断）。"""
    from app.domain.business_map import slice_for_themes

    return [line["code"] for line in slice_for_themes(themes).get("business_lines", []) if line.get("code")]


# 8 维评分卡（02 §5.2）里可由规则通道与政策字段直接支撑的维度映射。
# 每一条分数都必须能在 reason 里指出来源；无依据的维度一律 None 并注明缺什么，
# 不允许用"可能有影响"凑分（05-P4 硬性要求）。
RELEVANCE_SCORE = {"high": 5, "medium": 3, "low": 1, "not_mentioned": 0, "na": 0}

# certainty：按文件类型与生效状态派生。law/regulation 已颁布即确定性高；
# consultation/press_release 条款仍可能调整；effective_at 有值时以生效状态为准。
CERTAINTY_BY_TYPE = {
    "law": 4, "regulation": 4, "guideline": 3, "circular": 3,
    "consultation": 2, "press_release": 2, "other": 2,
}

# compliance：命中红线主题给 4 并提示报备；未命中按 0（基于受控词表，非全文结论）。
RED_LINE_THEMES = ("资本与流动性要求", "反洗钱与制裁", "消费者保护", "数据跨境")

ENTITY_LABELS = {"hsbc_hk": "香港汇丰", "hsbc_cn": "汇丰（中国）"}
RELEVANCE_LABELS = {"high": "高相关", "medium": "中相关", "low": "低相关",
                    "not_mentioned": "未提及", "na": "不适用"}


def _exposure_score(exposure: dict | None) -> int | None:
    """暴露规模按合成口径余额区间保守分档（区间上限，单位亿）。"""
    if not exposure:
        return None
    high = float(exposure.get("high") or 0)
    if high >= 100:
        return 4
    if high >= 20:
        return 3
    if high >= 5:
        return 2
    return 1


def offline_impact(
    themes: list[str],
    *,
    relevance_by_entity: dict[str, str],
    policy_type: str = "other",
    effective_at=None,
    foreign_bank_differential: bool = False,
    differential_quotes: list[str] | None = None,
    exposure: dict | None = None,
) -> dict:
    """P4 的离线替代：只对规则通道与政策字段可支撑的维度打分（02 §5.2），
    其余维度置 None 并说明缺什么，不编造影响结论。"""
    from app.domain.scoring import DIMENSIONS

    best = max(relevance_by_entity.values(), key=lambda v: RELEVANCE_SCORE.get(v, 0), default="not_mentioned")
    entity_note = "；".join(
        f"{ENTITY_LABELS.get(entity, entity)} {RELEVANCE_LABELS.get(value, value)}"
        for entity, value in relevance_by_entity.items()
    ) or "无目标实体判定"

    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    scores: dict[str, dict] = {}

    scores["relevance"] = {
        "score": RELEVANCE_SCORE.get(best, 0),
        "reason": f"规则通道相关性判定：{entity_note}（未经模型判断）",
        "evidence_ids": [],
    }

    if exposure:
        scores["exposure"] = {
            "score": _exposure_score(exposure),
            "reason": f"合成客户暴露口径：{exposure.get('basis') or '见暴露口径说明'}；量级需人工核实真实数据",
            "evidence_ids": [],
        }
    else:
        scores["exposure"] = {
            "score": None,
            "reason": "缺少客户暴露数据（合成数据集未覆盖该主题），需人工补充口径",
            "evidence_ids": [],
        }

    if effective_at is not None:
        days = (effective_at.date() - today).days
        if days <= 0:
            urgency, note = 5, f"生效日 {effective_at.date()} 已到，动作窗口紧迫"
        elif days <= 30:
            urgency, note = 5, f"距生效日不足 30 天（{effective_at.date()}）"
        elif days <= 90:
            urgency, note = 3, f"距生效日 30–90 天（{effective_at.date()}）"
        else:
            urgency, note = 2, f"距生效日超过 90 天（{effective_at.date()}），时间窗充裕"
        scores["urgency"] = {"score": urgency, "reason": note, "evidence_ids": []}
    else:
        scores["urgency"] = {
            "score": None,
            "reason": "原文未给出生效/申报截止日期，时间窗无法评定",
            "evidence_ids": [],
        }

    if effective_at is not None:
        certainty = 5 if effective_at.date() <= today else 3
        state = "已生效" if certainty == 5 else "已颁布未生效"
        scores["certainty"] = {
            "score": certainty,
            "reason": f"生效日 {effective_at.date()}：{state}",
            "evidence_ids": [],
        }
    else:
        certainty = CERTAINTY_BY_TYPE.get(policy_type)
        if certainty is None:
            scores["certainty"] = {"score": None, "reason": "文件类型未识别，正文效力需人工确认", "evidence_ids": []}
        else:
            scores["certainty"] = {
                "score": certainty,
                "reason": f"按文件类型派生：{policy_type}；生效日期原文未明确",
                "evidence_ids": [],
            }

    scores["actionability"] = {
        "score": None,
        "reason": "可行动性（30 天内能否采取具体动作）需人工结合业务判断，规则通道不下结论",
        "evidence_ids": [],
    }

    if foreign_bank_differential:
        quotes = "、".join(f"“{q}”" for q in list(dict.fromkeys(differential_quotes or []))[:3])
        scores["differential"] = {
            "score": 5,
            "reason": f"规则通道命中外资行差异条款 {quotes}：外资行被排除或区别对待（核心维度）".replace("  ", " "),
            "evidence_ids": [],
        }
    else:
        scores["differential"] = {
            "score": 0,
            "reason": "规则通道未命中对外资行的差异限定表述；不排除漏检，需人工复核适用主体段落",
            "evidence_ids": [],
        }

    red_lines = [t for t in themes if t in RED_LINE_THEMES]
    if red_lines:
        scores["compliance"] = {
            "score": 4,
            "reason": f"主题命中监管红线领域：{'、'.join(red_lines)}；是否涉及报备/合规程序需人工确认",
            "evidence_ids": [],
        }
    else:
        scores["compliance"] = {
            "score": 0,
            "reason": "主题标签未命中资本/流动性/反洗钱/消保等红线领域（基于受控词表，非全文结论）",
            "evidence_ids": [],
        }

    if best in ("high", "medium"):
        chain = [
            "政策条款生效（施行安排以原文生效日为准）",
            "→ 对适用主体的业务经营、申报或待遇产生影响",
            "→ 待人工确认对汇丰业务线与客户行为的具体传导",
            "→ 业务线主管评估应对动作与时间窗",
        ]
    else:
        chain = [
            "规则通道判定适用范围不含汇丰两个目标实体",
            "→ 归档观察；若人工复核发现误判，恢复分析",
        ]

    today_iso = today.isoformat()
    actions = [{
        "owner": "analyst.default",
        "action": "阅读原文并复核规则通道的相关性判定与影响维度",
        "deadline": (today + timedelta(days=1)).isoformat(),
    }]
    if foreign_bank_differential:
        actions.append({
            "owner": "reviewer.l2",
            "action": "评估外资行差异条款的影响范围，确认是否启动倡导性应对",
            "deadline": (today + timedelta(days=3)).isoformat(),
        })
    if exposure:
        actions.append({
            "owner": "business.cmb",
            "action": "按合成暴露口径排查相关客户，并核实用真实数据",
            "deadline": (today + timedelta(days=3)).isoformat(),
        })

    unknowns = [
        "各维度评分由规则通道与政策字段派生，未经模型判断，需人工复核",
    ]
    if exposure is None:
        unknowns.append("缺少客户暴露数据，暴露规模无法评定")
    if effective_at is None:
        unknowns.append("原文未给出生效日期，紧迫性无法评定")

    direction = "negative" if foreign_bank_differential else "neutral"
    return {
        "scores": {dim: scores[dim] for dim in DIMENSIONS},
        "direction": direction,
        "transmission_chain": chain,
        "confidence": 0.5 if best in ("high", "medium") else 0.4,
        "affected": {
            "business_lines": affected_business_lines(themes),
            "segments": [],
            "exposure_range": exposure,
        },
        "recommended_actions": actions,
        "case_links": [],
        "unknowns": unknowns,
    }


def offline_alert(policy, entity_relevance: dict[str, str]) -> str:
    """P5 的离线替代：六段结构占位，内容全部来自已入库的规则结论，不含推测。"""
    entity_labels = {"hsbc_hk": "香港汇丰", "hsbc_cn": "汇丰（中国）"}
    relevance_labels = {"high": "高相关", "medium": "中相关", "low": "低相关",
                        "not_mentioned": "未提及", "na": "不适用"}
    who = "、".join(
        f"{entity_labels.get(entity, entity)}（{relevance_labels.get(value, value)}）"
        for entity, value in entity_relevance.items()
    ) or "待人工确认"
    themes = "、".join(policy.themes) or "未命中标签词表"
    scored = (
        f"规则通道派生综合分 {policy.score_total} / 优先级 {policy.priority}"
        if getattr(policy, "score_total", 0)
        else "影响分析待人工评定"
    )
    return (
        f"【一句话结论】《{policy.title[:60]}》已入库，{scored}，未经人工审核不得外发。\n"
        f"【影响对象】{who}\n"
        f"【机制】未接入 AI 分析，正文机制未自动归纳；各评分维度由规则通道与政策字段派生。\n"
        f"【建议动作】由审核人员阅读政策原文后复核评分与建议动作。\n"
        f"【证据】主题标签：{themes}。\n"
        f"【置信度】低——仅规则通道结论。"
    )

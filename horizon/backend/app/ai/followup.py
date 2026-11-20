"""政策跟进 Agent：动态分析受影响客户、生成政策跟踪报告邮件。

设计原则与平台其它链路一致（05 §0.3 四道闸）：
- 系统接入真实 LLM（dashscope / ollama）时，由模型基于实时统计与政策字段生成结论；
- provider 为 mock、未配置密钥或调用失败时，退回「数据驱动归纳」：
  只使用统计结果与政策字段组织文字，不臆造数字，接口永远返回可用内容，
  避免前端出现「加载失败」。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.ai.guard import SchemaValidationError, repair_json, validate_schema
from app.ai.provider import LLMProvider, get_provider
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("ai.followup")

# mock provider 只会返回固定样例，无法反映当前政策，直接走数据驱动归纳
_NON_GENERATIVE_PROVIDERS = {"mock"}

BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["headline", "summary", "focus_points", "suggested_actions"],
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "focus_points": {"type": "array", "items": {"type": "string"}},
        "suggested_actions": {"type": "array", "items": {"type": "string"}},
    },
}

EMAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["subject", "body"],
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
}

_BRIEF_SYSTEM = """你是汇丰银行政策研究团队的「政策跟进智能体」。
任务：根据给定的政策信息与受影响客户统计数据，输出客户影响概况。
硬性要求：
1. 只能使用给定数据中出现的数字与事实，不得编造客户、金额、日期、文号；
2. 语言简洁、面向业务决策，避免空话；
3. headline 一句话结论（不超过 60 字）；
4. summary 2–4 句说明影响范围与集中度；
5. focus_points 3–5 条需要重点关注的客户/客群/业务线；
6. suggested_actions 3–5 条可执行的跟进动作，指明业务线或角色。
只输出 JSON 对象。"""

_EMAIL_SYSTEM = """你是汇丰银行政策研究团队的「政策跟进智能体」。
任务：根据给定的政策信息、受影响客户统计与使用者反馈，撰写一封可直接发送的政策跟踪报告邮件。
硬性要求：
1. 只能使用给定数据中出现的数字与事实，不得编造客户、金额、日期、文号、链接；
2. 邮件为中文商务邮件：开头称呼、分节小标题、结尾署名留「政策研究团队」；
3. 必须包含「受影响客户概况」一节，写明受影响客户户数、本行贷款合计、他行贷款合计、
   业务线分布、客群分布与单户敞口前列（全部使用给定 customer_stats / top_customers，不得编造）；
4. 分节顺序：政策概要 / 影响判断 / 受影响客户概况 / 使用者反馈 / 建议动作 / 原文出处；
5. 正文使用纯文本，不用 Markdown 表格与星号；
6. subject 不超过 60 字，格式为「【政策跟踪报告】政策标题」。
只输出 JSON 对象。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _provider() -> LLMProvider | None:
    try:
        return get_provider()
    except Exception as exc:  # 未配置密钥等：静默降级为数据驱动归纳
        log.warning("followup_provider_unavailable", error_type=type(exc).__name__)
        return None


def _ask(provider: LLMProvider | None, *, system: str, user: str, schema: dict,
         task: str) -> tuple[dict | None, str]:
    """调用模型并校验 Schema；失败返回 (None, "")，由调用方走数据驱动归纳。"""
    if provider is None:
        return None, ""
    if str(getattr(provider, "name", "")).lower() in _NON_GENERATIVE_PROVIDERS:
        return None, ""
    settings = get_settings()
    try:
        result = provider.complete(
            system=system,
            user=user,
            schema=schema,
            temperature=0.2,
            max_tokens=1600,
            model=settings.model_for_task("impact"),
            task=task,
        )
    except Exception as exc:
        log.warning("followup_llm_failed", task=task, error_type=type(exc).__name__)
        return None, ""

    parsed = result.parsed
    if parsed is None:
        parsed = repair_json(result.text or "")
    if not isinstance(parsed, dict):
        log.warning("followup_llm_unparsable", task=task)
        return None, ""
    try:
        validate_schema(parsed, schema)
    except SchemaValidationError as exc:
        log.warning("followup_llm_schema_fail", task=task, error=str(exc)[:160])
        return None, ""
    return parsed, result.model or str(getattr(provider, "name", ""))


_DIRECTION_LABELS = {"positive": "利好", "negative": "利空", "mixed": "利弊并存", "neutral": "中性"}


def _direction_label(policy: dict) -> str:
    direction = str(policy.get("direction") or "")
    return _DIRECTION_LABELS.get(direction, "中性")


def _line_text(stats: dict, limit: int = 4) -> str:
    items = stats.get("by_business_line") or []
    return "、".join(
        f"{item.get('business_line') or '未标注'} {item.get('customers', 0)} 户"
        f"（贷款 {item.get('loan_balance_cny_yi', 0)} 亿元）"
        for item in items[:limit]
    ) or "未标注业务线"


def _segment_text(stats: dict, limit: int = 4) -> str:
    items = stats.get("by_segment") or []
    return "、".join(
        f"{item.get('segment') or '未标注客群'} {item.get('customers', 0)} 户"
        for item in items[:limit]
    ) or "未标注客群"


def _top_text(stats: dict, limit: int = 3) -> str:
    items = stats.get("top_customers") or []
    return "；".join(
        f"{item.get('name_masked') or '客户'}（{item.get('business_line') or '—'}，"
        f"贷款 {item.get('loan_balance_cny_yi', 0)} 亿元）"
        for item in items[:limit]
    )


def _line_actions(stats: dict) -> list[str]:
    """按命中的业务线给出跟进动作（规则归纳，只覆盖客户库里的业务线代码）。"""
    codes = {str(item.get("business_line") or "") for item in stats.get("by_business_line") or []}
    actions: list[str] = []
    if "CIB" in codes:
        actions.append("CIB：逐户复核受影响对公客户的授信、跨境结算与贸易融资安排，评估条款变化对存量业务的影响。")
    if "WPB" in codes:
        actions.append("WPB：梳理受影响零售与理财客户的产品适配性与信息披露要求，准备客户沟通口径。")
    if "GTB" in codes:
        actions.append("GTB：复核跨境资金池与全球贸易融资安排，确认政策变动对通道与额度的影响。")
    if "Insurance" in codes:
        actions.append("保险业务：检查保险代销与再保险相关安排，确认是否需要调整产品结构。")
    if not actions:
        actions.append("由各业务线主管按受影响客户名单逐户复核，判断是否需要调整授信与产品安排。")
    if stats.get("overseas_customers"):
        actions.append(
            f"关注 {stats.get('overseas_customers')} 户涉及海外业务的客户，评估跨境条款联动的合规与操作影响。"
        )
    actions.append("以上客户数据为合成演示数据，业务决策前需以真实客户数据复核口径。")
    return actions


def _offline_brief(policy: dict, stats: dict, reports: dict) -> dict:
    total = int(stats.get("total_customers") or 0)
    loan = stats.get("loan_balance_total_cny_yi", 0)
    other = stats.get("other_bank_loans_total_cny_yi", 0)
    overseas = int(stats.get("overseas_customers") or 0)
    direction = _direction_label(policy)

    if total == 0:
        return {
            "headline": "客户库中未匹配到受影响客户",
            "summary": (
                "按当前政策标注的业务线，客户库中没有可匹配的客户记录。"
                "该结论仅代表合成客户数据集口径，不代表政策没有影响，建议核实政策适用主体与业务线标注。"
            ),
            "focus_points": ["政策适用主体与业务线标注是否完整", "是否需要按主题关键词重新匹配客户"],
            "suggested_actions": ["补充政策适用业务线后重新生成", "由业务主管人工确认受影响客户范围"],
        }

    headline = f"共 {total} 户客户受影响，本行贷款合计 {loan} 亿元，整体影响{direction}"
    summary = (
        f"按政策受影响业务线全量匹配，客户库共 {total} 户客户受影响：本行贷款合计 {loan} 亿元，"
        f"他行贷款合计 {other} 亿元，其中 {overseas} 户涉及海外业务。"
        f"客户集中在 {_line_text(stats)}；客群以 {_segment_text(stats)} 为主。"
        "该口径覆盖客户库全部客户，与发送影响报告的使用者是否名下有客户无关。"
    )
    focus_points = [
        f"业务线集中度：{_line_text(stats)}",
        f"客群分布：{_segment_text(stats)}",
        f"单户敞口前列：{_top_text(stats)}",
    ]
    if overseas:
        focus_points.append(f"海外业务客户 {overseas} 户，需关注跨境条款与合规联动。")
    if reports.get("count"):
        focus_points.append(
            f"政策使用者已提交 {reports.get('count')} 份影响报告"
            f"（待跟进 {reports.get('pending', 0)} 份），需结合反馈核对客户口径。"
        )
    return {
        "headline": headline,
        "summary": summary,
        "focus_points": focus_points,
        "suggested_actions": _line_actions(stats),
    }


def affected_customer_brief(policy: dict, stats: dict, reports: dict) -> dict:
    """受影响客户概况：优先模型生成，失败退回数据驱动归纳。"""
    fallback = _offline_brief(policy, stats, reports)
    provider = _provider()
    user = json.dumps(
        {
            "policy": policy,
            "customer_stats": {
                key: stats.get(key)
                for key in (
                    "total_customers", "loan_balance_total_cny_yi", "other_bank_loans_total_cny_yi",
                    "overseas_customers", "by_business_line", "by_segment", "match_rule",
                )
            },
            "top_customers": stats.get("top_customers") or [],
            "consumer_reports": reports,
        },
        ensure_ascii=False,
        indent=1,
    )
    parsed, model = _ask(provider, system=_BRIEF_SYSTEM, user=user, schema=BRIEF_SCHEMA, task="followup_brief")
    if parsed is None:
        return {
            **fallback,
            "generated_by": "rules",
            "model": "policy-followup-agent（离线归纳）",
            "generated_at": _now_iso(),
        }
    return {
        "headline": str(parsed.get("headline") or fallback["headline"]),
        "summary": str(parsed.get("summary") or fallback["summary"]),
        "focus_points": [str(item) for item in parsed.get("focus_points") or fallback["focus_points"]],
        "suggested_actions": [str(item) for item in parsed.get("suggested_actions") or fallback["suggested_actions"]],
        "generated_by": "ai_agent",
        "model": model or "llm",
        "generated_at": _now_iso(),
    }


def _customer_section_lines(stats: dict, *, top_limit: int = 5) -> list[str]:
    """受影响客户概况段落（邮件共用）：户数、金额、业务线/客群分布、单户敞口前列。"""
    total = int(stats.get("total_customers") or 0)
    if total == 0:
        return [
            "客户库中暂未匹配到受影响客户，建议核实政策适用主体与业务线标注。",
            f"统计口径：{stats.get('match_rule') or '按政策业务线匹配'}。",
        ]
    lines = [
        f"按客户库全量匹配，共 {total} 户客户受影响：本行贷款合计 "
        f"{stats.get('loan_balance_total_cny_yi', 0)} 亿元，他行贷款合计 "
        f"{stats.get('other_bank_loans_total_cny_yi', 0)} 亿元，含海外业务客户 "
        f"{stats.get('overseas_customers', 0)} 户。",
        f"业务线分布：{_line_text(stats, 6)}",
        f"客群分布：{_segment_text(stats, 6)}",
    ]
    top_customers = stats.get("top_customers") or []
    if top_customers:
        lines.append(f"单户敞口前列（前 {min(top_limit, len(top_customers))} 户）：")
        for index, item in enumerate(top_customers[:top_limit]):
            lines.append(
                f"  {index + 1}. {item.get('name_masked') or '客户'}"
                f"（{item.get('segment') or '—'}，{item.get('business_line') or '—'}，"
                f"贷款 {item.get('loan_balance_cny_yi', 0)} 亿元，他行贷款 "
                f"{item.get('other_bank_loans_cny_yi', 0)} 亿元）"
            )
    lines.append(
        f"统计口径：{stats.get('match_rule') or '按政策业务线匹配'}；"
        f"数据来源：{stats.get('source') or '合成客户数据集'}。"
    )
    return lines


def _ensure_customer_section(body: str, stats: dict) -> str:
    """模型生成的邮件若漏掉客户概况，追加一段确定性的数据统计。"""
    if "受影响客户概况" in body:
        return body
    block = "\n".join(["\n（附）受影响客户概况", *_customer_section_lines(stats)])
    return f"{body.rstrip()}\n{block}"


def _offline_email(policy: dict, stats: dict, reports: dict) -> dict:
    title = policy.get("title") or "政策"
    assessment_lines: list[str] = []
    chain = policy.get("transmission_chain") or []
    if chain:
        assessment_lines.append("传导路径：")
        assessment_lines.extend(f"  {index + 1}. {item}" for index, item in enumerate(chain))
    else:
        assessment_lines.append("传导路径：暂未生成传导路径。")
    affected = policy.get("affected") or {}
    lines = affected.get("business_lines") or stats.get("business_lines") or []

    body_lines = [
        "各位领导、同事：",
        "",
        f"现将「{title}」的政策跟踪情况汇报如下，供业务与合规决策参考。",
        "",
        "一、政策概要",
        f"政策编号：{policy.get('id') or '—'}",
        f"文　　号：{policy.get('doc_number') or '未标注'}",
        f"发文机构：{policy.get('issuing_body') or '未标注'}",
        f"辖　　区：{policy.get('jurisdiction') or '未标注'}",
        f"发布/生效：{policy.get('published_at') or '未标注'} / {policy.get('effective_at') or '未标注'}",
        f"优先级：{policy.get('priority') or '—'}（影响评分 {policy.get('score_total') or 0} 分）",
        f"影响方向：{_direction_label(policy)}",
        "",
        "二、影响判断",
        *assessment_lines,
        f"受影响业务线：{'、'.join(lines) if lines else '未标注'}",
    ]
    actions = policy.get("recommended_actions") or []
    body_lines.extend(["", "三、受影响客户概况", *_customer_section_lines(stats)])

    body_lines.extend(["", "四、使用者反馈"])
    if reports.get("count"):
        body_lines.append(
            f"政策使用者已提交 {reports.get('count')} 份影响报告，其中待跟进 {reports.get('pending', 0)} 份，"
            f"报告涉及客户 {reports.get('customers', 0)} 户。"
        )
    else:
        body_lines.append("暂未收到政策使用者反馈的影响报告。")

    body_lines.extend(["", "五、建议动作"])
    if actions:
        for index, item in enumerate(actions):
            if isinstance(item, str):
                text = item
            else:
                owner = item.get("owner") or ""
                deadline = item.get("deadline") or ""
                text = item.get("action") or ""
                if owner:
                    text += f"（负责人：{owner}）"
                if deadline:
                    text += f" 截止：{deadline}"
            body_lines.append(f"  {index + 1}. {text}")
    else:
        body_lines.extend(f"  {index + 1}. {text}" for index, text in enumerate(_line_actions(stats)))
    body_lines.extend(["", "六、原文出处", policy.get("url") or "暂无原文链接", "", "政策研究团队"])

    return {
        "subject": f"【政策跟踪报告】{title}",
        "body": "\n".join(body_lines),
        "generated_by": "rules",
        "model": "policy-followup-agent（离线归纳）",
        "generated_at": _now_iso(),
    }


def tracking_email(policy: dict, stats: dict, reports: dict) -> dict:
    """政策跟踪报告邮件：优先模型生成，失败退回数据驱动模板。"""
    fallback = _offline_email(policy, stats, reports)
    provider = _provider()
    user = json.dumps(
        {
            "policy": policy,
            "customer_stats": {
                key: stats.get(key)
                for key in (
                    "total_customers", "loan_balance_total_cny_yi", "other_bank_loans_total_cny_yi",
                    "overseas_customers", "by_business_line", "by_segment", "match_rule", "source",
                )
            },
            "top_customers": stats.get("top_customers") or [],
            "consumer_reports": reports,
        },
        ensure_ascii=False,
        indent=1,
    )
    parsed, model = _ask(provider, system=_EMAIL_SYSTEM, user=user, schema=EMAIL_SCHEMA, task="followup_email")
    if parsed is None:
        return fallback
    subject = str(parsed.get("subject") or fallback["subject"]).strip()
    body = str(parsed.get("body") or fallback["body"]).strip()
    return {
        "subject": subject,
        # 邮件必须包含受影响客户概况：模型漏写时用实时统计补齐
        "body": _ensure_customer_section(body, stats),
        "generated_by": "ai_agent",
        "model": model or "llm",
        "generated_at": _now_iso(),
    }

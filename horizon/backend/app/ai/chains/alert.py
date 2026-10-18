"""P5 预警草稿（plus 档）。输出 markdown，结构六段固定，≤350 字。"""
from __future__ import annotations

import json
import re

from app.ai.chains.base import BaseChain
from app.ai.guard import wrap_untrusted  # noqa: F401  提示词内已声明 untrusted 规则

REQUIRED_SECTIONS = ["【一句话结论】", "【影响对象】", "【机制】", "【建议动作】", "【证据】", "【置信度】"]
BANNED_WORDS = ["重大利好", "颠覆", "史上最严", "必将"]
AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:亿|万元|元|bps|bp)")


def validate_alert_md(text: str) -> list[str]:
    """返回违例列表：缺段 / 超长 / 夸张词 / 无估算标记的金额。"""
    errors: list[str] = []
    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"缺少段落 {section}")
    if len(text) > 350:
        errors.append(f"超长 {len(text)} 字")
    for word in BANNED_WORDS:
        if word in text:
            errors.append(f"出现夸张词 {word}")
    for m in AMOUNT_RE.finditer(text):
        window = text[max(0, m.start() - 10): m.end() + 10]
        if not any(marker in window for marker in ("估算", "区间", "约", "最高", "不超过")):
            errors.append(f"金额 {m.group(0)} 未标注估算/区间")
    return errors


class AlertChain(BaseChain):
    task = "alert"

    def run(self, *, policy_card: dict, assessment: dict) -> "ChainResult":  # noqa: ANN201
        result = super().run(
            variables={
                "policy_card": json.dumps(policy_card, ensure_ascii=False, indent=1),
                "assessment": json.dumps(assessment, ensure_ascii=False, indent=1),
            },
            content_text="",  # 预警不引用原文 span，证据段由 policy_card/assessment 携带
            schema=None,  # markdown 输出，不走 JSON Schema；结构校验见 validate_alert_md
        )
        errors = validate_alert_md(result.text)
        if errors:
            raise ValueError(f"alert 结构校验失败: {'; '.join(errors)}")
        return result

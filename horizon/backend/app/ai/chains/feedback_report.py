"""P9 反馈分析报告（审核员处理用户反馈，plus 档）。

输入：政策卡片 + 用户反馈 + 公司内部政策语料（合成演示数据，模拟数据2）。
输出：反馈归纳 + 内部政策比对分析 + 结论，见 FEEDBACK_REPORT_SCHEMA。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai.chains.base import BaseChain
from app.ai.guard import wrap_untrusted
from app.ai.schemas import FEEDBACK_REPORT_SCHEMA

INTERNAL_POLICY_DIR = Path(__file__).resolve().parents[3] / "seed" / "internal_policies"


def load_internal_policies() -> str:
    """加载公司内部政策语料（合成演示数据，模拟数据2）。"""
    if not INTERNAL_POLICY_DIR.exists():
        return "（未提供内部政策语料）"
    parts = []
    for path in sorted(INTERNAL_POLICY_DIR.glob("*.md")):
        parts.append(f"【{path.stem}】\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(parts)


class FeedbackReportChain(BaseChain):
    task = "feedback_report"

    def run(self, *, policy_card: dict, feedback: str):  # noqa: ANN201
        corpus = load_internal_policies()
        result = super().run(
            variables={
                "policy_card": json.dumps(policy_card, ensure_ascii=False, indent=1),
                "feedback": wrap_untrusted(feedback),
                "internal_policy_corpus": corpus,
            },
            content_text=corpus,  # 内部政策分析引用的 quote 以语料为定位基准
            schema=FEEDBACK_REPORT_SCHEMA,
            temperature=0.2,
        )
        return result

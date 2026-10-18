"""P6 政策 2.0 建议书生成（05 P6，max 档 + 强约束）。"""
from __future__ import annotations

import re

from app.ai.chains.base import BaseChain
from app.ai.evidence import locate_quote
from app.ai.guard import wrap_untrusted
from app.ai.schemas import STUDIO_SCHEMA

BANNED_PREDICTIONS = ["中国政府将", "香港将立法", "必将出台", "一定会", "监管将批准"]
BREAKTHROUGH_WORDS = ["取消", "豁免", "突破", "突破现行"]


def validate_proposal(parsed: dict, corpus_text: str) -> list[str]:
    """生成后自检（05 P6 §生成后自检）：返回违例列表，空 = 通过。"""
    errors: list[str] = []
    proposals = parsed.get("proposals") or []
    if not 5 <= len(proposals) <= 8:
        errors.append(f"建议数量 {len(proposals)} 不在 5–8 条范围")
    themes = {p.get("theme") for p in proposals}
    if len(themes) < 3:
        errors.append(f"覆盖主题 {len(themes)} 个，少于 3 个")

    for p in proposals:
        pid = p.get("id", "?")
        bases = p.get("current_basis") or []
        if not bases:
            errors.append(f"{pid}: current_basis 为空")
        for b in bases:
            if locate_quote(corpus_text, b.get("quote", "")) is None:
                errors.append(f"{pid}: 依据 quote 无法在语料中定位")
        if not p.get("kpis"):
            errors.append(f"{pid}: 缺少可衡量 KPI")
        draft = p.get("draft_clause", "")
        if any(w in draft for w in BREAKTHROUGH_WORDS):
            bc = [c for c in parsed.get("boundary_check", []) if c.get("proposal_id") == pid]
            if not bc or bc[0].get("status") == "pass":
                errors.append(f"{pid}: 涉及取消/豁免/突破现行限制，boundary_check 必须为 warn/fail")

    full_text = str(parsed)
    for word in BANNED_PREDICTIONS:
        if word in full_text:
            errors.append(f"出现断言式预测: {word}")
    return errors


class StudioChain(BaseChain):
    task = "studio"

    def run(self, *, theme: str, corpus_text: str):  # noqa: ANN201
        result = super().run(
            variables={"theme": theme, "corpus": wrap_untrusted(corpus_text[:12000])},
            content_text=corpus_text,
            schema=STUDIO_SCHEMA,
            temperature=0.2,
        )
        errors = validate_proposal(result.parsed, corpus_text)
        if errors:
            raise ValueError(f"政策 2.0 自检失败: {'; '.join(errors[:5])}")
        return result

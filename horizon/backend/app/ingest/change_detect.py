"""变更检测（06 §5.4）：hash 变化 → document_version + 段落级 diff + changed_ratio 分级。"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

SUBSTANTIAL_THRESHOLD = 0.3  # >0.3 实质修订需重跑分析；其余 minor_edit


@dataclass
class DiffResult:
    changed: bool
    changed_ratio: float
    minor_edit: bool
    diff: list[dict] = field(default_factory=list)  # [{op: equal/insert/delete/replace, before, after}]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{1,}|(?<=。)|(?<=；)", text or "") if p.strip()]


def compute_diff(old_text: str, new_text: str) -> DiffResult:
    """段落级 diff。changed_ratio = 变化段落数 / max(旧段落数, 新段落数)。"""
    old_p, new_p = _paragraphs(old_text), _paragraphs(new_text)
    if old_p == new_p:
        return DiffResult(changed=False, changed_ratio=0.0, minor_edit=False)

    diff: list[dict] = []
    changed_units = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_p, new_p).get_opcodes():
        if tag == "equal":
            continue
        changed_units += max(i2 - i1, j2 - j1)
        diff.append({
            "op": tag,
            "before": "\n".join(old_p[i1:i2]),
            "after": "\n".join(new_p[j1:j2]),
        })
    ratio = changed_units / max(len(old_p), len(new_p), 1)
    return DiffResult(
        changed=True,
        changed_ratio=round(ratio, 4),
        minor_edit=ratio <= SUBSTANTIAL_THRESHOLD,
        diff=diff,
    )

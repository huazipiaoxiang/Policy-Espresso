"""汇丰业务图谱（03 §3.4 search 层索引的第三类集合；MVP 先用规则切片）。

seed/business_map.json：业务线 × 政策主题敏感度 + 客群 + 产品。
影响分析（P4）输入切片 = 与政策主题相关的业务线及其敏感度。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "business_map.json"


@dataclass
class BusinessLine:
    code: str
    name: str
    themes_sensitivity: dict[str, int]
    segments: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)


def load_business_map() -> list[BusinessLine]:
    if not SEED_PATH.exists():
        return []
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return [BusinessLine(**row) for row in rows]


def slice_for_themes(themes: list[str], *, min_sensitivity: int = 3) -> dict:
    """按政策主题取业务线切片：命中主题且敏感度 ≥ min_sensitivity 的业务线。"""
    out = []
    for line in load_business_map():
        hits = {t: s for t, s in line.themes_sensitivity.items() if t in themes and s >= min_sensitivity}
        if hits:
            out.append({
                "code": line.code, "name": line.name,
                "sensitive_themes": hits, "segments": line.segments, "products": line.products,
            })
    return {"business_lines": out, "matched_themes": [t for t in themes if any(t in o["sensitive_themes"] for o in out)]}

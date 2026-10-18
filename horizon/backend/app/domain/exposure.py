"""客户暴露聚合（合成数据，04 §7：不使用真实客户数据）。

输入：政策主题 + 客群线索；输出：金额区间 + 计算口径 basis + 置信度。
区间取总余额的 0.6–1.2 倍，basis 必须写明"合成数据集口径"。
"""
from __future__ import annotations

import json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[3] / "seed" / "synthetic_customers.json"


def load_customers() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def aggregate_exposure(themes: list[str], segment_hints: list[str]) -> dict | None:
    """按主题（贷款/贴息类）与客群线索聚合合成客户贷款余额。

    优先用 subsidy_eligible 标记户（贴息类政策口径，见 09 §1.2）；
    无标记户时退回按客群线索（含"制造业/中小微"）匹配。
    无匹配客户 → None（调用方把 exposure 置 null 并注明缺数据）。
    """
    if "贷款与贴息" not in themes:
        return None
    customers = load_customers()
    matched = [c for c in customers if c.get("subsidy_eligible")]
    if not matched:
        matched = [
            c for c in customers
            if any(h in c.get("segment", "") for h in list(segment_hints) + ["制造业", "中小微"])
        ]
    if not matched:
        return None
    total = round(sum(float(c.get("loan_balance_cny_yi", 0)) for c in matched), 1)
    return {
        "low": round(total * 0.6, 1),
        "high": round(total * 1.2, 1),
        "currency": "CNY",
        "unit": "亿",
        "basis": f"合成数据集口径：{len(matched)} 户符合贴息条件客群的贷款余额合计 {total} 亿元，区间取 0.6–1.2 倍",
        "confidence": 0.5,
    }

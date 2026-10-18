"""影响评分卡（02 §5.2）。纯函数，不依赖 LLM/FastAPI，可单测。

8 维 0–5 分，direction 不参与加权。综合分 0–100 → 优先级 P0/P1/P2/P3。
缺证据的维度必须置 None（由 ai 层强制），此处按 0 计入并在结果中标注缺失。
"""
from __future__ import annotations

from dataclasses import dataclass, field

DIMENSIONS = [
    "relevance",
    "exposure",
    "urgency",
    "certainty",
    "actionability",
    "differential",
    "compliance",
]

WEIGHTS: dict[str, float] = {
    "relevance": 0.25,
    "exposure": 0.20,
    "urgency": 0.15,
    "certainty": 0.10,
    "actionability": 0.10,
    "differential": 0.15,
    "compliance": 0.05,
}

DIRECTIONS = {"positive", "negative", "mixed", "neutral"}

PRIORITY_THRESHOLDS = [("P0", 80.0), ("P1", 60.0), ("P2", 40.0), ("P3", 0.0)]


@dataclass
class ScoreResult:
    score_total: float  # 0–100
    priority: str  # P0–P3
    missing_dimensions: list[str] = field(default_factory=list)


class ScoreValidationError(ValueError):
    pass


def compute_score(scores: dict[str, int | None], direction: str = "neutral") -> ScoreResult:
    """按权重加权 8 维分数。

    输入：scores 各维 0–5 或 None（缺证据）；direction 取值 DIRECTIONS（不加权，仅校验）。
    输出：0–100 综合分与优先级。None 维按 0 计，并列入 missing_dimensions。
    失败模式：维度名/分值非法、direction 非法 → ScoreValidationError。
    """
    if direction not in DIRECTIONS:
        raise ScoreValidationError(f"非法 direction: {direction}")
    unknown = set(scores) - set(DIMENSIONS)
    if unknown:
        raise ScoreValidationError(f"未知评分维度: {sorted(unknown)}")

    total = 0.0
    missing: list[str] = []
    for dim, weight in WEIGHTS.items():
        value = scores.get(dim)
        if value is None:
            missing.append(dim)
            continue
        if not isinstance(value, int) or not 0 <= value <= 5:
            raise ScoreValidationError(f"{dim} 分值须为 0–5 整数，得到 {value!r}")
        total += (value / 5.0) * weight * 100.0

    total = round(total, 1)
    priority = next(level for level, threshold in PRIORITY_THRESHOLDS if total >= threshold)
    return ScoreResult(score_total=total, priority=priority, missing_dimensions=missing)

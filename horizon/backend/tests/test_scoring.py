import pytest

from app.domain.scoring import ScoreValidationError, compute_score

FULL = {
    "relevance": 5,
    "exposure": 4,
    "urgency": 5,
    "certainty": 5,
    "actionability": 4,
    "differential": 5,
    "compliance": 2,
}


def test_full_score_matches_weights():
    # 按 02 §5.2 权重表：Σ(score/5 × weight) × 100 = 91.0 → P0
    # 注：04 文档 JSON 示例写 86.5，与权重表不符，以权重表为准（见 docs/DECISIONS.md）
    result = compute_score(FULL, direction="negative")
    assert result.score_total == pytest.approx(91.0)
    assert result.priority == "P0"
    assert result.missing_dimensions == []


def test_missing_dimensions_counted_and_zeroed():
    result = compute_score({"relevance": 5}, direction="neutral")
    assert result.score_total == pytest.approx(25.0)
    assert result.priority == "P3"
    assert set(result.missing_dimensions) == {
        "exposure", "urgency", "certainty", "actionability", "differential", "compliance"
    }


def test_priority_boundaries():
    base = {d: 0 for d in FULL}
    assert compute_score(base).priority == "P3"
    assert compute_score({d: 4 for d in FULL}).priority == "P0"  # 80.0
    assert compute_score({d: 3 for d in FULL}).priority == "P1"  # 60.0


def test_invalid_inputs():
    with pytest.raises(ScoreValidationError):
        compute_score({"relevance": 6})
    with pytest.raises(ScoreValidationError):
        compute_score({"unknown_dim": 1})
    with pytest.raises(ScoreValidationError):
        compute_score(FULL, direction="sideways")

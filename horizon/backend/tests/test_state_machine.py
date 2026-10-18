import pytest

from app.domain import state_machine as sm


def test_happy_path():
    cur = "draft"
    for target in ["ai_checked", "pending_review", "in_review", "approved", "published"]:
        cur = sm.transition(cur, target)
    assert cur == "published"


def test_illegal_transition_raises():
    with pytest.raises(sm.InvalidTransitionError):
        sm.transition("draft", "published")
    with pytest.raises(sm.InvalidTransitionError):
        sm.transition("archived", "draft")


def test_rejected_reopen_requires_reason():
    with pytest.raises(sm.InvalidTransitionError):
        sm.transition("rejected", "draft")
    assert sm.transition("rejected", "draft", reason="补证据后重开") == "draft"


def test_double_sign_rule():
    assert sm.required_review_levels("P0") == 2
    assert sm.required_review_levels("P1") == 2
    assert sm.required_review_levels("P2") == 1
    assert sm.required_review_levels("P3") == 1


def test_dispatch_gate():
    assert not sm.can_dispatch("approved")  # approved 后须先 published
    assert sm.can_dispatch("published")
    assert not sm.can_dispatch("in_review")

"""N02: one level policy.  Pure functions, no database."""
import re
from types import SimpleNamespace as NS

import pytest

from src.domain import level_policy as lp
from src.domain.alpha_engine import theta_to_level

GRID = [round(-4.0 + i * 0.01, 2) for i in range(801)]
BOUNDARIES = [-1.4, -0.5, 0.1, 1.0]


@pytest.mark.parametrize("theta,category,status", [
    (-3.0, "below_grade", "critical"),
    (-1.4001, "below_grade", "critical"),
    (-1.4, "below_grade", "below"),
    (-0.5001, "below_grade", "below"),
    (-0.5, "at_grade", "partial_gap"),
    (0.0999, "at_grade", "partial_gap"),
    (0.1, "at_grade", "on_level"),
    (0.9999, "at_grade", "on_level"),
    (1.0, "above_grade", "above"),
    (3.5, "above_grade", "above"),
])
def test_cut_offs_and_status_refine_category(theta, category, status):
    result = lp.classify(theta, 0.2, 9)
    assert result["category"] == category and result["status"] == status
    assert lp.CATEGORY_OF_STATUS[status] == category


def test_category_agrees_with_cat_theta_to_level_on_the_whole_grid():
    for theta in GRID:
        assert lp.classify(theta, 0.3, 8)["category"] == theta_to_level(theta), theta
        # the 5-step status never contradicts the 3-step CAT category
        assert lp.CATEGORY_OF_STATUS[lp.classify(theta, 0.3, 8)["status"]] == theta_to_level(theta)


def test_no_class_equivalent_is_computed_or_stored():
    """N03a (O4): "beginning/middle/end of grade N" has no norming behind it."""
    assert not hasattr(lp, "class_equivalent")
    for theta in GRID[::25]:
        for grade in (5, 8, 11):
            level = lp.classify(theta, 0.3, grade)
            assert "class_equivalent" not in level
            assert not re.search(r"(начал|середин|конец|конц)", str(level))
    # the level band itself is untouched and does not depend on the declared grade
    for theta in (-2.5, -0.7, 0.3, 1.2):
        assert lp.classify(theta, 0.3, 6) == lp.classify(theta, 0.3, 10)


def test_provisional_flag():
    assert lp.classify(0.2, 0.40, 9)["provisional"] is False
    assert lp.classify(0.2, 0.4001, 9)["provisional"] is True
    assert lp.classify(0.2, None, 9)["provisional"] is True


def test_no_theta_concludes_nothing():
    result = lp.classify(None, 0.2, 9)
    assert result["category"] is result["status"] is None
    assert result["provisional"] is True


def test_percent_correct_cannot_change_the_level():
    # The old report said "critical" for theta=+0.48 because only 20% were right.
    level = lp.build_level(0.48, 0.25, 8, solved=2, total=10)
    assert level["status"] == "on_level" and level["category"] == "at_grade"
    assert (level["solved"], level["total"]) == (2, 10)
    assert set(level) == {"category", "status", "provisional",
                          "theta", "se", "solved", "total"}


@pytest.mark.parametrize("outcome,expected", [
    (1, True), (1.0, True), ("1.0", True), (0.5, False), (0, False), (0.0, False),
    (None, False), ("x", False),
])
def test_is_correct_single_rule_legacy_half_is_not_correct(outcome, expected):
    assert lp.is_correct(outcome) is expected


def test_count_solved_counts_cat_items_only():
    answers = [NS(outcome=1, is_deep_scan=False), NS(outcome=0, is_deep_scan=False),
               NS(outcome=0.5, is_deep_scan=False), NS(outcome=1, is_deep_scan=True)]
    assert lp.count_solved(answers) == {"solved": 1, "total": 3}
    assert lp.count_solved(answers, include_deep_scan=True) == {"solved": 2, "total": 4}


def test_legacy_status_codes_match_the_front_end_vocabulary():
    from src.domain.report_generator import VALID_STATUS
    assert set(lp.LEGACY_STATUS.values()) == VALID_STATUS

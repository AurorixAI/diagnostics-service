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


@pytest.mark.parametrize("grade", range(5, 12))
def test_class_equivalent_is_monotonic_in_theta_and_capped(grade):
    parts = {"начало": 0, "середина": 1, "конец": 2}
    previous = -1
    for theta in GRID:
        text = lp.classify(theta, 0.3, grade)["class_equivalent"]
        part, number = re.fullmatch(r"(начало|середина|конец) (\d+) класса", text).groups()
        assert 5 <= int(number) <= 11
        ordinal = int(number) * 3 + parts[part]
        assert ordinal >= previous, (theta, text)
        previous = ordinal


def test_class_equivalent_depends_only_on_theta_and_grade_not_on_se():
    for theta in (-2.5, -0.7, 0.3, 1.2):
        assert (lp.classify(theta, 0.1, 9)["class_equivalent"]
                == lp.classify(theta, 0.9, 9)["class_equivalent"]
                == lp.classify(theta, None, 9)["class_equivalent"])


def test_class_equivalent_examples_documented_in_the_module():
    assert lp.class_equivalent(0.48, 8) == "начало 8 класса"       # stage session 2ab4c0de
    assert lp.class_equivalent(0.7, 8) == "середина 8 класса"
    assert lp.class_equivalent(-1.5, 9) == "начало 7 класса"
    assert lp.class_equivalent(-0.1, 9) == "конец 8 класса"
    assert lp.class_equivalent(3.0, 11) == "конец 11 класса"
    assert lp.class_equivalent(-3.0, 5) == "начало 5 класса"


def test_provisional_flag():
    assert lp.classify(0.2, 0.40, 9)["provisional"] is False
    assert lp.classify(0.2, 0.4001, 9)["provisional"] is True
    assert lp.classify(0.2, None, 9)["provisional"] is True


def test_no_theta_concludes_nothing():
    result = lp.classify(None, 0.2, 9)
    assert result["category"] is result["status"] is result["class_equivalent"] is None
    assert result["provisional"] is True


def test_percent_correct_cannot_change_the_level():
    # The old report said "critical" for theta=+0.48 because only 20% were right.
    level = lp.build_level(0.48, 0.25, 8, solved=2, total=10)
    assert level["status"] == "on_level" and level["category"] == "at_grade"
    assert (level["solved"], level["total"]) == (2, 10)
    assert set(level) == {"category", "status", "class_equivalent", "provisional",
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

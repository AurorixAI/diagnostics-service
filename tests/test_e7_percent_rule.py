"""Wave E7 / decision 7: ONE percent rule - a whole number, half up - for the report cards, the achievements and the line of the AI prompt;
the analytics API keeps one decimal, derived from the same mastery fraction."""
import pathlib
import re
from types import SimpleNamespace as NS

import pytest

from src.domain import level_policy as lp
from src.domain.report_generator import _build_achievements, _build_skill_blocks

# alpha -> (0.5 + alpha / 4) * 100 = raw -> whole percent, half up
TABLE = [(-3.0, 0), (-2.0, 0), (-1.5, 13), (-0.5, 38), (0.0, 50), (0.01, 50), (0.02, 51), (0.2, 55), (0.30, 58), (0.33, 58), (1.0, 75), (1.998, 100), (2.0, 100), (3.0, 100)]


@pytest.mark.parametrize("alpha, percent", TABLE)
def test_topic_mastery_percent_is_a_whole_number_half_up(alpha, percent):
    assert lp.topic_mastery_percent(alpha) == percent


def test_the_fraction_is_clipped_and_the_percent_is_the_fraction_rounded():
    assert lp.topic_mastery_fraction(0.30) == pytest.approx(0.575)
    assert (lp.topic_mastery_fraction(-9.0), lp.topic_mastery_fraction(9.0)) == (0.0, 1.0)
    for alpha in (-2.5, -1.3, -0.07, 0.4, 0.77, 1.9):
        assert lp.topic_mastery_percent(alpha) == lp.round_percent(lp.topic_mastery_fraction(alpha) * 100)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_broken_alpha_is_the_middle_not_a_full_bar(bad):
    assert lp.topic_mastery_fraction(bad) == 0.5 and lp.topic_mastery_percent(bad) == 50


@pytest.mark.parametrize("value, expected", [(0.0, 0), (12.5, 13), (62.5, 63), (62.4999, 62), (57.49999999999999, 58), (57.4999, 57), (99.5, 100), (100.0, 100), (-3.0, 0), (130.0, 100)])
def test_round_percent_half_up(value, expected):
    assert lp.round_percent(value) == expected


def test_the_achievements_show_the_same_number():
    answers = [NS(topic_id="G9_T1", outcome=1.0, skill_id="x", is_deep_scan=False)]
    for alpha, percent in TABLE:
        out = _build_achievements({"G9_T1": {"alpha": alpha}}, {"G9_T1": {"name_ru": "Дроби"}}, answers)
        assert out[0]["mastery_percent"] == percent, alpha


def test_the_topic_cards_show_the_same_number():
    names = {"G9_T1": {"name_ru": "Дроби"}}
    answers = [NS(topic_id="G9_T1", outcome=1.0, skill_id="x", is_deep_scan=False)] * 3
    strong, _weak, _critical = _build_skill_blocks({"G9_T1": {"alpha": 1.0, "observations": 3}}, [], names, answers, l2_of=lambda sid: sid)
    assert strong[0]["mastery_percent"] == 75
    # 0.30 is 57.5 raw: the card (strong from 70) must not be below its own number
    _, weak, _ = _build_skill_blocks({"G9_T1": {"alpha": 0.30, "observations": 2}}, [], names,
                                     [NS(topic_id="G9_T1", outcome=1.0, skill_id="x", is_deep_scan=False),
                                      NS(topic_id="G9_T1", outcome=0.0, skill_id="x", is_deep_scan=False)], l2_of=lambda sid: sid)
    assert weak[0]["mastery_percent"] == 58


def test_no_inline_copy_of_the_formula_is_left():
    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders = [str(path.relative_to(src)) for path in src.rglob("*.py")
                 if path.name != "level_policy.py" and re.search(r"alpha\s*/\s*4(\.0)?\s*\)", path.read_text(encoding="utf-8"))]
    assert offenders == []
    assert "int(round(correct / total * 100))" not in (src / "domain" / "report_generator.py").read_text(encoding="utf-8")


def test_the_score_percent_of_the_report_is_half_up_too():
    assert round(5 / 8 * 100) == 62                     # Python's round() goes to the even number: 62.5 -> 62
    assert lp.round_percent(5 / 8 * 100) == 63 and lp.round_percent(1 / 8 * 100) == 13

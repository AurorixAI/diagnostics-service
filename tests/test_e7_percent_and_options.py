"""Wave E7, pinned BEFORE the code changes (commit of tests only): what the report shows for a topic mastery (DU-04) and which field of an
answer option each place reads (DU-05). The code commits of the wave change the lines marked ``# today``."""
from types import SimpleNamespace as NS

import pytest

from src.domain import task_display
from src.domain.report_generator import _build_achievements, _option_value


def achieved(alpha):
    answers = [NS(topic_id="G9_T1", outcome=1.0, skill_id="x", is_deep_scan=False)]
    out = _build_achievements({"G9_T1": {"alpha": alpha}}, {"G9_T1": {"name_ru": "Дроби"}}, answers)
    return out[0]["mastery_percent"]


# alpha -> (0.5 + alpha / 4) * 100: 57.5 for 0.30
@pytest.mark.parametrize("alpha, shown_today", [
    (-3.0, 0), (-2.0, 0), (-1.5, 12), (-0.5, 37), (0.0, 50), (0.01, 50), (0.02, 50), (0.2, 55),
    (0.30, 57), (0.33, 58), (1.0, 75), (2.0, 100), (3.0, 100),
])
def test_the_report_truncates_the_percent_today(alpha, shown_today):
    assert achieved(alpha) == shown_today              # today: int() truncation - 0.02 shows 50 (50.5), 0.30 shows 57 (57.5)


def test_an_option_with_text_and_value_is_read_in_two_orders_today():
    option = {"text": "x > 0", "value": "x>0"}
    assert task_display._extract_option_text(option) == "x > 0"      # the screen and the grader: text first
    assert _option_value(option) == "x>0"                            # today: the report looks at `value` first (DU-05)


def test_a_numeric_zero_option_is_lost_by_the_report_chain_today():
    assert task_display._extract_option_text({"value": 0}) == "0"
    assert _option_value({"value": 0}) == ""                         # today: the `or` chain drops 0 (DU-05)

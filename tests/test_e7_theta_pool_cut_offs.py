"""Wave E7 / DU-03: no bare theta literal is left in the CAT code. The two cut-offs of the task POOL (previous grade below -0.5, two grades back below
-1.5) are named in level_policy; -1.5 is deliberately not the 'critical' cut-off (-1.4): it decides which tasks to serve, not what the student is called."""
import json
import pathlib
import re

import pytest

from src.domain import level_policy as lp

GOLDEN = json.loads((pathlib.Path(__file__).parent / "fixtures" / "level_thresholds_golden.json").read_text(encoding="utf-8"))["not_level_thresholds"]


def test_the_pool_cut_offs_are_the_golden_ones_and_the_second_is_not_the_critical_one():
    assert lp.POOL_PREVIOUS_GRADE_THETA == GOLDEN["pool_previous_grade_below"] == lp.THETA_AT
    assert lp.POOL_TWO_GRADES_BACK_THETA == GOLDEN["pool_two_grades_back_below"]
    assert lp.POOL_TWO_GRADES_BACK_THETA != lp.THETA_CRITICAL


@pytest.mark.parametrize("theta, grade, floor", [
    (0.3, 9, None), (-0.5, 9, None), (-0.5001, 9, 8), (-1.0, 9, 8), (-1.4001, 9, 8), (-1.5, 9, 8), (-1.5001, 9, 7), (-3.0, 9, 7),
    (-3.0, 6, 5), (-3.0, 5, 5), (-0.6, 5, 5), (-0.6, 6, 5),
])
def test_the_lowest_grade_of_the_pool(theta, grade, floor):
    assert lp.lower_grade_floor(theta, grade) == floor


def test_the_cat_code_has_no_bare_level_theta_literal():
    domain = pathlib.Path(__file__).resolve().parents[1] / "src" / "domain"
    for name in ("session_service.py", "alpha_engine.py"):
        text = (domain / name).read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in text.splitlines())
        for literal in (r"theta_val\s*<\s*-\s*[0-9]", r'"below_grade":\s*\(-4\.0,\s*-0\.5\)', r'"at_grade":\s*\(-0\.5,\s*1\.0\)', r'"above_grade":\s*\(1\.0,\s*4\.0\)'):
            assert re.search(literal, code) is None, (name, literal)

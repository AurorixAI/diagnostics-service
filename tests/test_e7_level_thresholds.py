"""Wave E7 / DU-03: the theta cut-offs in one table (``fixtures/level_thresholds_golden.json`` - the same data auth-service and the front read)."""
import json
import pathlib

import pytest

from src.domain import level_policy as lp
from src.domain.alpha_engine import ThetaState, _THETA_GRID, level_confidence, theta_to_level

GOLDEN = json.loads((pathlib.Path(__file__).parent / "fixtures" / "level_thresholds_golden.json").read_text(encoding="utf-8"))


def test_the_constants_are_the_ones_of_the_table():
    t = GOLDEN["thresholds"]
    assert (lp.THETA_ABOVE, lp.THETA_AT, lp.THETA_ON_LEVEL, lp.THETA_CRITICAL, lp.PROVISIONAL_SE) == \
        (t["above"], t["at"], t["on_level"], t["critical"], t["provisional_se"])


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=[str(c["theta"]) for c in GOLDEN["cases"]])
def test_category_and_status_of_every_case(case):
    assert lp.theta_category(case["theta"]) == theta_to_level(case["theta"]) == case["category"]
    assert lp.theta_status(case["theta"]) == case["status"]
    assert lp.classify(case["theta"], 0.2, 9) == {"category": case["category"], "status": case["status"], "provisional": False}


@pytest.mark.parametrize("case", GOLDEN["provisional"], ids=[str(c["se"]) for c in GOLDEN["provisional"]])
def test_provisional_cut_off(case):
    assert lp.classify(0.2, case["se"], 9)["provisional"] is case["provisional"]


def test_the_confidence_of_the_level_splits_the_cell_at_the_category_cut_offs():
    """``level_confidence`` counts the posterior mass inside the band of the estimated category; the boundary cell is cut exactly at -0.5 / 1.0."""
    step = float(_THETA_GRID[1] - _THETA_GRID[0])
    k = int(((-0.5) - (-4.0)) // step)                       # the cell that contains -0.5
    lo, hi = _THETA_GRID[k] - step / 2, _THETA_GRID[k] + step / 2
    assert lo < lp.THETA_AT < hi
    posterior = [0.0] * len(_THETA_GRID)
    posterior[k] = 1.0
    above_part = (hi - lp.THETA_AT) / step                    # the part of the cell at or above -0.5
    assert level_confidence(ThetaState(theta=-0.45, se=0.3, posterior=posterior)) == pytest.approx(above_part)       # at_grade
    assert level_confidence(ThetaState(theta=-0.55, se=0.3, posterior=posterior)) == pytest.approx(1 - above_part)   # below_grade
    j = int((1.0 - (-4.0)) // step)
    lo, hi = _THETA_GRID[j] - step / 2, _THETA_GRID[j] + step / 2
    assert lo < lp.THETA_ABOVE < hi
    posterior = [0.0] * len(_THETA_GRID)
    posterior[j] = 1.0
    assert level_confidence(ThetaState(theta=1.05, se=0.3, posterior=posterior)) == pytest.approx((hi - lp.THETA_ABOVE) / step)

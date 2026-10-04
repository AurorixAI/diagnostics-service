import itertools
import math

from src.domain.alpha_engine import IRTParams, _p3pl, fisher_information


def test_information_matches_response_probability_derivative():
    """Independent finite-difference definition covers guessing and difficulties."""
    for theta, a, b, c in itertools.product([-2., 0., 2.], [.5, 1., 2.], [-1., 1.], [0., .2]):
        params = IRTParams(a=a, b=b, c=c)
        p = _p3pl(theta, a, b, c)
        h = 1e-5
        derivative = (_p3pl(theta+h, a, b, c)-_p3pl(theta-h, a, b, c))/(2*h)
        expected = derivative**2/(p*(1-p))
        assert math.isclose(fisher_information(theta, params), expected, rel_tol=1e-7)


def test_2pl_information_peaks_at_matched_difficulty():
    params = IRTParams(a=1., b=0., c=0.)
    assert fisher_information(0., params) == .25
    assert fisher_information(-2., params) < .25
    assert fisher_information(2., params) < .25
    assert math.isclose(fisher_information(-2., params), fisher_information(2., params))

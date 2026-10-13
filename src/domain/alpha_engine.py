"""
Diagnostic Service — Alpha Engine (IRT 3PL)

IRT 3PL model:
  P(θ) = c + (1 − c) / (1 + exp(−a·(θ − b)))

Outcome scale (binary):
  1.0 → correct answer
  0.0 → wrong / distractor / idk

Distractor answers are scored as 0.0 (wrong) — the diagnostic value
(which misconception was triggered) is stored in eval_category field,
not in the IRT outcome.

Likelihood:
  correct → L = P(θ)
  wrong   → L = 1 − P(θ)

EAP theta estimation:
  61-point uniform grid over [−4, 4] with Gaussian prior.
  Posterior updated multiplicatively after each response.

AlphaTracker:
  Tracks per-topic mastery (alpha) independently of global theta.
  Uses additive update with K = 0.4 learning rate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

# ── Quadrature grid ────────────────────────────────────────────────────────
_THETA_GRID: np.ndarray = np.linspace(-4.0, 4.0, 61)
_PRIOR: np.ndarray = np.exp(-0.5 * _THETA_GRID ** 2) / math.sqrt(2 * math.pi)
_PRIOR = _PRIOR / _PRIOR.sum()  # normalize to sum = 1


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class IRTParams:
    """3PL IRT parameters for a single task."""
    a: float = 1.0   # discrimination
    b: float = 0.0   # difficulty
    c: float = 0.0   # guessing (pseudo-chance)


@dataclass
class ThetaState:
    """Current EAP ability estimate."""
    theta: float = 0.0
    se: float = 1.0
    posterior: List[float] = field(
        default_factory=lambda: list(_PRIOR.tolist())
    )


# ── Core IRT functions ─────────────────────────────────────────────────────

def _p3pl(theta: float, a: float, b: float, c: float) -> float:
    """3PL probability of a correct response at ability theta."""
    return c + (1.0 - c) / (1.0 + math.exp(-a * (theta - b)))


def p_correct(theta: float, params: IRTParams) -> float:
    """Model probability of a correct answer to an item with ``params`` at ability ``theta``."""
    return _p3pl(theta, params.a, params.b, params.c)


def _likelihood(outcome: float, p: float) -> float:
    """
    Response likelihood for 3PL (binary scoring).
      1.0 → correct  → L = P(θ)
      0.0 → wrong    → L = 1 − P(θ)
    Distractors are scored as 0.0 (wrong); their diagnostic value
    is captured in eval_category, not in the IRT outcome.
    """
    if outcome == 1.0:
        return p
    return 1.0 - p


def update_theta(state: ThetaState, params: IRTParams, outcome: float) -> ThetaState:
    """
    Bayesian EAP update after one response.
    Returns a new ThetaState (immutable).
    """
    posterior = np.array(state.posterior, dtype=float)

    for i, theta_pt in enumerate(_THETA_GRID):
        p = _p3pl(float(theta_pt), params.a, params.b, params.c)
        posterior[i] *= _likelihood(outcome, p)

    total = posterior.sum()
    if total < 1e-300:
        posterior = _PRIOR.copy()
    else:
        posterior /= total

    # EAP point estimate
    new_theta = float(np.dot(_THETA_GRID, posterior))

    # Standard Error = sqrt(Var[θ|data])
    e_theta2 = float(np.dot(_THETA_GRID ** 2, posterior))
    variance = max(0.0, e_theta2 - new_theta ** 2)
    new_se = math.sqrt(variance)

    return ThetaState(
        theta=round(new_theta, 4),
        se=round(new_se, 4),
        posterior=posterior.tolist(),
    )


def fisher_information(theta: float, params: IRTParams) -> float:
    """Fisher Information I(θ) — higher = more informative task at this ability."""
    p = _p3pl(theta, params.a, params.b, params.c)
    q = 1.0 - p
    if p <= params.c or p >= 1.0 or q <= 0:
        return 0.0
    # P'(theta) = a * (P-c) * (1-P) / (1-c).
    # Information is P'^2 / (P * (1-P)); one factor (1-P) remains
    # in the numerator. Without it, easy items are wrongly favoured.
    num = (params.a ** 2) * ((p - params.c) ** 2) * q
    den = ((1.0 - params.c) ** 2) * p
    return num / den if den > 0 else 0.0


def theta_to_level(theta: float) -> str:
    """Map theta to pedagogical level label (cut-offs live in level_policy)."""
    from src.domain.level_policy import theta_category
    return theta_category(theta)


def level_confidence(state: ThetaState) -> float:
    """Posterior mass in the estimated level, with fractional boundary cells.

    The production posterior has 61 quadrature points. Splitting cells at
    -0.5 and 1.0 avoids assigning a whole grid cell to one side of a cutoff.
    This is confidence conditional on the current IRT model, not an empirical
    accuracy percentage. Invalid/legacy posterior shapes cannot stop early.
    """
    posterior = np.asarray(state.posterior, dtype=float)
    if posterior.shape != _THETA_GRID.shape or not np.all(np.isfinite(posterior)):
        return 0.0
    if np.any(posterior < 0) or posterior.sum() <= 0:
        return 0.0
    level = theta_to_level(state.theta)
    lower, upper = {
        "below_grade": (-4.0, -0.5),
        "at_grade": (-0.5, 1.0),
        "above_grade": (1.0, 4.0),
    }[level]
    half_step = float(_THETA_GRID[1] - _THETA_GRID[0]) / 2
    left = np.maximum(-4.0, _THETA_GRID - half_step)
    right = np.minimum(4.0, _THETA_GRID + half_step)
    overlap = np.maximum(0.0, np.minimum(right, upper) - np.maximum(left, lower))
    fraction = overlap / (right - left)
    probability = float(np.dot(posterior, fraction) / posterior.sum())
    return min(1.0, max(0.0, probability))


# ── Per-topic mastery tracker ─────────────────────────────────────────────

class AlphaTracker:
    """
    Tracks per-topic mastery score (alpha) on a logit-like scale.
    Separate from the global IRT theta — used for topic-level breakdown.

    Update rule:
      delta = outcome − 0.5          # correct=+0.5, wrong=−0.5
      alpha_new = alpha_old + K * delta
    """

    K: float = 0.4  # learning rate

    def __init__(self) -> None:
        self._alphas: Dict[str, float] = {}
        self._counts: Dict[str, int] = {}

    def update(self, topic_id: str, outcome: float) -> float:
        """Update alpha for topic_id after one answer. Returns new alpha."""
        old = self._alphas.get(topic_id, 0.0)
        delta = outcome - 0.5          # correct=+0.5, wrong=−0.5
        new_alpha = round(old + self.K * delta, 4)
        self._alphas[topic_id] = new_alpha
        self._counts[topic_id] = self._counts.get(topic_id, 0) + 1
        return new_alpha

    def get_alpha(self, topic_id: str) -> float:
        return self._alphas.get(topic_id, 0.0)

    def get_count(self, topic_id: str) -> int:
        """Number of observations (answers) that updated this topic."""
        return int(self._counts.get(topic_id, 0))

    def get_all(self) -> Dict[str, float]:
        return dict(self._alphas)

    def topic_level(self, topic_id: str) -> str:
        return theta_to_level(self.get_alpha(topic_id))

    def to_dict(self) -> dict:
        return {"alphas": self._alphas, "counts": self._counts}

    @classmethod
    def from_dict(cls, data: dict) -> "AlphaTracker":
        tracker = cls()
        tracker._alphas = data.get("alphas", {})
        tracker._counts = data.get("counts", {})
        return tracker

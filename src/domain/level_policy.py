"""Diagnostic Service — the single source of truth for a student's level.

Before this module the level was computed in six places with different rules
(CAT ``theta_to_level``, the report's mix of theta and percent-correct, the
analytics maps, auth, and several front-end dictionaries), so one student could
see contradictory conclusions on different screens.

Rules (approved plan N02, decision 1)
-------------------------------------
* The level is determined ONLY by theta, which is what the adaptive test
  measured.  The share of correct answers is NOT an input: a CAT deliberately
  serves items near the student's ability so that about half are answered
  correctly; the percentage describes the issued item set, not the knowledge.
* ``category`` (3 values) is the CAT classification and is identical to
  ``alpha_engine.theta_to_level`` (theta >= 1.0 above, >= -0.5 at).
* ``status`` (5 values) only *refines* the category, it never contradicts it:

      theta <  -1.4          critical       (category below_grade)
      -1.4 <= theta < -0.5   below          (category below_grade)
      -0.5 <= theta <  0.1   partial_gap    (category at_grade)
       0.1 <= theta <  1.0   on_level       (category at_grade)
      theta >=  1.0          above          (category above_grade)

* ``class_equivalent`` is a monotonic (non-decreasing) function of theta and the
  declared grade only.  See ``_CLASS_BANDS``.
* ``provisional`` is True when the measurement is not precise yet
  (``se`` unknown or > 0.40, the same value the classification stop rule uses).

Outcome rule (``is_correct``)
-----------------------------
The IRT outcome is binary: 1.0 correct, 0.0 wrong/distractor/"don't know".
Historical code (before commit 97a5b4a) scored a hit on a known distractor as a
*partial* 0.5.  The theta likelihood (``alpha_engine._likelihood``) has always
treated only ``== 1.0`` as correct, and the report counted ``>= 1.0``; only the
live answer response used ``>= 0.5``.  A 0.5 therefore means "the student chose
a known wrong option" and is NOT correct.  This module only fixes how answers
are *counted and reported*; theta of past sessions is never recomputed.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# ── Cut-offs (the only place they are written down) ────────────────────────────
THETA_ABOVE = 1.0          # theta >= this  -> above_grade / above
THETA_AT = -0.5            # theta >= this  -> at_grade
THETA_ON_LEVEL = 0.1       # theta >= this  -> on_level (below: partial_gap)
THETA_CRITICAL = -1.4      # theta <  this  -> critical
PROVISIONAL_SE = 0.40      # se > this (or unknown) -> provisional

CATEGORY_LABEL_RU: Dict[str, str] = {
    "below_grade": "Ниже уровня класса",
    "at_grade": "На уровне класса",
    "above_grade": "Выше уровня класса",
}

STATUS_LABEL_RU: Dict[str, str] = {
    "critical": "Критическое отставание",
    "below": "Ниже уровня класса",
    "partial_gap": "Частичные пробелы",
    "on_level": "Соответствует уровню",
    "above": "Выше уровня класса",
}

# Status codes persisted in report_json.overall.status before N02 (and read by
# the front end: STATUS_CFG, VALID_STATUS).  Kept for backward compatibility.
LEGACY_STATUS: Dict[str, str] = {
    "critical": "critical",
    "below": "below_level",
    "partial_gap": "partial_gap",
    "on_level": "on_level",
    "above": "above_level",
}

CATEGORY_OF_STATUS: Dict[str, str] = {
    "critical": "below_grade",
    "below": "below_grade",
    "partial_gap": "at_grade",
    "on_level": "at_grade",
    "above": "above_grade",
}

# Class equivalent.  Each band is (theta upper bound exclusive, part, offset)
# meaning "<part> of grade (declared + offset)".  Bands are ordered by theta, so
# the ordinal grade*3+part never decreases as theta grows; the result is clamped
# to grades 5..11 (the range the bank covers), which preserves monotonicity.
#
#   critical  (<-1.4):  below -2.2 -> start of g-3, otherwise start of g-2
#   below     [-1.4,-0.5):   [-1.4,-0.95) end of g-2,  [-0.95,-0.5) middle of g-1
#   partial   [-0.5, 0.1):   end of g-1
#   on_level  [ 0.1, 1.0):   [0.1,0.55) start of g,    [0.55,1.0) middle of g
#   above     >= 1.0:        [1.0,1.5) end of g, [1.5,2.2) start of g+1, else middle of g+1
_PARTS = ("начало", "середина", "конец")
_CLASS_BANDS = (
    (-2.2, 0, -3),
    (THETA_CRITICAL, 0, -2),
    (-0.95, 2, -2),
    (THETA_AT, 1, -1),
    (THETA_ON_LEVEL, 2, -1),
    (0.55, 0, 0),
    (THETA_ABOVE, 1, 0),
    (1.5, 2, 0),
    (2.2, 0, 1),
    (float("inf"), 1, 1),
)
MIN_GRADE = 5
MAX_GRADE = 11


def is_correct(outcome: Any) -> bool:
    """The only definition of a correct answer for counting/reporting.

    ``None`` and anything below 1.0 (including a legacy partial 0.5) are not
    correct.  See the module docstring for why 0.5 is not credited.
    """
    try:
        return outcome is not None and float(outcome) >= 1.0
    except (TypeError, ValueError):
        return False


def count_solved(answers: Iterable[Any], *, include_deep_scan: bool = False) -> Dict[str, int]:
    """{"solved": N, "total": M} over CAT answers (deep-scan probes excluded)."""
    solved = total = 0
    for answer in answers:
        if not include_deep_scan and bool(getattr(answer, "is_deep_scan", False)):
            continue
        total += 1
        if is_correct(getattr(answer, "outcome", None)):
            solved += 1
    return {"solved": solved, "total": total}


def theta_category(theta: float) -> str:
    """CAT category.  Identical to ``alpha_engine.theta_to_level``."""
    if theta >= THETA_ABOVE:
        return "above_grade"
    if theta >= THETA_AT:
        return "at_grade"
    return "below_grade"


def theta_status(theta: float) -> str:
    if theta < THETA_CRITICAL:
        return "critical"
    if theta < THETA_AT:
        return "below"
    if theta < THETA_ON_LEVEL:
        return "partial_gap"
    if theta < THETA_ABOVE:
        return "on_level"
    return "above"


def class_equivalent(theta: float, grade: int) -> str:
    """Human-readable class equivalent, monotonic in theta (see _CLASS_BANDS)."""
    part, offset = 1, 1
    for upper, band_part, band_offset in _CLASS_BANDS:
        if theta < upper:
            part, offset = band_part, band_offset
            break
    ordinal = (int(grade) + offset) * 3 + part
    ordinal = max(MIN_GRADE * 3, min(MAX_GRADE * 3 + 2, ordinal))
    return f"{_PARTS[ordinal % 3]} {ordinal // 3} класса"


def classify(theta: Optional[float], se: Optional[float], grade: int) -> Dict[str, Any]:
    """Level of a student from the CAT estimate.  Pure function of its inputs.

    Returns ``{"category", "status", "class_equivalent", "provisional"}``.
    With no theta at all nothing can be concluded: the three level fields are
    ``None`` and the result is provisional.
    """
    provisional = se is None or float(se) > PROVISIONAL_SE
    if theta is None:
        return {"category": None, "status": None, "class_equivalent": None,
                "provisional": True}
    value = float(theta)
    return {
        "category": theta_category(value),
        "status": theta_status(value),
        "class_equivalent": class_equivalent(value, grade),
        "provisional": provisional,
    }


def build_level(
    theta: Optional[float],
    se: Optional[float],
    grade: int,
    *,
    solved: int,
    total: int,
) -> Dict[str, Any]:
    """The ``level`` object stored in report_json (and projected elsewhere)."""
    level = classify(theta, se, grade)
    level.update({
        "theta": None if theta is None else round(float(theta), 4),
        "se": None if se is None else round(float(se), 4),
        "solved": int(solved),
        "total": int(total),
    })
    return level

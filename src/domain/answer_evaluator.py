"""
Diagnostic Service — Answer Evaluator

Layered evaluation pipeline for student answers:

  Layer 1  Exact string match         — fastest, handles MCQ and most numeric
  Layer 2  Numeric normalization       — "3,5" = "3.5", "1/2" = "0.5", "4 507" = "4507"
  Layer 3  SymPy equivalence           — "2²" = "4", "√9" = "3", "2(x+1)" = "2x+2"
                                         uses task.sympy_solution if populated,
                                         falls back to task.correct_answer
  Layer 4  Distractor check            — partial credit 0.5 for known misconceptions
  Layer 5  IDK / skip                  — student explicitly skipped

  [Phase 2] Gemini — open-ended text where math comparison is not applicable

Contract with AI digitization pipeline
───────────────────────────────────────
For every task, the pipeline must populate:
  correct_answer     — human-readable canonical answer (e.g. "2²" or "3.5")
  sympy_solution     — sympy-parseable form (e.g. "4" or "3.5" or "2*x + 2")

For answer_type="mcq":  sympy_solution is not required (Layer 1 covers it).
For answer_type="open": sympy_solution enables Layer 3 without Gemini.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from sympy import simplify
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

from .answer_value import answer_value_key

log = logging.getLogger(__name__)

_SYMPY_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)

# ── Math notation preprocessing ───────────────────────────────────────────────

# Unicode superscripts → ASCII exponent notation for sympy
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUPERSCRIPT_MAP = {
    "²": "**2", "³": "**3", "⁴": "**4", "⁵": "**5",
    "⁶": "**6", "⁷": "**7", "⁸": "**8", "⁹": "**9",
}


def _preprocess_for_sympy(value: str) -> str:
    """
    Convert common math notation to sympy-compatible syntax.
    Student input is messy — this handles the most common cases.
    """
    v = value.strip()

    # Typographic minus and en-dash → ASCII minus
    v = v.replace("−", "-").replace("–", "-")

    # Comma decimal separator → dot ("3,5" → "3.5")
    # Only when surrounded by digits to avoid breaking list notation
    v = re.sub(r"(?<=\d),(?=\d)", ".", v)

    # Thousands separator (space between digits: "4 507" → "4507")
    v = re.sub(r"(?<=\d)\s+(?=\d)", "", v)

    # Unicode superscript characters: ² → **2, ³ → **3 …
    for char, replacement in _SUPERSCRIPT_MAP.items():
        v = v.replace(char, replacement)

    # Caret exponent: 2^2 → 2**2
    v = re.sub(r"\^(\d+)", r"**\1", v)

    # Square root variants: √9 → sqrt(9), √(x+1) → sqrt(x+1)
    v = re.sub(r"√\(([^)]+)\)", r"sqrt(\1)", v)
    v = re.sub(r"√(\d+)", r"sqrt(\1)", v)

    # Multiplication sign variants: × → *, · → *
    v = v.replace("×", "*").replace("·", "*")

    # Pi symbol: π → pi
    v = v.replace("π", "pi")

    # Degree symbol in trig context: 90° → not handled without context
    # Left for Phase 2 (Gemini) if needed

    return v


# ── Numeric normalization ─────────────────────────────────────────────────────

def _normalize_number(value: str) -> Optional[float]:
    """
    Parse a student's math answer as a float.
    Handles: comma decimal, thousands space, typographic minus,
             simple fractions (1/2), trailing zeros.
    Returns None if value is not a plain number.
    """
    v = _preprocess_for_sympy(value)
    # Simple fraction: "1/2" → 0.5
    fraction_match = re.fullmatch(r"(-?\d+)\s*/\s*(-?\d+)", v)
    if fraction_match:
        num, den = int(fraction_match.group(1)), int(fraction_match.group(2))
        return None if den == 0 else round(num / den, 10)
    try:
        return float(v)
    except ValueError:
        return None


# ── SymPy equivalence ─────────────────────────────────────────────────────────

def _sympy_equivalent(student_expr: str, canonical_expr: str) -> bool:
    """
    Check whether two math expressions are symbolically equivalent using SymPy.
    Returns False on any parse error — never raises.

    Examples:
      "4"       == "2**2"      → True
      "sqrt(9)" == "3"         → True
      "2*x+2"   == "2*(x+1)"  → True
      "0.5"     == "1/2"       → True
    """
    try:
        local_dict: dict = {}

        expr_student = parse_expr(
            _preprocess_for_sympy(student_expr),
            local_dict=local_dict,
            transformations=_SYMPY_TRANSFORMATIONS,
        )
        expr_correct = parse_expr(
            _preprocess_for_sympy(canonical_expr),
            local_dict=local_dict,
            transformations=_SYMPY_TRANSFORMATIONS,
        )

        diff = simplify(expr_student - expr_correct)
        return diff == 0

    except Exception as exc:
        log.debug("SymPy equivalence check failed: %s", exc)
        return False


# ── Main evaluator ────────────────────────────────────────────────────────────

_IDK_TOKENS = {"не знаю", "незнаю", "?", "skip", "idk", ""}


class AnswerEvaluator:
    """
    Stateless evaluator — call evaluate() per answer.
    Instantiate once in SessionService; thread-safe.
    """

    def evaluate(self, task, student_answer: str) -> Tuple[float, str]:
        """
        Returns (outcome, category):
          outcome   — 0.0 | 1.0
          category  — correct | distractor | wrong | idk

        Outcome mapping:
          correct    → 1.0  — student solved the problem correctly
          distractor → 0.0  — student chose a known misconception answer (wrong, no credit)
          wrong      → 0.0  — any other incorrect answer
          idk        → 0.0  — student explicitly skipped

        NOTE: Distractors are wrong answers. The diagnostic value is captured in
        eval_category="distractor" so that AI reports and analytics can identify
        WHICH specific misconception the student triggered — but the IRT outcome
        is 0.0 (incorrect) to avoid inflating theta with wrong answers.

        MCQ:          Layer 1 → distractor → idk → wrong
        Open/numeric: Layer 1 → numeric → SymPy → distractor → idk → wrong

        Distractors exist in both answer types:
          MCQ  — wrong answer options shown to student (distractor_meta has their misconceptions)
          Open — hidden; caught when student types a known misconception value
        """
        correct = str(task.correct_answer).strip()
        given = student_answer.strip()

        # ── Layer 1: Exact match (case-insensitive) ───────────────────────
        if answer_value_key(given) == answer_value_key(correct):
            return 1.0, "correct"

        # ── Open/numeric only: numeric normalization + SymPy ─────────────
        if task.answer_type != "mcq":
            # Layer 2: Numeric normalization
            given_num = _normalize_number(given)
            correct_num = _normalize_number(correct)
            if given_num is not None and correct_num is not None:
                if given_num == correct_num:
                    return 1.0, "correct"
                skip_sympy = True  # both are plain numbers and they differ
            else:
                skip_sympy = False

            # Layer 3: SymPy symbolic equivalence
            if not skip_sympy:
                sympy_solution = getattr(task, "sympy_solution", None)
                canonical = str(sympy_solution).strip() if sympy_solution else correct
                if _sympy_equivalent(given, canonical):
                    return 1.0, "correct"

        # ── Layer 4: Distractor check (MCQ and open) ─────────────────────
        # Records the specific misconception for analytics/AI report.
        # outcome=0.0 because a distractor hit is a wrong answer — no IRT credit.
        if task.distractor_meta and isinstance(task.distractor_meta, list):
            distractor_values = {
                key
                for d in task.distractor_meta
                if isinstance(d, dict)
                for key in [answer_value_key(d.get("value") or d.get("text") or d.get("content"))]
                if key
            }
            if answer_value_key(given) in distractor_values:
                return 0.0, "distractor"   # ← was 0.5; distractor = wrong answer

        # ── Layer 5: IDK / explicit skip ──────────────────────────────────
        if given.lower() in _IDK_TOKENS:
            return 0.0, "idk"

        return 0.0, "wrong"

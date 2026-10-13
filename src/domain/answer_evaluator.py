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
import os
import re
import traceback
from typing import Optional, Tuple

from sympy import Abs, E, Float, Integer, Rational, Symbol, cos, exp, log as sympy_log, pi, simplify, sin, sqrt, tan
from sympy.parsing.sympy_parser import (
    auto_symbol,
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

from .answer_value import MAX_ANSWER_CHARS, answer_value_key

log = logging.getLogger(__name__)

# ``parse_expr`` ultimately delegates to Python ``eval``.  In particular, its
# default global namespace imports all of SymPy, which is not acceptable for a
# string sent by a student.  We remove auto_symbol (all accepted variables are
# supplied explicitly below) and pass a deliberately tiny parser namespace.
_SYMPY_TRANSFORMATIONS = tuple(
    transformation
    for transformation in standard_transformations
    if transformation is not auto_symbol
) + (implicit_multiplication_application,)

_MAX_SYMBOLIC_INPUT_LENGTH = 256
_MAX_PARENTHESES_DEPTH = 32
_MAX_OPERATOR_COUNT = 64
_MAX_POWER_OPERATORS = 4
_MAX_INTEGER_DIGITS = 16
_MAX_ABSOLUTE_INTEGER_POWER = 12
_ALLOWED_SYMBOLIC_CHARACTERS = re.compile(r"[0-9A-Za-z+*/().\-\s]+")
_IDENTIFIER = re.compile(r"[A-Za-z]+")
_INTEGER_LITERAL = re.compile(r"\d+")
_INTEGER_POWER = re.compile(r"\*\*\s*\(?\s*(-?\d+)\s*\)?")
_SAFE_FUNCTIONS = {
    "sqrt": sqrt,
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "log": sympy_log,
    "exp": exp,
    "abs": Abs,
}
_SAFE_CONSTANTS = {"pi": pi, "E": E}
_SAFE_GLOBALS = {
    "__builtins__": {},
    # Numeric transformations emitted by SymPy's parser need only these
    # constructors. No module, file, reflection or arbitrary callable is
    # available in this namespace.
    "Integer": Integer,
    "Float": Float,
    "Rational": Rational,
}

# ── Math notation preprocessing ───────────────────────────────────────────────

# Unicode superscripts → ASCII exponent notation for sympy
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUPERSCRIPT_MAP = {
    "²": "**2", "³": "**3", "⁴": "**4", "⁵": "**5",
    "⁶": "**6", "⁷": "**7", "⁸": "**8", "⁹": "**9",
}


def _sqrt_parentheses_to_call(text: str) -> str:
    """``√(x+1)`` -> ``sqrt(x+1)``: the same result as ``re.sub(r"√\\(([^)]+)\\)", r"sqrt(\\1)", text)`` in linear time.

    The regex retries ``[^)]+`` from every ``√(`` and so scans the rest of the text each time when there is no
    closing parenthesis (``"√(" * N`` took seconds).  A match ends at the first ``)`` after its ``√(``; a ``√(``
    with no ``)`` to its right cannot match, and neither can any later one.
    """
    parts = []
    last = pos = 0
    while True:
        start = text.find("√(", pos)
        if start < 0:
            break
        end = text.find(")", start + 2)
        if end < 0:
            break
        if end == start + 2:                    # `√()`: an empty radicand is not a match, try the next start
            pos = start + 1
            continue
        parts.append(text[last:start])
        parts.append("sqrt(" + text[start + 2:end] + ")")
        last = pos = end + 1
    parts.append(text[last:])
    return "".join(parts)


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
    v = _sqrt_parentheses_to_call(v)
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
    Returns None if value is not a plain number (also when it is too long / too large to be one: `int` refuses
    more than ``sys.get_int_max_str_digits()`` digits with ValueError, `num / den` of huge ints overflows).
    """
    if len(value) > MAX_ANSWER_CHARS:
        return None
    v = _preprocess_for_sympy(value)
    try:
        # Simple fraction: "1/2" → 0.5
        fraction_match = re.fullmatch(r"(-?\d+)\s*/\s*(-?\d+)", v)
        if fraction_match:
            num, den = int(fraction_match.group(1)), int(fraction_match.group(2))
            return None if den == 0 else round(num / den, 10)
        return float(v)
    except (ValueError, OverflowError, RecursionError):
        return None


# ── SymPy equivalence ─────────────────────────────────────────────────────────

def _safe_parse_symbolic_expression(value: str):
    """Parse a bounded school-math expression without executable Python input.

    This is an input boundary for student answers, not a general SymPy parser.
    It accepts the notation already supported by the evaluator (numbers,
    single-letter variables, arithmetic, parentheses and a small function
    allow-list), then creates every symbol explicitly. Any other token is
    rejected before ``parse_expr`` is reached.
    """
    expression = _preprocess_for_sympy(value)
    if not expression or len(expression) > _MAX_SYMBOLIC_INPUT_LENGTH:
        raise ValueError("symbolic expression has invalid length")
    if not _ALLOWED_SYMBOLIC_CHARACTERS.fullmatch(expression):
        raise ValueError("symbolic expression contains unsupported characters")
    if "__" in expression:
        raise ValueError("dunder names are not valid math")
    # A decimal point is allowed only inside a numeric literal. This rejects
    # attribute syntax such as ``x.__class__`` even if future character rules
    # are relaxed by accident.
    if re.search(r"(?<!\d)\.|\.(?!\d)", expression):
        raise ValueError("decimal point must be surrounded by digits")
    if sum(expression.count(operator) for operator in ("+", "-", "*", "/")) > _MAX_OPERATOR_COUNT:
        raise ValueError("symbolic expression has too many operators")
    if any(len(number.group(0)) > _MAX_INTEGER_DIGITS for number in _INTEGER_LITERAL.finditer(expression)):
        raise ValueError("numeric literal is too large")

    powers = list(_INTEGER_POWER.finditer(expression))
    if len(powers) > _MAX_POWER_OPERATORS:
        raise ValueError("symbolic expression has too many powers")
    if any(abs(int(power.group(1))) > _MAX_ABSOLUTE_INTEGER_POWER for power in powers):
        raise ValueError("integer power is outside the supported school range")

    depth = 0
    for character in expression:
        if character == "(":
            depth += 1
            if depth > _MAX_PARENTHESES_DEPTH:
                raise ValueError("symbolic expression is too deeply nested")
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("symbolic expression has unbalanced parentheses")
    if depth != 0:
        raise ValueError("symbolic expression has unbalanced parentheses")

    local_dict = {**_SAFE_FUNCTIONS, **_SAFE_CONSTANTS}
    for match in _IDENTIFIER.finditer(expression):
        name = match.group(0)
        following = expression[match.end():].lstrip()
        if name in _SAFE_FUNCTIONS:
            if not following.startswith("("):
                raise ValueError("math function must be called")
            continue
        if name in _SAFE_CONSTANTS:
            if following.startswith("("):
                raise ValueError("math constant cannot be called")
            continue
        if len(name) != 1:
            raise ValueError("only single-letter variables are supported")
        local_dict[name] = Symbol(name, real=True)

    return parse_expr(
        expression,
        local_dict=local_dict,
        global_dict=_SAFE_GLOBALS,
        transformations=_SYMPY_TRANSFORMATIONS,
    )

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
        expr_student = _safe_parse_symbolic_expression(student_expr)
        expr_correct = _safe_parse_symbolic_expression(canonical_expr)

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
        One bad answer never breaks grading: an answer longer than ``MAX_ANSWER_CHARS`` is wrong without being
        looked at, and an exception while comparing counts as wrong too (logged without the answer text -
        exception messages of ``int`` / ``float`` quote it).  ``_evaluate`` holds the rules.
        """
        try:
            return self._evaluate(task, student_answer)
        except Exception as exc:
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            log.warning(
                "answer_evaluation_failed task_id=%s error_type=%s at=%s:%s answer_len=%s",
                getattr(task, "id", None) or getattr(task, "task_id", None), type(exc).__name__,
                os.path.basename(frame.filename), frame.lineno, len(student_answer) if isinstance(student_answer, str) else "?",
            )
            return 0.0, "wrong"

    def _evaluate(self, task, student_answer: str) -> Tuple[float, str]:
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
        if len(given) > MAX_ANSWER_CHARS:
            log.warning(
                "answer_too_long task_id=%s answer_len=%s", getattr(task, "id", None) or getattr(task, "task_id", None), len(given)
            )
            return 0.0, "wrong"

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

"""How tasks are shown in diagnostic UI (MCQ vs open input)."""
from __future__ import annotations

import random
from typing import Any, Optional

from .proof_answer import extract_proof_expression, format_proof_answer, is_proof_placeholder
from .answer_value import answer_value_key, answers_equivalent

# Types that never get auto-built MCQ (no meaningful button choices).
_DIAG_ALWAYS_OPEN_TYPES = frozenset({
    "open_text",
})

# A yes/no question is a natural two-button choice; it needs only the one
# opposite distractor instead of the usual two.
_BINARY_ANSWERS = frozenset({"да", "нет", "верно", "неверно", "yes", "no"})

_LETTER_OPTION_KEYS = frozenset({"a", "b", "c", "d", "а", "б", "в", "г"})


def _is_binary_answer(value: str) -> bool:
    return answer_value_key(value).strip(".!") in _BINARY_ANSWERS


def _is_letter_only(values: list[str]) -> bool:
    """Options that are bare letters point at choices printed in the question.

    The UI labels buttons A, B, C, D by position, so reordering such options
    would put the letter "C" under the button labelled "A".
    """
    return all(answer_value_key(v).strip(".)") in _LETTER_OPTION_KEYS for v in values)


def _same_on_screen(value: str, latex: str, other_value: str, other_latex: str) -> bool:
    """Two options a student cannot tell apart: same value or same display.

    Grading follows what the student sees. Historical rows sometimes pair a
    display string with a differently written (or even different) raw value;
    if an option is displayed exactly like the key it must count as the key,
    and two options displayed identically must not both be offered.
    """
    return answers_equivalent(value, other_value) or answers_equivalent(latex or value, other_latex or other_value)


def _ordered(pairs: list[tuple[str, str]], seed: Optional[str]) -> tuple[list[str], list[str]]:
    """Return (values, latex), shuffled deterministically when a seed is given.

    The seed is the session and task, so every student gets an independent
    order that never changes within their attempt (e.g. after a page reload).
    Without a seed the canonical order is kept.
    """
    pairs = list(pairs)
    if seed is not None and not _is_letter_only([value for value, _ in pairs]):
        random.Random(seed).shuffle(pairs)
    return [value for value, _ in pairs], [latex for _, latex in pairs]


def _distractor_values(task: Any) -> list[str]:
    dm = getattr(task, "distractor_meta", None)
    if not isinstance(dm, list):
        return []
    out: list[str] = []
    for d in dm:
        if isinstance(d, dict):
            # `text` is a legacy canonical shape. Read it at the API boundary
            # without mutating the stored task or inventing a new answer.
            v = str(d.get("value") or d.get("text") or d.get("content") or "").strip()
            if v:
                out.append(v)
    return out


def _has_stored_options(task: Any) -> bool:
    """True when an author supplied a complete-enough UI option list."""
    existing = getattr(task, "answer_options", None)
    return isinstance(existing, list) and len(existing) >= 2


def should_show_diag_mcq(task: Any) -> bool:
    """Diagnostic: MCQ whenever we have ≥2 choices (stored or from distractor_meta)."""
    at = (getattr(task, "answer_type", "") or "").lower()
    if at in _DIAG_ALWAYS_OPEN_TYPES:
        return False

    # An author-supplied option list is the exact UI source. distractor_meta
    # enriches matching wrong choices with error logic, but never replaces an
    # independently authored list.
    if _has_stored_options(task):
        return True
    distractors = _distractor_values(task)
    if len(distractors) >= 2:
        return True
    correct = str(getattr(task, "correct_answer", "") or "").strip()
    return bool(distractors) and _is_binary_answer(correct)


def _latex_for_value(task: Any, value: str) -> str:
    correct = str(getattr(task, "correct_answer", "") or "").strip()
    if answer_value_key(value) == answer_value_key(correct):
        return str(getattr(task, "correct_answer_latex", "") or "").strip()
    for d in getattr(task, "distractor_meta", None) or []:
        if not isinstance(d, dict):
            continue
        canonical = str(d.get("value") or d.get("text") or d.get("content") or "").strip()
        if answer_value_key(canonical) == answer_value_key(value):
            return str(d.get("value_latex") or d.get("text_latex") or d.get("content_latex") or "").strip()
    return ""


def _extract_option_latex(x: Any) -> str:
    """Return an explicitly stored display representation, if present."""
    if not isinstance(x, dict):
        return ""
    for key in ("latex", "value_latex", "content_latex", "text_latex"):
        value = x.get(key)
        if value:
            return str(value).strip()
    return ""


def _extract_option_text(x: Any) -> str:
    """Safely extract display text from an option.

    answer_options rows can be stored in multiple formats:
      - plain string:  "x > 0"
      - dict:          {'text': 'x > 0', 'is_correct': True}
      - nested dict:   {'value': 'x > 0'}

    Using str() on a dict produces "{'text': '...', 'is_correct': True}"
    which breaks both display and IRT scoring (student_answer mismatch).
    """
    if isinstance(x, dict):
        for key in ("text", "value", "content"):
            v = x.get(key)
            if v is not None:
                return str(v).strip()
        return ""
    return str(x).strip()

def _clean_correct_answer(task: Any) -> str:
    ca = str(getattr(task, "correct_answer", "") or "").strip()
    if is_proof_placeholder(ca):
        return format_proof_answer(str(getattr(task, "question_text", "") or ""))
    return ca


def build_diag_answer_options(
    task: Any, seed: Optional[str] = None,
) -> tuple[Optional[list[str]], Optional[list[str]]]:
    """
    Build MCQ options (+ parallel LaTeX) for diagnostic presentation.
    Returns (None, None) when task should use open input.

    The grader compares the submitted option value with the key, so the one
    option that equals the key — in whatever notation it was stored — is
    served with the key itself as its value while keeping its own display.
    Options that are the same value in another notation are merged, so a
    student never sees two versions of one answer with only one counted.

    ``seed`` (session + task) enables a stable per-attempt shuffle.
    """
    correct = _clean_correct_answer(task)
    key_latex = _latex_for_value(task, correct)
    distractors = _distractor_values(task)
    existing = getattr(task, "answer_options", None)
    if _has_stored_options(task) and isinstance(existing, list):
        stored_latex = getattr(task, "answer_options_latex", None)
        stored = []
        for index, option in enumerate(existing):
            value = _extract_option_text(option)
            latex = (
                (str(stored_latex[index]).strip() if isinstance(stored_latex, list) and index < len(stored_latex) and stored_latex[index] else "")
                or _extract_option_latex(option)
                or _latex_for_value(task, value)
            )
            stored.append((value, latex))
        key_index = next(
            (i for i, (value, latex) in enumerate(stored)
             if correct and _same_on_screen(value, latex, correct, key_latex)),
            None,
        )
        pairs: list[tuple[str, str]] = []
        for index, (value, latex) in enumerate(stored):
            if index == key_index:
                # Keep the author's notation on screen: showing the key's own
                # notation (0,22 among fractions 1/4, 1/5) would give it away.
                pairs.append((correct, latex or value))
            elif key_index is not None and _same_on_screen(value, latex, correct, key_latex):
                continue
            elif any(_same_on_screen(value, latex, served, shown) for served, shown in pairs):
                continue
            else:
                pairs.append((value, latex))
        if correct and key_index is None:
            pairs.append((correct, key_latex or correct))
        return _ordered(pairs, seed)

    if correct and (len(distractors) >= 2 or (distractors and _is_binary_answer(correct))):
        pairs = [(correct, key_latex)] if answer_value_key(correct) else []
        for value in distractors:
            latex = _latex_for_value(task, value)
            if not answer_value_key(value) or any(_same_on_screen(value, latex, served, shown) for served, shown in pairs):
                continue
            pairs.append((value, latex))
        if len(pairs) >= 2:
            return _ordered(pairs, seed)

    return None, None


def diag_answer_type_for_display(task: Any, options: Optional[list[str]]) -> str:
    """Use mcq when options are shown so evaluator treats answer as a choice."""
    if options:
        return "mcq"
    return str(getattr(task, "answer_type", "") or "open")

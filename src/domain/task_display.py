"""How tasks are shown in diagnostic UI (MCQ vs open input)."""
from __future__ import annotations

import random
from typing import Any, Optional

from .proof_answer import extract_proof_expression, format_proof_answer, is_proof_placeholder
from .answer_value import answer_value_key

# Types that never get auto-built MCQ (no meaningful button choices).
_DIAG_ALWAYS_OPEN_TYPES = frozenset({
    "open_text",
})


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
    return len(_distractor_values(task)) >= 2


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


def build_diag_answer_options(task: Any) -> tuple[Optional[list[str]], Optional[list[str]]]:
    """
    Build shuffled MCQ options (+ parallel LaTeX) for diagnostic presentation.
    Returns (None, None) when task should use open input.
    """
    correct = _clean_correct_answer(task)
    distractors = _distractor_values(task)
    existing = getattr(task, "answer_options", None)
    if _has_stored_options(task) and isinstance(existing, list):
        opts = [_extract_option_text(x) for x in existing]
        stored_latex = getattr(task, "answer_options_latex", None)
        latex = [
            (str(stored_latex[index]).strip() if isinstance(stored_latex, list) and index < len(stored_latex) and stored_latex[index] else "")
            or _extract_option_latex(option)
            or _latex_for_value(task, value)
            for index, (option, value) in enumerate(zip(existing, opts))
        ]
        correct_key = answer_value_key(correct)
        if correct and correct_key and not any(answer_value_key(option) == correct_key for option in opts):
            opts.append(correct)
            latex.append(_latex_for_value(task, correct) or correct)
        return opts, latex

    if correct and len(distractors) >= 2:
        seen: set[str] = set()
        opts: list[str] = []
        for value in [correct, *distractors]:
            key = answer_value_key(value)
            if not key or key in seen:
                continue
            seen.add(key)
            opts.append(value)
        shuffled = list(opts)
        random.shuffle(shuffled)
        return shuffled, [_latex_for_value(task, value) for value in shuffled]

    return None, None


def diag_answer_type_for_display(task: Any, options: Optional[list[str]]) -> str:
    """Use mcq when options are shown so evaluator treats answer as a choice."""
    if options:
        return "mcq"
    return str(getattr(task, "answer_type", "") or "open")

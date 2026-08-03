"""How tasks are shown in diagnostic UI (MCQ vs open input)."""
from __future__ import annotations

import random
from typing import Any, Optional

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
            v = str(d.get("value", "")).strip()
            if v:
                out.append(v)
    return out


def should_show_diag_mcq(task: Any) -> bool:
    """Diagnostic: MCQ whenever we have ≥2 choices (stored or from distractor_meta)."""
    at = (getattr(task, "answer_type", "") or "").lower()
    if at in _DIAG_ALWAYS_OPEN_TYPES:
        return False

    existing = getattr(task, "answer_options", None)
    if isinstance(existing, list) and len(existing) >= 2:
        return True

    return len(_distractor_values(task)) >= 2


def _latex_for_value(task: Any, value: str) -> str:
    correct = str(getattr(task, "correct_answer", "") or "").strip()
    if value == correct:
        return str(getattr(task, "correct_answer_latex", "") or "").strip()
    for d in getattr(task, "distractor_meta", None) or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("value", "")).strip() == value:
            return str(d.get("value_latex", "") or "").strip()
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


def build_diag_answer_options(task: Any) -> tuple[Optional[list[str]], Optional[list[str]]]:
    """
    Build shuffled MCQ options (+ parallel LaTeX) for diagnostic presentation.
    Returns (None, None) when task should use open input.
    """
    existing = getattr(task, "answer_options", None)
    if isinstance(existing, list) and len(existing) >= 2:
        opts = [_extract_option_text(x) for x in existing]
        latex = [_latex_for_value(task, o) for o in opts]
        return opts, latex

    if not should_show_diag_mcq(task):
        return None, None

    correct = str(getattr(task, "correct_answer", "") or "").strip()
    if not correct:
        return None, None

    seen: set[str] = set()
    opts: list[str] = []
    for v in [correct, *_distractor_values(task)]:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        opts.append(v)

    if len(opts) < 2:
        return None, None

    shuffled = list(opts)
    random.shuffle(shuffled)
    latex = [_latex_for_value(task, o) for o in shuffled]
    return shuffled, latex


def diag_answer_type_for_display(task: Any, options: Optional[list[str]]) -> str:
    """Use mcq when options are shown so evaluator treats answer as a choice."""
    if options:
        return "mcq"
    return str(getattr(task, "answer_type", "") or "open")

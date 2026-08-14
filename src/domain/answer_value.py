"""Non-destructive comparison keys for canonical answer values.

Some historical options were stored with only outer `$...$` delimiters while
their matching distractor used the same value without delimiters. This helper
normalizes that transport/display wrapper only; it never parses, solves, or
rewrites a mathematical expression.
"""
from __future__ import annotations


def answer_value_key(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 4 and text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    return text.casefold()

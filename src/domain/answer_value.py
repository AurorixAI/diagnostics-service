"""Non-destructive comparison keys for canonical answer values.

Some historical options were stored with only outer `$...$` delimiters while
their matching distractor used the same value without delimiters. This helper
normalizes that transport/display wrapper only; it never parses, solves, or
rewrites a mathematical expression.
"""
from __future__ import annotations


import re

def answer_value_key(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 4 and text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    
    # Mathematical normalization
    text = text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    text = text.replace("\\cdot", "*").replace("\\times", "*")
    text = text.replace("\\cup", "∪").replace("\\cap", "∩")
    text = text.replace("\\infty", "∞").replace("\\pi", "π")
    text = text.replace("\\le ", "\\leq ").replace("\\ge ", "\\geq ")
    text = text.replace("\\,", "").replace("\\;", "").replace("\\quad", "").replace("\\qquad", "")
    text = text.replace("{,}", ",")
    text = text.replace("\\left(", "(").replace("\\right)", ")")
    text = text.replace("\\left[", "[").replace("\\right]", "]")
    text = text.replace("\\left\\{", "{").replace("\\right\\}", "}")
    text = text.replace("\\sin", "sin").replace("\\cos", "cos").replace("\\tan", "tan").replace("\\tg", "tg")
    text = text.replace("\\log", "log").replace("\\ln", "ln")
    # remove whitespace
    text = re.sub(r"\s+", "", text)
    return text.casefold()

"""Non-destructive comparison keys for canonical answer values.

Some historical options were stored with only outer `$...$` delimiters while
their matching distractor used the same value without delimiters. This helper
normalizes that transport/display wrapper only; it never parses, solves, or
rewrites a mathematical expression.
"""
from __future__ import annotations


import ast
import hashlib
import json
import re
from fractions import Fraction
from typing import Optional

# The longest answer text the service looks into: a student's answer (the API rejects longer ones with 422), a
# stored key / option / distractor and a journal row alike.  Real content is well below it (bank of 12.10.2026: the
# longest served choice is 1283 characters, 14 tasks exceed 500, nothing exceeds 1283); a chosen option is sent as its
# full text, so the limit must stay above the longest option of the bank.  A longer text is never parsed, normalised
# or solved: it only ever equals itself (see ``_oversize_key``).  Everything below is linear in the length, so this is
# a bound on memory / bytes and not the thing that keeps the event loop free.
MAX_ANSWER_CHARS = 2000
_MAX_WRAPPED_ANSWER_CHARS = MAX_ANSWER_CHARS
_OVERSIZE_PREFIX = "\ue002oversize:"      # private-use mark: no normalised key of a real answer starts with it


def _oversize_key(text: str) -> str:
    """Comparison key of a text longer than ``MAX_ANSWER_CHARS``: equal only to the identical text."""
    return _OVERSIZE_PREFIX + hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def display_student_answer(raw: object) -> object:
    """The answer text a report shows, without changing the (append-only) journal row.

    Some historical rows hold the answer as the repr or JSON of a transport object,
    ``{'text': '$x \\in [1; +\\infty)$', 'is_correct': False}``.  When the value is such a dict with a
    string ``text``, that text is returned; anything else (plain answers, set notation such as
    ``{1; 2}`` or ``{x | x>0}``, malformed or oversized values, non-strings) comes back unchanged.
    Only ``json.loads`` and ``ast.literal_eval`` are used - nothing is evaluated.
    """
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if not text.startswith("{") or len(text) > _MAX_WRAPPED_ANSWER_CHARS:
        return raw
    value: object = None
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):        # a deeply nested `{"a":{"a":...` is a RecursionError, not a ValueError
        try:
            value = ast.literal_eval(text)
        except Exception:                       # SyntaxError, ValueError, MemoryError, RecursionError, ...
            return raw
    if isinstance(value, dict):
        inner = value.get("text")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
    return raw

def answer_value_key(value: object) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_ANSWER_CHARS:
        return _oversize_key(text)
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


_SINGLE_TOKEN_BRACES_RE = re.compile(r"([\^_])\{\s*([^\W_])\s*\}")

# --- equivalent spellings, REPORT SIDE ONLY ---------------------------------------------------------------------
# A task's stored options were shown to the student in one spelling (older snapshots: plain Unicode) while the
# bank's distractor_meta was later rewritten in another (LaTeX).  Only 1:1 spellings of the same symbol are merged
# here; nothing is parsed, simplified or solved.  When in doubt the two spellings stay different: a missed match
# falls back to the generic report text, a false match shows the student someone else's explanation.
_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}   # not merged on purpose: phi/varphi, epsilon/varepsilon, vartheta ... (one Unicode letter, two different glyphs)
_COMMAND_SYMBOLS = {
    **_GREEK, "infty": "∞", "in": "∈", "notin": "∉", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "pm": "±", "mp": "∓", "emptyset": "∅", "varnothing": "∅",
}
_FUNCTION_NAMES = frozenset(
    ("sin cos tan tg cot ctg sec csc arcsin arccos arctan arctg arccot arcctg sinh cosh tanh coth "
     "lg ln log exp max min").split()
)
_NUMBER_SETS = {"N": "ℕ", "Z": "ℤ", "Q": "ℚ", "R": "ℝ"}
_UNICODE_SPELLINGS = str.maketrans({"\u2212": "-", "·": "*", "⋅": "*", "×": "*", "²": "^2", "³": "^3"})
_GREEK_LETTERS = "".join(_GREEK.values())

_COMMAND_RE = re.compile(r"(?<!\\)\\([A-Za-z]+)(?![A-Za-z])")
_OPERATORNAME_RE = re.compile(r"\\operatorname\s*\{\s*([A-Za-z]+)\s*\}")
_MATHBB_RE = re.compile(r"\\mathbb\s*(?:\{\s*([NZQR])\s*\}|([NZQR])(?![A-Za-z]))")
_BARE_SET_AFTER_IN_RE = re.compile(r"([∈∉])\s*([NZQR])(?![A-Za-z0-9])")
_DEGREE_RE = re.compile(r"\^\s*(?:\{\s*\\circ\s*\}|\\circ(?![A-Za-z]))")
_ASCII_LE_RE, _ASCII_GE_RE = re.compile(r"<=(?!>)"), re.compile(r">=")
# `\sqrt3` is TeX for "the root of the next token"; `√3` / `√x` / `√(x+1)` is the same root.  `√2x`, `√12.5`, `√x^2`
# (radicand or what the exponent belongs to is a guess) and nested parentheses are left alone.
_BARE_SQRT_RE = re.compile(rf"\\sqrt\s*([0-9A-Za-z{_GREEK_LETTERS}])")
_UNI_SQRT_ATOM_RE = re.compile(
    rf"√\s*(\d+|[A-Za-z{_GREEK_LETTERS}])(?!\s*[A-Za-z0-9{_GREEK_LETTERS}^_(\\√]|[.,]\d)"
)
_UNI_SQRT_PAREN_RE = re.compile(r"√\s*\(([^()]+)\)(?!\s*[A-Za-z0-9^_(\\√])")
# `6, 5π/6`: a comma + space between digits is a list separator (a decimal comma has no space).  The key drops all
# whitespace, so the separator is remembered with a private marker until fractions are recognised.
_LIST_COMMA_RE = re.compile(r"(?<=\d),\s+(?=\d)")
_LIST_MARK = "\ue000"
# `1 3/25` is the mixed number 1 3/25, not the fraction 13/25: a gap between two digits is remembered the same way so
# that neither neighbour can become a fraction atom.  Both markers are removed again from the finished key, so for
# everything except fractions the key still ignores spaces exactly as ``answer_value_key`` does.
_FRACTION_GAP_RE = re.compile(r"(?<=\d)(?:\s|~|\\[,;:! ])+(?=\d)")
_GAP_MARK = "\ue001"


def _equivalent_spellings(text: str) -> str:
    """Rewrite 1:1 alternative spellings of one symbol to a single form (before ``answer_value_key``)."""
    text = text.translate(_UNICODE_SPELLINGS)
    text = _ASCII_LE_RE.sub("≤", text)
    text = _ASCII_GE_RE.sub("≥", text)
    text = _DEGREE_RE.sub("°", text)
    text = _OPERATORNAME_RE.sub(lambda m: m.group(1) if m.group(1) in _FUNCTION_NAMES else m.group(0), text)
    text = _MATHBB_RE.sub(lambda m: _NUMBER_SETS[m.group(1) or m.group(2)], text)

    def command(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name in _COMMAND_SYMBOLS:
            return _COMMAND_SYMBOLS[name]
        return name if name in _FUNCTION_NAMES else m.group(0)

    text = _COMMAND_RE.sub(command, text)
    text = _BARE_SQRT_RE.sub(r"\\sqrt{\1}", text)
    text = _UNI_SQRT_ATOM_RE.sub(r"\\sqrt{\1}", text)
    text = _UNI_SQRT_PAREN_RE.sub(r"\\sqrt{\1}", text)
    # a bare N/Z/Q/R is the number set ONLY right after a membership sign (`k ∈ Z`); anywhere else it is just a letter
    text = _BARE_SET_AFTER_IN_RE.sub(lambda m: m.group(1) + _NUMBER_SETS[m.group(2)], text)
    text = _LIST_COMMA_RE.sub("," + _LIST_MARK, text)
    return _FRACTION_GAP_RE.sub(_GAP_MARK, text)


# A numerator is one "atom": an integer, a single letter, `\sqrt` of one of those, or an integer coefficient in front
# of a letter / root (`5π`, `2x`, `3√2`); a denominator is the same WITHOUT a coefficient (`1/2π` may be ½π or
# 1/(2π), so `2π` is never taken as a denominator).  `2πk` and `x+1` are not atoms.  Applied to the already
# normalised key (lower case, no spaces).  `(?<!\d)` keeps the scan linear: a number is tried only from its first
# digit (a start inside a digit run is rejected anyway, its left neighbour being a digit).
_SYM = rf"(?:[a-z{_GREEK_LETTERS.lower()}])"
_ROOT = rf"(?:\\sqrt\{{(?:\d+|{_SYM})\}})"
_NUMERATOR = rf"(?:\d+(?:{_SYM}|{_ROOT})?|{_SYM}|{_ROOT})"
_DENOMINATOR = rf"(?:\d+|{_SYM}|{_ROOT})"
_PLAIN_FRACTION_RE = re.compile(rf"(?<!\d)({_NUMERATOR})/({_DENOMINATOR})")
# `:` and `÷` are division signs as often as separators and are NOT a left boundary (`8:4/2`, like `8/4/2`, is not
# rewritten); `:` after the denominator is only a division (`1/2:3` is `(1/2):3`) and stays a right boundary.
_FRACTION_LEFT = frozenset("([{=+-*<>≤≥≠,;|±∓∈∉∪∩" + _LIST_MARK)
_FRACTION_RIGHT = frozenset(")]}=+-*<>≤≥≠,;:|±∓∈∉∪∩")
_FRACTION_SIGNS = "+-±∓"


def _plain_fractions_to_frac(key: str) -> str:
    """``π/45`` -> ``\\frac{π}{45}`` when A and B are single atoms standing on their own.

    "On their own" = the neighbours are the start / end of the answer or an operator / bracket / separator, so
    ``1/2x`` (is it ½x or 1/(2x)?), ``a/b/c``, ``8/-4/2``, ``8:4/2``, ``x^1/2``, ``0.5/2`` and ``1,5/2`` (decimal
    comma) are never rewritten and stay different from any ``\\frac``.  A numerator / denominator that is a sum, a
    product of several letters or a power is never an atom, so ``(x+1)/2`` and ``\\frac{x+1}{2}`` keep different keys.
    """
    def replace(m: "re.Match[str]") -> str:
        start, end = m.span()
        before = key[start - 1] if start else ""
        after = key[end] if end < len(key) else ""
        if before and before not in _FRACTION_LEFT:
            return m.group(0)
        sign = start
        while sign > 0 and key[sign - 1] in _FRACTION_SIGNS:
            sign -= 1
        if sign < start and sign > 0 and key[sign - 1] in "/÷:^_":         # 8/-4/2, x^-1/2: what binds to what?
            return m.group(0)
        if before == "," and start >= 2 and key[start - 2].isdigit() and m.group(1)[0].isdigit():
            return m.group(0)                                                 # 1,5/2 : decimal comma
        if after and after not in _FRACTION_RIGHT and not (after == "." and end + 1 == len(key)):
            return m.group(0)
        if after == "," and key[end + 1:end + 2].isdigit():                  # 1/2,5 : decimal comma
            return m.group(0)
        return "\\frac{%s}{%s}" % (m.group(1), m.group(2))

    return _PLAIN_FRACTION_RE.sub(replace, key)


def report_answer_key(value: object) -> str:
    """Key for matching a STORED student answer to the options / distractors of a (since repaired) task.

    REPORT SIDE ONLY: scoring at answer time keeps using ``answer_value_key`` and the stored outcome.
    On top of ``answer_value_key`` (``\\dfrac`` = ``\\frac``, whitespace ignored) every ``$`` is dropped
    and a braced group that holds a SINGLE character is the same as the bare character:
    ``x^{3}`` = ``x^3``, ``a_{2}`` = ``a_2`` (content waves rewrite stored values this way).  A group of
    several characters is never unwrapped, so ``x^{13}`` (exponent 13) stays different from ``x^13``
    (``x^1`` followed by ``3``) and from ``x^1 3``.  Mirrors the front's ``canonicalAnswerKey`` for these
    cases without its broader brace stripping.

    Older snapshots show options in plain Unicode (``$π/45$``, ``k ∈ Z``) while the bank was rewritten in LaTeX
    (``$\\dfrac{\\pi}{45}$``, ``k \\in \\mathbb{Z}$``).  The same symbol spelled either way gets one key (``π`` =
    ``\\pi``, ``≤`` = ``\\le`` = ``\\leq``, ``ℤ`` = ``\\mathbb{Z}``, ``√3`` = ``\\sqrt{3}`` ...) and a fraction of two
    single atoms is the same as its slash form (``5π/2`` = ``\\frac{5\\pi}{2}``); see ``_equivalent_spellings``.

    Keys are compared with keys, never fed back in: the key is NOT idempotent for a mixed number.  ``4 3/28`` keeps
    its digit gap while the fractions are recognised (so it never becomes the fraction ``43/28``) and loses it in the
    finished key ``43/28``; keying that key again would read it as the fraction ``\\frac{43}{28}``.  Every caller keys
    raw stored values (answers, options, distractors) and compares the results only with each other.
    """
    text = str(value or "")
    if len(text) > MAX_ANSWER_CHARS:
        return _oversize_key(text.strip())
    text = text.replace("$", "")
    text = _SINGLE_TOKEN_BRACES_RE.sub(r"\1\2", text)
    key = _plain_fractions_to_frac(answer_value_key(_equivalent_spellings(text)))
    return key.replace(_LIST_MARK, "").replace(_GAP_MARK, "")


_LEFT_RIGHT_RE = re.compile(r"\\(?:left|right)(?![A-Za-z])")
_DIGIT_GAP_RE = re.compile(r"(?<=\d)\s+(?=\d)")
_DECIMAL_COMMA_RE = re.compile(r"(?<=\d)(?:\{,\}|,)(?=\d)")
# `\sin{\alpha}` renders exactly like `\sin \alpha`: braces around a single
# argument of a function (after an optional index or power) are invisible.
_FUNC_ARG_BRACES_RE = re.compile(
    r"(\\(?:arcsin|arccos|arctan|arctg|arcctg|sin|cos|tan|tg|cot|ctg|sec|csc|ln|lg|log|exp)"
    r"(?:[_^](?:\{[^{}]*\}|[0-9A-Za-z]))*)\s*\{(\\?[A-Za-z]+|\d+)\}"
)
_THIN_SPACE_RE = re.compile(r"\\[,;!]|\\q?quad(?![A-Za-z])")
# `\s*(\d+)?\s*` splits a run of spaces in N ways when the match fails (quadratic); `\s*(?:(\d+)\s*)?` accepts the same
# texts and tries each position once.
_MIXED_LATEX_RE = re.compile(r"(-?)\s*(?:(\d+)\s*)?\\frac\{\s*(-?\d+)\s*\}\{\s*(\d+)\s*\}")
_MIXED_PLAIN_RE = re.compile(r"(-?)(\d+)\s+(\d+)\s*/\s*(\d+)")
_FRACTION_RE = re.compile(r"(-?\d+)\s*/\s*(\d+)")
_THOUSANDS_RE = re.compile(r"-?\d{1,3}(?: \d{3})+")
_DECIMAL_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _strip_trailing_punct(text: str) -> str:
    """Drop the closing whitespace / periods / semicolons (what ``[\\s.;]+$`` removed, without its quadratic scan)."""
    end = len(text)
    while end and (text[end - 1] in ".;" or text[end - 1].isspace()):
        end -= 1
    return text[:end]


def _notation_key(value: object) -> str:
    """answer_value_key after removing every math delimiter, not only outer ones.

    `$[-4$; $2]$` and `$[-4; 2]$` are the same value split differently into
    formulas, and `0{,}78` and `0.78` are one decimal written with a Russian
    and an English separator. Invisible braces (`\\sin{\\alpha}`) and a
    closing period or semicolon do not change an answer either. A space
    between two digits is kept as a marker so the mixed number `3 4/9` never
    collapses into the different fraction `34/9`.
    """
    text = str(value or "")
    if len(text) > MAX_ANSWER_CHARS:
        return _oversize_key(text.strip())
    text = text.replace("$", "").replace("−", "-")
    text = _LEFT_RIGHT_RE.sub("", text)
    text = _FUNC_ARG_BRACES_RE.sub(r"\1 \2", text)
    text = _DECIMAL_COMMA_RE.sub(".", text)
    text = _strip_trailing_punct(text)
    text = _DIGIT_GAP_RE.sub("␣", text)
    return answer_value_key(text)


def exact_number(value: object) -> Optional[Fraction]:
    """Exact rational value of a plain number, fraction or mixed number.

    Recognises only unambiguous numeric forms; anything else (expressions,
    intervals, lists, percentages) returns None so it can never be matched
    by value. There is deliberately no floating-point tolerance: 1/3 and
    0,33 are different answers.  Never raises: a text longer than ``MAX_ANSWER_CHARS`` is not a number, and
    neither is one whose digits Python refuses to convert (``int`` / ``Fraction`` raise ``ValueError`` past
    ``sys.get_int_max_str_digits()``).
    """
    text = str(value or "")
    if len(text) > MAX_ANSWER_CHARS:
        return None
    try:
        return _exact_number(text)
    except (ValueError, OverflowError, RecursionError, ZeroDivisionError, MemoryError):
        return None


def _exact_number(text: str) -> Optional[Fraction]:
    text = text.replace("$", "").replace("{,}", ",").replace("−", "-")
    text = text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    text = _THIN_SPACE_RE.sub(" ", text).strip()
    m = _MIXED_LATEX_RE.fullmatch(text)
    if m:
        sign, whole, num, den = m.groups()
        if int(den) == 0 or (whole and num.startswith("-")):
            return None
        result = Fraction(int(num), int(den)) + (int(whole) if whole else 0)
        return -result if sign else result
    m = _MIXED_PLAIN_RE.fullmatch(text)
    if m:
        sign, whole, num, den = m.groups()
        if int(den) == 0:
            return None
        result = int(whole) + Fraction(int(num), int(den))
        return -result if sign else result
    m = _FRACTION_RE.fullmatch(text)
    if m:
        return Fraction(int(m.group(1)), int(m.group(2))) if int(m.group(2)) else None
    if _THOUSANDS_RE.fullmatch(text):
        return Fraction(text.replace(" ", ""))
    if _DECIMAL_RE.fullmatch(text):
        return Fraction(text.replace(",", "."))
    return None


def answers_equivalent(first: object, second: object) -> bool:
    """True only when two stored answers are provably the same value.

    Used to recognise one answer written in two notations (`0,22` and
    `\\dfrac{11}{50}`, `$[-4$; $2]$` and `$[-4; 2]$`) among a task's options.
    It is intentionally strict: a false positive would let a wrong option be
    shown as correct, so anything not provably equal counts as different.
    """
    a, b = _notation_key(first), _notation_key(second)
    if not a or not b:
        return False
    if a == b:
        return True
    na, nb = exact_number(first), exact_number(second)
    return na is not None and nb is not None and na == nb

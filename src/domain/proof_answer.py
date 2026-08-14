from __future__ import annotations

import re

_PROOF_PLACEHOLDERS = {
    "Доказательство",
    "Доказательство:",
    "Доказательство: ...",
}

_ALLOWED_LEFT_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "_\\{}()[]^+-*/·×÷.,=<>≤≥√−– "
)

_RELATION_TO_ZERO_RE = re.compile(r"[<>≤≥=]\s*0")


def is_proof_placeholder(value: str | None) -> bool:
    text = (value or "").strip()
    return text in _PROOF_PLACEHOLDERS or text.startswith("Доказательство: ...")


def normalize_math_snippet(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    cleaned = cleaned.replace("−", "-").replace("–", "-")
    cleaned = re.sub(r"\bsqrt\(([^()]+)\)", r"\\sqrt{\1}", cleaned)
    cleaned = re.sub(r"√\(([^()]+)\)", r"\\sqrt{\1}", cleaned)
    cleaned = re.sub(r"√(\d+)", r"\\sqrt{\1}", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*([<>≤≥=])\s*", r" \1 ", cleaned)
    return cleaned.strip(" ,;:.")


def _score_proof_candidate(candidate: str) -> tuple[int, int, int, int, int]:
    return (
        1 if "(" in candidate else 0,
        1 if "_" in candidate else 0,
        1 if "^" in candidate else 0,
        1 if "\\" in candidate or "sqrt" in candidate or "√" in candidate else 0,
        len(candidate),
    )


def extract_proof_expression(question_text: str | None) -> str | None:
    text = re.sub(r"\s+", " ", (question_text or "")).strip()
    if not text:
        return None

    candidates: list[str] = []
    for match in _RELATION_TO_ZERO_RE.finditer(text):
        end = match.end()
        start = match.start()
        i = start - 1
        while i >= 0 and text[i] in _ALLOWED_LEFT_CHARS:
            i -= 1
        candidate = text[i + 1 : end].strip(" ,;:.")
        if not candidate:
            continue
        if re.search(r"[А-Яа-яЁё]", candidate):
            continue
        if len(re.findall(r"[<>≤≥=]", candidate)) != 1:
            continue
        candidates.append(candidate)

    if not candidates:
        return None

    return normalize_math_snippet(max(candidates, key=_score_proof_candidate))


def format_proof_answer(question_text: str | None, fallback: str = "Доказательство: ...") -> str:
    extracted = extract_proof_expression(question_text)
    if extracted:
        return f"${extracted}$"
    return fallback
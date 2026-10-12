"""Claims that a diagnostic report must never make (N03a, owner decision O4).

Three families of statements have no verified basis:

* a class equivalent of the level («конец 7 класса») - checked only on the prose that
  states the level (the caller decides where), because «в конце 7 класса изучают …» is a
  legitimate curriculum reference elsewhere;
* the reliability / credibility of the diagnosis («надёжность диагноза 83%», «Диагноз
  достоверен») - checked everywhere; the probability-theory wording
  («надёжность прибора равна 0,95») is told apart by the sentence subject;
* confirming or NOT confirming a single root cause («Единая первопричина не
  подтверждена»).

The detectors are small token-level grammars, not wide regular expressions: precision
matters (a false positive withholds a legitimate summary or forces the deterministic
fallback) and every scan is linear in the text size (no unbounded quantifiers, words
longer than ``_MAX_WORD`` collapse to a placeholder).  All of them work on text
normalised by ``_normalize_claim_text``: lower case, ё -> е, every dash variant -> «-»,
invisible characters removed.
"""
from __future__ import annotations

import re
from typing import Any, List, Sequence, Set

# ── Class equivalent ──────────────────────────────────────────────────────────

_GRADE_WORDS = r"(?:пят|шест|седьм|восьм|девят|десят|одиннадцат)(?:ого|ой|ом|ый|ому|ым|ая|ое|ую)"
_CLASS_EQUIVALENT_RE = re.compile(
    r"(?<![а-яё])(?:начал[а-яё]{0,6}|середин[а-яё]{0,4}|кон(?:ец|ц[а-яё]{0,4}))\s{1,3}"   # начало / середина / конец
    r"(?:\d{1,2}|" + _GRADE_WORDS + r")"                                                 # 7  |  седьмого
    r"[-\s]{0,3}(?:(?:го|й|м|ом|ого)[-\s]{1,3})?класс",                                  # [-го] класс(а)
    re.IGNORECASE,
)

# ── Normalisation and tokens ──────────────────────────────────────────────────

_DASH_RE = re.compile("[‐‑‒–—―−]")      # ‐ ‑ ‒ – — ― −
_INVISIBLE_RE = re.compile("[­​‌‍⁠﻿]")       # soft hyphen, zero-width
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"\d{1,6}(?:[.,]\d{1,6})?|[a-zа-я]+(?:-[a-zа-я0-9]+){0,5}|[,:;()«»\"%]|-")
_MAX_WORD = 48
_OPEN = frozenset({"«", "(", '"'})
_CLOSE = frozenset({"»", ")", '"'})


def _normalize_claim_text(text: str) -> str:
    """Lower case, ё -> е, every dash variant -> «-», invisible characters removed."""
    text = _DASH_RE.sub("-", _INVISIBLE_RE.sub("", text))
    return text.lower().replace("ё", "е")


def _tokens(sentence: str) -> List[str]:
    """Words (hyphenated words stay whole; «не-X» splits), numbers and the punctuation that matters."""
    out: List[str] = []
    for match in _TOKEN_RE.finditer(sentence):
        token = match.group()
        if len(token) > _MAX_WORD:
            out.append("#")
        elif token.startswith("не-") and len(token) > 3:
            out.extend(("не", token[3:]))
        else:
            out.append(token)
    return out


def _is_word(token: str) -> bool:
    return token[0].isalpha() or token[0] == "#"


def _has_class_equivalent(text: Any) -> bool:
    return isinstance(text, str) and bool(_CLASS_EQUIVALENT_RE.search(_normalize_claim_text(text)))


# ── Root cause ────────────────────────────────────────────────────────────────
# Retired: «Единая первопричина не подтверждена».  The negation must DIRECTLY govern the
# root-cause noun phrase (NP); a bare «причина» is not a root cause.

_RC_HEAD = re.compile(r"перво-?причин[а-я]{0,6}")
_RC_CAUSE = re.compile(r"причин(?:а|ы|е|у|ой|ою|ам|ами|ах)?")
_RC_ADJ = re.compile(
    r"(?:един|общ|главн|основн|корнев)"
    r"(?:ая|ой|ей|ую|ым|им|ые|ие|ых|их|ое|ее|ого|его|ому|ему|ом|ем|ыми|ими)"
)
_RC_ONE = re.compile(r"един(?:ый|ого|ому|ым|ом)")
_RC_ROOT = re.compile(r"корень|корня|корню|корнем|корне")

# finite / participle forms that AFFIRM (when not negated) that something was established
_PASSIVE = re.compile(r"(?:подтвержден|установлен|выявлен|определен|найден|обнаружен|прослежен|выяснен)(?:а|о|ы)?")
_PASSIVE_FEM = re.compile(r"(?:подтвержден|установлен|выявлен|определен|найден|обнаружен|прослежен)а")
_PRESENT_REFL = re.compile(r"(?:подтвержда|устанавлива|выявля|определя|обнаружива|прослежива)(?:ется|ются)")
_PAST_REFL = re.compile(r"(?:подтвердил|установил|выявил|определил|обнаружил|нашл)(?:ась|ись|ось)")
_ACTIVE_PAST = re.compile(r"(?:подтвердил|установил|выявил|определил|обнаружил|прослеживал)[аио]?|нашел|нашл[аио]")
_ACTIVE_PRESENT = re.compile(r"(?:подтвержда|устанавлива|выявля|определя|обнаружива|прослежива)(?:ет|ют)")
_FINITE_FORMS = (_PASSIVE, _PRESENT_REFL, _PAST_REFL, _ACTIVE_PAST, _ACTIVE_PRESENT)
_PREDICATE_FORMS = (_PASSIVE, _PRESENT_REFL, _PAST_REFL)           # «первопричина не <…>»

_AUX = frozenset({"был", "была", "было", "были", "будет", "будут"})
_MODAL = frozenset({
    "удалось", "удается", "удавалось", "получилось", "получается",
    "позволил", "позволила", "позволило", "позволили", "позволяет", "позволяют",
    "может", "могут", "могла", "могло", "мог", "могли", "смог", "смогла", "смогли", "сможет", "смогут",
})
_INFINITIVE = frozenset({"установить", "определить", "подтвердить", "выявить", "найти", "обнаружить", "выделить", "выяснить"})
_IMPOSSIBLE = ("нельзя", "невозможно")
_REMAINED = frozenset({"остался", "осталась", "осталось", "остались", "остается", "остаются", "останется"})
_UNESTABLISHED = re.compile(
    r"(?:неустановлен|невыяснен|неопределен|неподтвержден|невыявлен|необнаружен|ненайден)(?:н?ой|н?ым|н?ыми|н?ые|н?ая|н?ое|н?ую|н?ых)?"
)
_ABSENT = re.compile(r"отсутству[а-я]{1,8}")
_CLAUSE_BREAKERS = frozenset({"а", "но", "однако"})
_MAX_GAP_WORDS = 5          # words between NP and a negated predicate
_MAX_NEAR_WORDS = 3         # words between NP and «нет» / «отсутствует»


def _matches_any(token: str, patterns: Sequence["re.Pattern[str]"]) -> bool:
    return any(p.fullmatch(token) for p in patterns)


def _noun_phrases(tokens: Sequence[str]) -> List[tuple]:
    """(start, end_exclusive, head) of every root-cause noun phrase."""
    found = []
    for i, token in enumerate(tokens):
        if _RC_HEAD.fullmatch(token):
            start = i - 1 if i and _RC_ADJ.fullmatch(tokens[i - 1]) else i
            found.append((start, i + 1, token))
        elif i and _RC_CAUSE.fullmatch(token) and _RC_ADJ.fullmatch(tokens[i - 1]):
            found.append((i - 1, i + 1, token))
        elif i and _RC_ROOT.fullmatch(token) and _RC_ONE.fullmatch(tokens[i - 1]):
            found.append((i - 1, i + 1, token))
    return found


def _np_follows(tokens: Sequence[str], pos: int, starts: Set[int], max_words: int = 2) -> bool:
    """A noun phrase begins within ``max_words`` plain words from ``pos`` (opening quotes are free)."""
    words = 0
    while pos < len(tokens):
        if pos in starts:
            return True
        token = tokens[pos]
        if token in _OPEN:
            pos += 1
            continue
        if not _is_word(token):
            return False
        words += 1
        if words > max_words:
            return False
        pos += 1
    return False


def _negated_before(tokens: Sequence[str], idx: int) -> bool:
    """The form at ``idx`` stands under «не» / «нельзя» (optionally via «был»)."""
    if idx >= 1 and tokens[idx - 1] in ("не", "нельзя"):
        return True
    return idx >= 2 and tokens[idx - 1] in _AUX and tokens[idx - 2] == "не"


def _affirmed_before(tokens: Sequence[str], start: int) -> bool:
    """NP is the object of an un-negated «подтвердила / установлена …» within three words before it."""
    seen = 0
    pos = start - 1
    while pos >= 0 and seen < 3:
        token = tokens[pos]
        if token in _OPEN:
            pos -= 1
            continue
        if not _is_word(token):
            return False
        if _matches_any(token, _FINITE_FORMS) and not _negated_before(tokens, pos):
            return True
        seen += 1
        pos -= 1
    return False


def _negated_predicate_at(tokens: Sequence[str], i: int) -> bool:
    """«не <предикат>» / «нельзя установить» / «<причастие> не была» starting at token ``i``."""
    n = len(tokens)
    token = tokens[i]
    if token == "не":
        j = i + 1
        if j < n and tokens[j] in _AUX:
            j += 1
        if j >= n:
            return False
        if _matches_any(tokens[j], _PREDICATE_FORMS):
            return True
        if tokens[j] in ("удалось", "удается", "удавалось", "получилось", "получается"):
            return True
        if tokens[j] in _MODAL and j + 2 < n and tokens[j + 1] == "быть" and _PASSIVE.fullmatch(tokens[j + 2]):
            return True
        return False
    if token in _IMPOSSIBLE:
        if i + 1 < n and tokens[i + 1] in _INFINITIVE:
            return True                                        # «первопричину нельзя / невозможно установить»
        return token == "невозможно" and i >= 1 and tokens[i - 1] in _INFINITIVE    # «… подтвердить невозможно»
    if token in _REMAINED:
        return i + 1 < n and _UNESTABLISHED.fullmatch(tokens[i + 1]) is not None   # «осталась неустановленной»
    # «первопричина выявлена не была»
    return bool(
        _PASSIVE.fullmatch(token) and i + 2 < n and tokens[i + 1] == "не" and tokens[i + 2] in _AUX
    )


def _claim_negation_before(tokens: Sequence[str], starts: Set[int]) -> bool:
    """A: «не подтвердила (наличие) единую первопричину», «не позволила установить первопричину»."""
    n = len(tokens)
    for i, token in enumerate(tokens):
        if token != "не" and token not in _IMPOSSIBLE:
            continue
        j = i + 1
        if token == "не" and j < n and tokens[j] in _AUX:
            j += 1
        if j >= n:
            continue
        if token == "не" and _matches_any(tokens[j], _FINITE_FORMS):
            end = j + 1
        elif token == "не" and tokens[j] in _MODAL and j + 1 < n and tokens[j + 1] in _INFINITIVE:
            end = j + 2
        elif token in _IMPOSSIBLE and tokens[j] in _INFINITIVE:
            end = j + 1
        else:
            continue
        if _np_follows(tokens, end, starts):
            return True
    return False


def _infinitive_before(tokens: Sequence[str], start: int) -> bool:
    """An infinitive of «установить / подтвердить …» stands within two words before the noun phrase."""
    seen = 0
    pos = start - 1
    while pos >= 0 and seen < 3:
        token = tokens[pos]
        if token in _OPEN:
            pos -= 1
            continue
        if not _is_word(token):
            return False
        if token in _INFINITIVE:
            return True
        seen += 1
        pos -= 1
    return False


def _claim_negation_after(tokens: Sequence[str], nps: Sequence[tuple]) -> bool:
    """B: «Единая первопричина не подтверждена», «Первопричину установить не удалось», «… нет»."""
    n = len(tokens)
    for start, end, head in nps:
        if _affirmed_before(tokens, start):
            continue
        i = end
        while i < n and tokens[i] in _CLOSE:
            i += 1
        # a dash directly after the subject: only «первопричина - не подтверждена»
        if i < n and tokens[i] == "-":
            if (
                i == end and _RC_HEAD.fullmatch(head) and head.endswith("а")
                and i + 2 < n and tokens[i + 1] == "не" and _PASSIVE_FEM.fullmatch(tokens[i + 2])
            ):
                return True
            continue
        words = 0
        while i < n:
            token = tokens[i]
            if token == ",":
                nxt = tokens[i + 1] if i + 1 < n else ""
                if nxt in _CLAUSE_BREAKERS or (nxt == "при" and i + 2 < n and tokens[i + 2] == "этом"):
                    break
                i += 1
                continue
            if not _is_word(token):
                break                                          # : ; ( ) « » - % and numbers
            if _negated_predicate_at(tokens, i):
                return True
            if token in _IMPOSSIBLE and _infinitive_before(tokens, start):
                return True                                    # «Подтвердить единую первопричину невозможно»
            if words <= _MAX_NEAR_WORDS and (token == "нет" or _ABSENT.fullmatch(token)):
                return True
            if _matches_any(token, _FINITE_FORMS):
                break                                          # «Первопричина подтверждена, … не выявлены»
            words += 1
            if words > _MAX_GAP_WORDS:
                break
            i += 1
    return False


def _claim_no_np(tokens: Sequence[str], starts: Set[int]) -> bool:
    """C: «нет единой первопричины», «отсутствует единая первопричина»."""
    for i, token in enumerate(tokens):
        if token == "нет" or _ABSENT.fullmatch(token):
            if _np_follows(tokens, i + 1, starts):
                return True
    return False


def _has_root_cause_claim(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    normalized = _normalize_claim_text(text)
    if "причин" not in normalized and "корен" not in normalized and "корн" not in normalized:
        return False
    for line in normalized.split("\n"):
        for sentence in _SENTENCE_RE.split(line):
            tokens = _tokens(sentence)
            nps = _noun_phrases(tokens)
            if not nps:
                continue
            starts = {start for start, _end, _head in nps}
            if (
                _claim_negation_before(tokens, starts)
                or _claim_negation_after(tokens, nps)
                or _claim_no_np(tokens, starts)
            ):
                return True
    return False


# ── Reliability / credibility of the diagnosis ────────────────────────────────

_REL_NOUN = re.compile(r"(?:не)?(?:надежност|достоверност)(?:ь|и|ью|ей)?")
_REL_ADJ = re.compile(
    r"(?:не)?(?:достовер|надеж)(?:ен|н(?:а|ы|ый|ая|ые|ое|ого|ой|ому|ым|ом|ую|ых|ыми))"
)
# «точность» / «уверенность» are claims only when the subject is the diagnosis («Точность диагностики 87%»);
# «с точностью до 0,01», «уверенно решает», «точность измерения прибора» are ordinary mathematics.
_SOFT_NOUN = re.compile(r"(?:точност|уверенност)(?:ь|и|ью)")
_NUMBER = re.compile(r"\d{1,6}(?:[.,]\d{1,6})?")
_PROBABILITY = re.compile(r"[01][.,]\d{1,6}")
_PERCENT_WORD = re.compile(r"процент[а-я]{0,4}")

# the subject of the claim: the diagnosis / report itself ...
_SUBJECT = re.compile(
    r"(?:диагноз|диагностик|тест|тестирован|отчет|заключен)(?:а|ы|у|е|и|ом|ой|ию|ие|ия|ии|ов|ам|ами|ах|ем)?"
    r"|(?:диагностическ|оценочн)(?:ий|ая|ое|ие|ого|ой|ому|им|ом|ую|их|ими|ые)"
)
# ... or an assessment / method / conclusion / measurement that is itself about the diagnosis
# («метод диагностики», «оценка уровня»); «метод подстановки» and «достоверность корня» are not.
_CONDITIONAL_SUBJECT = re.compile(
    r"(?:оценк|измерен|метод|методик|вывод)(?:а|ы|у|е|и|ом|ой|ию|ие|ия|ии|ов|ам|ами|ах|ем)?"
)
_DIAGNOSIS_STRONG = re.compile(
    r"(?:диагноз|диагностик|отчет)(?:а|ы|у|е|и|ом|ой|ию|ие|ия|ии|ов|ам|ами|ах|ем)?"
)
_DIAGNOSIS_WEAK = re.compile(
    r"(?:тест|тестирован|заключен)(?:а|ы|у|е|и|ом|ой|ию|ие|ия|ии|ов|ам|ами|ах|ем)?"
)
_LEVEL_OBJECT = frozenset({"уровня", "знаний", "ученика", "подготовки"})
_RESULT = re.compile(r"результат(?:а|ы|у|е|ом|ов|ам|ами|ах)?")
_EVALUATE = re.compile(
    r"счита(?:ть|ется|ются|ем|йте)|являет(?:ся)|являются|признан(?:ы|а|о)?|призна(?:ть|ются)|оценива(?:ется|ются)"
)

# technical objects of probability tasks (whole words only: «автоматическое», «систематически»,
# «элементарные» are NOT technical objects)
_TECH_ENDINGS = r"(?:|а|о|ы|у|е|и|я|ю|ь|ов|ев|ей|ом|ем|ой|ою|ам|ям|ах|ях|ами|ями)"
_TECH = re.compile(
    r"(?:прибор|систем|элемент|устройств|узл|ламп|лампочк|схем|детал|механизм|блок|цеп|сет|датчик"
    r"|двигател|станк|автомат|компонент|агрегат|канал|аппарат|предохранител|процессор|аккумулятор"
    r"|лифт|насос|самолет)" + _TECH_ENDINGS
    + r"|узел|станок|реле|издели(?:е|я|ю|ем|й)|оборудован(?:ие|ия|ию|ием)|батаре(?:я|и|й|ю|ей)"
)
_WINDOW_FIGURE = 8          # tokens after the reliability noun searched for a figure


def _tech_follows(tokens: Sequence[str], i: int) -> bool:
    """«надёжность <прибора / работы лампы …>»: a technical object within two words after the noun."""
    return any(
        j < len(tokens) and _TECH.fullmatch(tokens[j]) for j in (i + 1, i + 2)
    )


def _subject_at(tokens: Sequence[str], j: int) -> bool:
    token = tokens[j]
    if _SUBJECT.fullmatch(token):
        return True
    if _CONDITIONAL_SUBJECT.fullmatch(token) and j + 1 < len(tokens):
        nxt = tokens[j + 1]
        return bool(
            _SUBJECT.fullmatch(nxt) or nxt in _LEVEL_OBJECT
            if token.startswith("оценк") else _SUBJECT.fullmatch(nxt)
        )
    return False


def _subject_after(tokens: Sequence[str], i: int, max_words: int = 3) -> bool:
    for j in range(i + 1, min(len(tokens), i + 1 + max_words)):
        token = tokens[j]
        if not (_is_word(token) or _NUMBER.fullmatch(token)):
            return False
        if _subject_at(tokens, j):
            return True
    return False


def _diagnostic_subject_after(tokens: Sequence[str], i: int, max_words: int = 4) -> bool:
    """«Точность диагностики», «Точность оценки уровня», «Уверенность в результатах теста 85%».

    ``тест`` / ``тестирование`` / ``заключение`` alone are everyday words («уверенность при решении
    тестов»): they count with a figure after the noun or a preceding «результат…».
    """
    saw_result = False
    for j in range(i + 1, min(len(tokens), i + 1 + max_words)):
        token = tokens[j]
        if not (_is_word(token) or _NUMBER.fullmatch(token)):
            return False
        if _DIAGNOSIS_STRONG.fullmatch(token):
            return True
        if token.startswith("оценк") and j + 1 < len(tokens) and tokens[j + 1] in _LEVEL_OBJECT:
            return True
        if _RESULT.fullmatch(token):
            saw_result = True
        elif _DIAGNOSIS_WEAK.fullmatch(token) and (saw_result or _figure_after(tokens, i, limit=4)):
            return True
    return False


def _subject_before(tokens: Sequence[str], i: int, max_between: int = 3) -> bool:
    for j in range(i - 1, max(-1, i - 2 - max_between), -1):
        token = tokens[j]
        if not (_is_word(token) or _NUMBER.fullmatch(token)):
            return False
        if _subject_at(tokens, j):
            return True
    return False


def _is_figure(tokens: Sequence[str], j: int) -> bool:
    token = tokens[j]
    if not _NUMBER.fullmatch(token):
        return False
    if _PROBABILITY.fullmatch(token):
        return True
    return j + 1 < len(tokens) and (tokens[j + 1] == "%" or bool(_PERCENT_WORD.fullmatch(tokens[j + 1])))


def _figure_after(tokens: Sequence[str], i: int, limit: int = _WINDOW_FIGURE) -> bool:
    return any(_is_figure(tokens, j) for j in range(i + 1, min(len(tokens), i + 1 + limit)))


def _figure_before(tokens: Sequence[str], i: int) -> bool:
    for j in range(i - 1, max(-1, i - 5), -1):
        token = tokens[j]
        if token in (",", ";", ":", "(", ")"):
            return False
        if (token == "%" or _PERCENT_WORD.fullmatch(token)) and j >= 1 and _NUMBER.fullmatch(tokens[j - 1]):
            return True
    return False


_WORKS = frozenset({"работает", "работают", "функционирует", "функционируют", "срабатывает", "откажет"})


def _technical_object_works(tokens: Sequence[str], i: int) -> bool:
    """«Прибор работает с 95% надёжностью»: exactly <object> <works> с <N>% <надёжность>."""
    return (
        i >= 5 and tokens[i - 1] == "%" and _NUMBER.fullmatch(tokens[i - 2]) is not None
        and tokens[i - 3] == "с" and tokens[i - 4] in _WORKS and _TECH.fullmatch(tokens[i - 5]) is not None
    )


def _result_judged_before(tokens: Sequence[str], i: int) -> bool:
    """«Результаты можно считать надёжными»: «результат…» + an evaluating verb just before the adjective."""
    verb = None
    for j in range(i - 1, max(-1, i - 5), -1):
        token = tokens[j]
        if not _is_word(token):
            return False
        if verb is None:
            if _EVALUATE.fullmatch(token):
                verb = j
        elif _RESULT.fullmatch(token):
            return True
    return False


def _event_nearby(tokens: Sequence[str], i: int, first_diag: int) -> bool:
    """«Достоверное событие» / «событие достоверно» is the probability term, not a claim.

    Never when a result / diagnostic subject precedes the adjective in the sentence
    («Результат по теме «Случайные события» надёжен на 85%», «Диагноз достоверен, событие не влияет»);
    ``first_diag`` is the index of the first such token (-1 when there is none).
    """
    if 0 <= first_diag < i:
        return False
    return any(re.fullmatch(r"событ[а-я]{1,4}", t) for t in tokens[max(0, i - 3):i + 4])


def _reliability_in_sentence(tokens: Sequence[str]) -> bool:
    # computed once per sentence: scanning tokens[:i] for every adjective would be quadratic
    first_result = next((k for k, t in enumerate(tokens) if _RESULT.fullmatch(t)), -1)
    first_subject = next((k for k, t in enumerate(tokens) if _SUBJECT.fullmatch(t)), -1)
    first_diag = min((k for k in (first_result, first_subject) if k >= 0), default=-1)
    for i, token in enumerate(tokens):
        if _REL_NOUN.fullmatch(token):
            if _subject_after(tokens, i):                      # «надёжность результатов диагностики»
                return True
            if _tech_follows(tokens, i) or _technical_object_works(tokens, i):    # «надёжность прибора равна 0,95»
                continue
            if _subject_before(tokens, i):                     # «Диагноз поставлен с высокой достоверностью»
                return True
            if _figure_after(tokens, i) or _figure_before(tokens, i):        # «надёжность 83%», «83% надёжности»
                return True
        elif _REL_ADJ.fullmatch(token):
            if _event_nearby(tokens, i, first_diag):           # «вероятность достоверного события равна 100%»
                continue
            if _subject_before(tokens, i):                     # «Диагноз достоверен»
                return True
            if _result_judged_before(tokens, i):               # «Результаты можно считать надёжными»
                return True
            tech_subject = i >= 1 and _TECH.fullmatch(tokens[i - 1])
            credibility = token.startswith(("достовер", "недостовер"))
            if _figure_after(tokens, i, limit=4) and not tech_subject and (
                not credibility or 0 <= first_result < i
            ):                                                 # «Результат достоверен на 90%»
                return True
        elif _SOFT_NOUN.fullmatch(token) and _diagnostic_subject_after(tokens, i):
            return True                                        # «Точность диагностики — 87%», «Уверенность в диагностике 85%»
    return False


def _has_reliability_claim(text: Any) -> bool:
    """Reliability / credibility of the diagnosis as a statement or a figure (not probability tasks)."""
    if not isinstance(text, str):
        return False
    normalized = _normalize_claim_text(text).replace("\n", " ")
    if not any(stem in normalized for stem in ("надеж", "достовер", "уверенност", "точност")):
        return False
    return any(_reliability_in_sentence(_tokens(s)) for s in _SENTENCE_RE.split(normalized))


# ── Public API ────────────────────────────────────────────────────────────────

def contains_retired_claim(text: Any) -> bool:
    """True when prose states a class equivalent, a reliability claim or a root-cause (non-)confirmation (O4)."""
    return _has_class_equivalent(text) or _has_reliability_claim(text) or _has_root_cause_claim(text)


_SEGMENT_RE = re.compile(r"((?<=[.!?])\s+|\n+)")
_SENTENCE_ONLY_RE = re.compile(r"((?<=[.!?])\s+)")


# the figure of a claim that wrapped onto the next line: «— 83%», «83%», «- 0,83» (a bullet «- Решите» is not)
_LIST_MARKER_RE = re.compile(r"\s*\d{1,2}[.)]")
_DASH_CLASS = "[-\u2010-\u2015\u2212]"
# Matched against ``segment.strip()``: no leading/trailing ``\s*`` (two adjacent
# ``\s*`` around ``[.;]?`` backtrack quadratically on a long whitespace run).
_CONTINUATION_RE = re.compile(
    r"(?:" + _DASH_CLASS + r"\s*)?"
    r"(?:\d{1,3}(?:[.,]\d+)?\s*(?:%|процент[а-я]{0,4})|[01][.,]\d+)\s*[.;]?"
)


def _drop_flagged_segments(text: str, splitter: "re.Pattern[str]") -> str:
    parts = splitter.split(text)                       # segment, separator, segment, ...
    segments, separators = parts[0::2], parts[1::2] + [""]
    merged: List[tuple] = []                           # a bare list marker («1.») belongs to its line
    k = 0
    while k < len(segments):
        segment, separator = segments[k], separators[k]
        while _LIST_MARKER_RE.fullmatch(segment) and k + 1 < len(segments):
            k += 1
            segment, separator = segment + separator + segments[k], separators[k]
        merged.append((segment, separator))
        k += 1
    segments, separators = [m[0] for m in merged], [m[1] for m in merged]
    kept: List[str] = []
    dropped = False
    previous_open = False                              # the previous segment was dropped without a closing .!?
    for segment, separator in zip(segments, separators):
        flagged = _has_reliability_claim(segment) or _has_root_cause_claim(segment)
        continuation = previous_open and _CONTINUATION_RE.fullmatch(segment.strip()) is not None
        if flagged or continuation:                    # «Надёжность диагноза\n— 83%.» goes as a whole
            dropped = True
            previous_open = flagged and not segment.rstrip().endswith((".", "!", "?"))
            continue
        previous_open = False
        kept.append(segment + separator)
    return "".join(kept).rstrip() if dropped else text


def drop_retired_sentences(text: Any) -> Any:
    """Plan prose without the sentences / lines that make a reliability or root-cause claim.

    Sentences and lines (bullets) are cut separately and re-joined with their original
    separators, so one hit removes only its own line.  A claim that wraps over a line break is
    caught by a second, sentence-only pass.  A class equivalent is NOT swept here: in the plan
    «в конце 7 класса изучают …» is a curriculum reference.  Clean text is returned unchanged.
    """
    if not isinstance(text, str):
        return text
    if not (_has_reliability_claim(text) or _has_root_cause_claim(text)):
        return text
    cleaned = _drop_flagged_segments(text, _SEGMENT_RE)
    if _has_reliability_claim(cleaned) or _has_root_cause_claim(cleaned):
        cleaned = _drop_flagged_segments(cleaned, _SENTENCE_ONLY_RE)
    return cleaned

"""Deterministic runs of the three binary-search navigators; the dict of ``to_dict()`` after every step is what
``tests/fixtures/navigators_to_dict_golden.json`` stores (it is also what the sessions keep as JSON: wave E7 / DU-01)."""
from __future__ import annotations

from src.domain.navigators.skill_navigator import SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator
from src.domain.navigators.topic_navigator import TopicEntry, TopicNavigator

SIZES = (0, 1, 2, 3, 5, 8)
# every answer sequence of length <= 3 plus two long ones: the run stops when the navigator is exhausted
SEQUENCES = ((True,), (False,), (True, False), (False, True), (True, True, True), (False, False, False), (True, False, True, False, True))


def make(kind: str, n: int):
    """``n`` entries given in a scrambled order (the navigator sorts them by position / difficulty)."""
    order = [(i * 3) % n for i in range(n)] if n and n % 3 else list(reversed(range(n)))
    if kind == "topic":
        return TopicNavigator.create("G9_SEC", [TopicEntry(f"G9_T{i}", "G9_SEC", i, 5 + i % 3, f"Тема {i}") for i in order])
    if kind == "subtopic":
        return SubtopicNavigator.create("G9_T1", 7, [SubtopicEntry(f"G9_T1_S{i}", "G9_T1", i, 4 + i % 4, f"Подтема {i}") for i in order])
    return SkillNavigator.create("G9_T1_S1", [SkillEntry(f"G9_T1_S1_K{i}", "G9_T1_S1", i, round(-1.5 + i * 0.4, 2), f"Навык {i}") for i in order])


def run(kind: str, n: int, sequence) -> list:
    nav = make(kind, n)
    steps = [nav.to_dict()]
    for answer in sequence:
        if nav.state.exhausted or nav.peek_current() is None:
            break
        if kind == "subtopic":
            nav.record_score(0.8 if answer else 0.2)
        nav.move(answer)
        steps.append(nav.to_dict())
    return steps


def all_runs() -> dict:
    return {f"{kind}-{n}-{''.join('Y' if a else 'N' for a in seq)}": run(kind, n, seq)
            for kind in ("topic", "subtopic", "skill") for n in SIZES for seq in SEQUENCES}

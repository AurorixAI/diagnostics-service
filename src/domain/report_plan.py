"""N03b-2: the content of a diagnostic report that is built from the attempt's own data - no model is involved here.

What a teacher reads is made of facts of ONE attempt:

* the error journal (``error_patterns``) numbers its rows (``journal_no``) and marks the answers of tasks that were taken
  out of the bank after the attempt (``task_withdrawn``);
* the map of checked topics counts, per topic, the measured tasks and the wrong ones - by the ONE rule of the header
  (``level_policy.count_solved``: Deep Scan probes are not measured tasks and are never mixed in);
* a plan step is built from a skill with errors: the BASIS (journal rows of this attempt), the GOAL (the skill), the MATERIAL
  (up to three active tasks of the skill from the bank) and the CHECK (one more active task of the skill that the student did
  not get in this attempt - or "a task of this skill at the lesson" when the bank has none);
* the skills with errors that did not fit into the five steps are listed as "more difficulties".

The model only rewords the title and the description of a step (``report_generator``); it never touches the lines above.

ORDER OF THE PLAN (Б3).  By facts of the attempt, never by a percentage: (1) the number of wrong answers of the skill, more first;
(2) the prerequisite relation: of equal skills the root of a Deep Scan chain goes first (a stored-link root before a reconstructed
one), and a root is always placed before the skill it was found under; (3) ONLY on a full tie of the facts above, the lower
hidden mastery estimate (alpha) of the topic goes first - it decides nothing else and is never shown; (4) the skill id, so
that the same data always gives the same plan.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .level_policy import is_correct

log = logging.getLogger(__name__)

PLAN_STEPS_MAX = 5          # steps of the plan (the rest goes to "more difficulties")
EVIDENCE_MAX = 5            # journal rows quoted as the basis of one step
MATERIAL_MAX = 3            # bank tasks offered as material of one step
TASK_WINDOW = 50            # active tasks of a skill read from the bank to choose from
DEVELOPMENT_WINDOW = 200    # the development step wants the hardest tasks: the whole skill (the bank API allows 200)

# All reads of the bank for ONE report together (the first read starts the clock).  Well below report_jobs.STALE_GENERATING_AFTER (10 min):
# a hanging content-service must not keep a worker busy until another worker takes the job.  A read that is slow but answers is
# allowed to finish; the NEXT read is refused once the budget is spent.
BANK_BUDGET_S = 60.0

NO_TOPIC = "Без темы"
CHECK_STATEMENT = "Ученик решает без ошибки задание этого навыка из банка"
ON_LESSON = "задание этого навыка на занятии"

# Evidence codes of a step (``evidence_kind``).  Which fact put the skill into the plan - not a verdict.
KIND_CONFIRMED_PREREQUISITE = "confirmed_prerequisite"   # root of a Deep Scan chain backed by the stored link
KIND_OBSERVED_PREREQUISITE = "observed_prerequisite"     # root of a chain reconstructed from the order of the answers
KIND_OBSERVED_ERROR = "observed_error"                   # wrong answers on the skill
KIND_DEVELOPMENT = "error_free_development"              # no errors in the attempt


# ── The bank (the only place of this module that talks to content-service) ────

def bank_task_is_active(task_id: str) -> bool:
    """False when the task is inactive or gone from the bank (404); a transport failure raises."""
    from src.repositories.knowledge_repo import TaskRepository

    task = TaskRepository().get_by_id(task_id)
    return task is not None and getattr(task, "is_active", True) is not False


def bank_unused_tasks(skill_id: str, exclude_ids: Sequence[str], *, hardest_first: bool = False) -> List[Dict[str, Any]]:
    """Active tasks of the skill that are not in ``exclude_ids``, in a fixed order (by difficulty, then id).

    content-service returns active tasks only; ``is_active`` is checked again here so that a link never leads to an inactive task.
    """
    from src.repositories.knowledge_repo import TaskRepository

    rows = TaskRepository().get_tasks_for_skill(
        skill_id, exclude_ids=list(exclude_ids) or None,
        limit=DEVELOPMENT_WINDOW if hardest_first else TASK_WINDOW,
    )
    excluded = set(exclude_ids)
    tasks: List[Dict[str, Any]] = []
    for row in rows:
        task_id = str(getattr(row, "task_id", None) or getattr(row, "id", None) or "")
        if not task_id or task_id in excluded or getattr(row, "is_active", True) is False:
            continue
        tasks.append({
            "task_id": task_id,
            "question_text": (getattr(row, "question_text", None) or "").strip() or None,
            "question_latex": (getattr(row, "question_latex", None) or "").strip() or None,
            "irt_difficulty": float(getattr(row, "irt_difficulty", 0) or 0),
        })
    sign = -1 if hardest_first else 1
    tasks.sort(key=lambda t: (sign * t["irt_difficulty"], t["task_id"]))
    return tasks


def _now() -> float:
    return time.monotonic()


class BankReader:
    """The reads of the bank for one report: a time budget, a stop after the FIRST failure, a cache of identical reads.

    After a transport failure (or a timeout, or the spent budget) NO other read is made: ``failure`` says why, every answer is ``None``
    ("unknown"), and the caller marks the report degraded and builds no material / check - an unread bank is not an empty one.
    ``is_active`` / ``unused`` replace the real reads in tests; by default the module functions are looked up at call time.
    """

    def __init__(
        self,
        *,
        budget_s: float = BANK_BUDGET_S,
        is_active: Optional[Callable[[str], bool]] = None,
        unused: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    ) -> None:
        self.budget_s = budget_s
        self.failure: Optional[str] = None           # "unreachable" | "budget"
        self.reads = 0                               # reads that reached the bank
        self._is_active, self._unused = is_active, unused
        self._started: Optional[float] = None
        self._status: Dict[str, bool] = {}
        self._tasks: Dict[Tuple[str, Tuple[str, ...], bool], List[Dict[str, Any]]] = {}

    def _may_read(self) -> bool:
        if self.failure:
            return False
        now = _now()
        if self._started is None:
            self._started = now
        elif now - self._started >= self.budget_s:
            self.failure = "budget"
            log.warning("The bank budget of %.0f s for one report is spent after %d reads: no more reads", self.budget_s, self.reads)
            return False
        return True

    def _fail(self, what: str, exc: Exception) -> None:
        self.failure = "unreachable"
        log.warning("Could not read %s in the bank: %s - no more reads for this report", what, exc)

    def task_is_active(self, task_id: str) -> Optional[bool]:
        """True / False (inactive or gone), ``None`` when it could not be read."""
        if task_id in self._status:
            return self._status[task_id]
        if not self._may_read():
            return None
        self.reads += 1
        try:
            value = bool((self._is_active or bank_task_is_active)(task_id))
        except Exception as exc:
            self._fail(f"the state of task {task_id}", exc)
            return None
        self._status[task_id] = value
        return value

    def unused_tasks(self, skill_id: str, exclude_ids: Sequence[str], *, hardest_first: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Free tasks of the skill, ``None`` when they could not be read."""
        key = (skill_id, tuple(sorted(exclude_ids)), hardest_first)
        if key in self._tasks:
            return self._tasks[key]
        if not self._may_read():
            return None
        self.reads += 1
        try:
            tasks = (self._unused or bank_unused_tasks)(skill_id, list(exclude_ids), hardest_first=hardest_first)
        except Exception as exc:
            self._fail(f"the tasks of skill {skill_id}", exc)
            return None
        self._tasks[key] = tasks
        return tasks


def find_withdrawn_tasks(task_ids: Iterable[str], reader: Optional[BankReader] = None) -> Tuple[Set[str], List[str]]:
    """({tasks no longer active in the bank}, [tasks whose state could not be read]).

    Unknown is not "withdrawn": it goes to the second list and the report is marked degraded by the caller.  The reader stops after the first failure,
    so the rest of the tasks are unread, not asked.
    """
    reader = reader or BankReader()
    withdrawn: Set[str] = set()
    unread: List[str] = []
    for task_id in dict.fromkeys(t for t in task_ids if t):
        state = reader.task_is_active(task_id)
        if state is None:
            unread.append(task_id)
        elif not state:
            withdrawn.add(task_id)
    return withdrawn, unread


# ── The journal ───────────────────────────────────────────────────────────────

def number_journal(
    patterns: List[Dict[str, Any]],
    answers_by_id: Dict[str, Any],
    withdrawn: Set[str],
    skill_map: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Journal rows get their 1-based number, the Deep Scan flag, the topic and the "task withdrawn" mark (in place; returns the list)."""
    for number, pattern in enumerate(patterns, 1):
        answer = answers_by_id.get(pattern.get("answer_id"))
        topic_id = getattr(answer, "topic_id", None)
        pattern["journal_no"] = number
        pattern["is_deep_scan"] = bool(getattr(answer, "is_deep_scan", False))
        pattern["topic_id"] = topic_id
        pattern["topic_name_ru"] = skill_map.get(topic_id, {}).get("name_ru") or topic_id if topic_id else None
        pattern["task_withdrawn"] = pattern.get("task_id") in withdrawn
    return patterns


def _live_errors(journal: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Journal rows that may serve as a basis: a task taken out of the bank is not a basis of anything."""
    return [p for p in journal if not p.get("task_withdrawn")]


# ── Checked topics (R14) ──────────────────────────────────────────────────────

def build_checked_topics(answers: Sequence[Any], skill_map: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    """Per topic of the attempt: how many measured tasks were checked and how many of them were answered wrongly.

    ONE rule with the header of the level (``count_solved``): measured tasks only, Deep Scan probes are not counted here
    (they are a separate check of earlier skills, see ``report_meta.prerequisite_*``).  No percent, no verdict.  The sums of the map
    are the numbers of the header: ``sum(checked) == total_questions``, ``sum(errors) == total_questions - questions_correct``.
    """
    order: List[str] = []
    counts: Dict[str, List[int]] = {}
    for answer in answers:
        if bool(getattr(answer, "is_deep_scan", False)):
            continue
        # an answer without a topic still counts (one count with the header): it goes to the bucket "Без темы", never silently dropped
        topic_id = getattr(answer, "topic_id", None) or getattr(answer, "skill_id", None) or ""
        if topic_id not in counts:
            order.append(topic_id)
            counts[topic_id] = [0, 0]
        counts[topic_id][0] += 1
        if not is_correct(getattr(answer, "outcome", None)):
            counts[topic_id][1] += 1
    return [
        {
            "topic_id": topic_id or None,
            "topic_name_ru": (skill_map.get(topic_id, {}).get("name_ru") or topic_id) if topic_id else NO_TOPIC,
            "checked": counts[topic_id][0],
            "errors": counts[topic_id][1],
        }
        for topic_id in order
    ]


# ── Candidates of the plan ────────────────────────────────────────────────────

def _evidence_ref(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """A reference to one journal row: enough to read the basis without opening the journal, the row itself has the rest."""
    return {
        "journal_no": pattern["journal_no"],
        "answer_id": pattern.get("answer_id"),
        "task_id": pattern.get("task_id"),
        "student_answer": pattern.get("student_answer"),
        "explanation": pattern.get("distractor_explanation"),
        "is_deep_scan": bool(pattern.get("is_deep_scan")),
    }


def _prerequisite_ranks(chains: List[Dict[str, Any]]) -> Dict[str, int]:
    """{skill_id: 0 stored-link root | 1 reconstructed root} for the roots of Deep Scan chains that found a prerequisite gap."""
    ranks: Dict[str, int] = {}
    for chain in chains:
        root = chain.get("root_gap_skill_id")
        if not root or not chain.get("has_prerequisite_gap", True) or root == chain.get("source_skill_id"):
            continue
        rank = 1 if chain.get("evidence_source") == "inferred" else 0
        ranks[root] = min(rank, ranks.get(root, rank))
    return ranks


def build_plan_candidates(
    journal: List[Dict[str, Any]],
    chains: List[Dict[str, Any]],
    topic_breakdown: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """ALL skills with at least one live wrong answer, in plan order (see the module docstring).  The caller cuts the first five.

    Each item: ``skill_id``, ``skill_name_ru``, ``topic_id``, ``topic_name_ru``, ``errors`` (number of live wrong answers),
    ``rows`` (those journal rows), ``evidence_kind``, ``prerequisite_of`` (the skill a Deep Scan chain started from, when the
    skill is the root of a gap found under it).
    """
    by_skill: Dict[str, Dict[str, Any]] = {}
    for row in _live_errors(journal):
        skill_id = row.get("skill_id")
        if not skill_id:
            continue
        item = by_skill.setdefault(skill_id, {
            "skill_id": skill_id,
            "skill_name_ru": row.get("skill_name_ru") or skill_id,
            "topic_id": row.get("topic_id"),
            "topic_name_ru": row.get("topic_name_ru"),
            "rows": [],
        })
        item["rows"].append(row)
    ranks = _prerequisite_ranks(chains)
    source_of: Dict[str, str] = {}
    for chain in chains:
        root, source = chain.get("root_gap_skill_id"), chain.get("source_skill_id")
        if root in ranks and source and source != root:
            source_of.setdefault(root, source)

    def alpha(item: Dict[str, Any]) -> float:
        try:
            return float((topic_breakdown.get(item["topic_id"]) or {}).get("alpha", 0.0))
        except (TypeError, ValueError):
            return 0.0

    for item in by_skill.values():
        item["errors"] = len(item["rows"])
        rank = ranks.get(item["skill_id"])
        item["evidence_kind"] = (
            KIND_OBSERVED_ERROR if rank is None
            else KIND_CONFIRMED_PREREQUISITE if rank == 0 else KIND_OBSERVED_PREREQUISITE
        )
        if item["skill_id"] in source_of:
            item["prerequisite_of"] = source_of[item["skill_id"]]

    # (1) wrong answers, (2) prerequisite root, (3) alpha ONLY on a tie of the facts, (4) id
    ordered = sorted(
        by_skill.values(),
        key=lambda i: (-i["errors"], ranks.get(i["skill_id"], 2), alpha(i), i["skill_id"]),
    )
    # a prerequisite is worked before the skill it was found under
    for item in list(ordered):
        source = item.get("prerequisite_of")
        if not source:
            continue
        names = [i["skill_id"] for i in ordered]
        if source in names and names.index(item["skill_id"]) > names.index(source):
            ordered.remove(item)
            ordered.insert(names.index(source), item)
    return ordered


# ── Steps ─────────────────────────────────────────────────────────────────────

def _numbers_text(rows: List[Dict[str, Any]]) -> str:
    return ", ".join(f"№{r['journal_no']}" for r in rows)


def _errors_word(count: int) -> str:
    last_two, last = count % 100, count % 10
    if last == 1 and last_two != 11:
        return "неверный ответ"
    if last in (2, 3, 4) and not 12 <= last_two <= 14:
        return "неверных ответа"
    return "неверных ответов"


def deterministic_description(item: Dict[str, Any], names: Dict[str, str], *, first: bool = False) -> str:
    """The wording of a correction step built from the facts of the skill: it differs from skill to skill.

    «с него следует начать» is said of the FIRST step only (it is where the plan starts); a prerequisite further down is just one.
    """
    name = item["skill_name_ru"]
    rows = item["rows"]
    parts = [f"В диагностике по навыку «{name}» зафиксировано {item['errors']} {_errors_word(item['errors'])} (журнал: {_numbers_text(rows)})."]
    explained = [r for r in rows if r.get("distractor_explanation")]
    if explained:
        row = explained[0]
        explanation = str(row["distractor_explanation"]).strip().rstrip(".")
        parts.append(f"Выбранный в задании №{row['journal_no']} вариант соответствует ошибке: {explanation}.")
    kind = item["evidence_kind"]
    source = item.get("prerequisite_of")
    source_name = names.get(source or "", "")
    if kind == KIND_CONFIRMED_PREREQUISITE and source_name:
        parts.append(
            f"Это подтверждённый пререквизит навыка «{source_name}», поэтому с него следует начать коррекцию." if first
            else f"Это подтверждённый пререквизит навыка «{source_name}»."
        )
    elif kind == KIND_OBSERVED_PREREQUISITE and source_name:
        parts.append(f"Затруднение в этом навыке зафиксировано углублённой проверкой при разборе навыка «{source_name}».")
    parts.append(
        "Восстановить алгоритм навыка на коротких примерах из блока «Материал», затем решить задание из блока «Проверка»."
    )
    return " ".join(parts)


def _task_ref(task: Dict[str, Any]) -> Dict[str, Any]:
    return {k: task.get(k) for k in ("task_id", "question_text", "question_latex")}


def pick_material_and_check(free: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """(up to three tasks of the material, one task of the check) from the tasks the student did not get, in the given order.

    The check is never a task of the material.  One free task becomes the material (the check is then "at the lesson"); with two or
    more the last one needed is kept for the check.
    """
    if not free:
        return [], None
    if len(free) == 1:
        return [_task_ref(free[0])], None
    material = free[: min(MATERIAL_MAX, len(free) - 1)]
    check = free[len(material)]
    return [_task_ref(t) for t in material], _task_ref(check)


def material_block(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    block: Dict[str, Any] = {"tasks": tasks, "on_lesson": not tasks}
    if not tasks:
        block["text"] = ON_LESSON
    return block


def check_block(task: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "statement": CHECK_STATEMENT,
        "task": task,
        "on_lesson": task is None,
        "text": f"{CHECK_STATEMENT}." if task else f"Ученик решает без ошибки {ON_LESSON}.",
    }


def build_correction_steps(
    candidates: List[Dict[str, Any]],
    *,
    attempt_task_ids: Sequence[str],
    names: Dict[str, str],
    reader: Optional[BankReader] = None,
) -> List[Dict[str, Any]]:
    """The first five candidates as steps with the four lines.  Deterministic: the same data gives the same steps.

    When the bank could not be read (``reader.failure``: a transport failure, a timeout, the spent budget) the steps keep their basis but get
    NO material and NO check (``None``): an unread bank is not an empty bank, "a task at the lesson" would be a false statement.  The caller marks
    the report degraded (it is built again).
    """
    reader = reader or BankReader()
    steps: List[Dict[str, Any]] = []
    for number, item in enumerate(candidates[:PLAN_STEPS_MAX], 1):
        free = reader.unused_tasks(item["skill_id"], list(attempt_task_ids))
        material, check = pick_material_and_check(free or [])
        steps.append({
            "priority": number,
            "kind": "correction",
            "skill_id": item["skill_id"],
            "skill_name_ru": item["skill_name_ru"],
            "topic_id": item.get("topic_id"),
            "topic_name_ru": item.get("topic_name_ru"),
            "action_title": f"Отработать: {item['skill_name_ru']}",
            "full_description": deterministic_description(item, names, first=number == 1),
            "evidence_kind": item["evidence_kind"],
            "errors_count": item["errors"],
            "evidence": [_evidence_ref(r) for r in item["rows"][:EVIDENCE_MAX]],
            "material": material_block(material),
            "check": check_block(check),
            "source": "deterministic_fallback",
        })
    if reader.failure:
        for step in steps:
            step["material"], step["check"] = None, None
    return steps


def build_more_difficulties(candidates: List[Dict[str, Any]], steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Skills with errors that are not a step of the plan, grouped by topic - so that no skill with errors is named nowhere."""
    in_plan = {s["skill_id"] for s in steps}
    groups: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        if item["skill_id"] in in_plan:
            continue
        key = item.get("topic_id") or item["skill_id"]
        group = groups.setdefault(key, {
            "topic_id": item.get("topic_id"),
            "topic_name_ru": item.get("topic_name_ru") or item["skill_name_ru"],
            "skills": [],
        })
        group["skills"].append({
            "skill_id": item["skill_id"],
            "skill_name_ru": item["skill_name_ru"],
            "errors": item["errors"],
            "journal_nos": [r["journal_no"] for r in item["rows"]],
        })
    return list(groups.values())


# ── Development (no errors) ───────────────────────────────────────────────────

def build_development_step(
    achievements: List[Dict[str, Any]],
    answers: Sequence[Any],
    skill_map: Dict[str, Dict[str, str]],
    *,
    attempt_task_ids: Sequence[str],
    reader: Optional[BankReader] = None,
) -> Optional[Dict[str, Any]]:
    """The next step of an attempt without errors; no deficit is implied.

    The focus is the verified topic with the FEWEST checked tasks (a plain count), on a tie the lower hidden estimate (alpha), then the
    id.  Inside it the skill with the fewest correct answers.  The basis is its correct answers of this attempt; the material
    is the hardest tasks of the skill the student did not get, the check is one more of them.
    """
    if not achievements:
        return None
    topic = min(achievements, key=lambda a: (a["correct_answers"], a["mastery_percent"], a["skill_id"]))
    mine = [
        a for a in answers
        if getattr(a, "topic_id", None) == topic["skill_id"] and not getattr(a, "is_deep_scan", False) and is_correct(getattr(a, "outcome", None))
    ]
    per_skill: Dict[str, List[Any]] = {}
    for a in mine:
        per_skill.setdefault(a.skill_id, []).append(a)
    if not per_skill:
        return None
    skill_id = min(per_skill, key=lambda s: (len(per_skill[s]), s))
    name = skill_map.get(skill_id, {}).get("name_ru") or skill_id
    topic_name = topic["skill_name_ru"]
    reader = reader or BankReader()
    free = reader.unused_tasks(skill_id, list(attempt_task_ids), hardest_first=True)
    material, check = pick_material_and_check(free or [])
    step = {
        "priority": 1,
        "kind": "development",
        "skill_id": skill_id,
        "skill_name_ru": name,
        "topic_id": topic["skill_id"],
        "topic_name_ru": topic_name,
        "action_title": f"Развитие: {name}",
        "full_description": (
            "Все выполненные задания решены верно, дефицит не выявлен. Следующий шаг — развитие: "
            f"предложить задачи повышенной сложности и в новом контексте по навыку «{name}» (тема «{topic_name}»), "
            "затем сравнить способы решения и обосновать выбор метода. "
            f"Тема выбрана потому, что среди решённых без ошибок тем по ней проверено меньше всего заданий: {topic['correct_answers']}."
        ),
        "evidence_kind": KIND_DEVELOPMENT,
        "errors_count": 0,
        "evidence": [
            {
                "answer_id": str(a.id),
                "task_id": a.task_id,
                "student_answer": getattr(a, "student_answer", None),
                "correct": True,
            }
            for a in sorted(per_skill[skill_id], key=lambda x: (str(getattr(x, "answered_at", "") or ""), str(x.id)))[:EVIDENCE_MAX]
        ],
        "material": material_block(material),
        "check": check_block(check),
        "source": "deterministic_development",
    }
    if reader.failure:
        step["material"], step["check"] = None, None
    return step

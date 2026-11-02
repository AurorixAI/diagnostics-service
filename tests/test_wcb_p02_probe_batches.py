"""WC-B P-02: the precision-targeting step probes the candidate skills 8 at a time (one ``GET /tasks?skill_ids=...``) instead of one HTTP call per skill.

content-service is NOT changed: the existing endpoint takes ``skill_ids``, ``target_b``, ``exclude_ids`` and ``limit``.  The choice must stay the one the
skill-by-skill scan makes: the same FIRST skill with a free task.  Tested here (1) by counting HTTP calls of one answer of a student before/after on a
bank with empty skills, (2) against the old scan on hundreds of random banks, including windows cut by ``limit`` (a skill with farther tasks than the
window, a skill with fewer than 20 rows in it), (3) through the real ``_pick_precision_targeting_task``."""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from src.repositories import knowledge_repo
from src.repositories.knowledge_repo import KnowledgeRepository, TaskRepository, clear_hierarchy_cache
from tests.fake_content import FakeContent


def old_scan(repo, ordered, target_b, exclude):
    """The loops of origin/main: get_task_by_difficulty_target skill by skill, then the any-task pass."""
    for skill_id in ordered:
        task = repo.get_task_by_difficulty_target(skill_id, target_b=target_b, exclude_ids=exclude)
        if task is not None:
            return skill_id, task
    for skill_id in ordered:
        tasks = repo.get_tasks_for_skill(skill_id, exclude_ids=exclude, limit=1)
        if tasks:
            return skill_id, tasks[0]
    return None, None


def bank(content, grade=7, *, free_from=0, free_every=1):
    skills = content.l4(grade)
    for i, sid in enumerate(skills):
        if i >= free_from and (i - free_from) % free_every == 0:
            content.add_tasks(sid, [round(random.uniform(-2, 2), 2) for _ in range(random.randint(1, 6))])
    return skills


def service_with(content, monkeypatch, grade=7, theta=0.2):
    content.patch(monkeypatch)
    service = SessionService.__new__(SessionService)
    service.knowledge_repo, service.task_repo, service.prereq_repo = KnowledgeRepository(), TaskRepository(), None
    service._task_to_out = lambda task, state: task                 # the shape of the task is not under test
    state = SessionState(session_id="s", student_id="st", grade_level=grade)
    state.theta.theta = theta
    return service, state


@pytest.mark.parametrize("empty_prefix, probes_before, probes_after", [
    (0, 1, 1),          # the first skill has tasks: one call either way (the batch answer is enough, no second call)
    (7, 8, 1),          # the first 8 skills are empty: 8 probes -> one batch
    (40, 41, 6),        # 40 skills without a free task in front: 41 probes -> 6 batches
])
def test_task_probes_of_one_precision_answer(monkeypatch, empty_prefix, probes_before, probes_after):
    content = FakeContent(topics=4, subtopics_per_topic=8, skills_per_subtopic=4)       # 128 L4 skills
    skills = content.l4(7)
    for sid in skills[empty_prefix:]:
        content.add_tasks(sid, [0.0, 0.3, 1.0])
    service, state = service_with(content, monkeypatch)
    monkeypatch.setattr(random, "shuffle", lambda seq: seq.sort(key=skills.index))     # pin the candidate order: the empty skills are in front

    out = service._pick_precision_targeting_task(state)
    after = content.count("/api/v1/content/tasks")
    content.calls.clear()
    old_skill, old_task = old_scan(service.task_repo, skills, state.theta.theta, state.used_task_ids)       # the scan of origin/main
    before = content.count("/api/v1/content/tasks")
    print(f"\nP-02 {empty_prefix} empty skills in front: GET /tasks {before} -> {after}")
    assert out is not None and out.skill_id == old_skill == skills[empty_prefix]
    assert (before, after) == (probes_before, probes_after)


def test_a_bank_without_free_tasks_costs_a_scan_of_128_probes_twice_before_and_17_calls_after(monkeypatch):
    content = FakeContent(topics=4, subtopics_per_topic=8, skills_per_subtopic=4)
    skills = content.l4(7)
    service, state = service_with(content, monkeypatch)
    monkeypatch.setattr(random, "shuffle", lambda seq: seq.sort(key=skills.index))
    assert service._pick_precision_targeting_task(state) is None
    assert state.stop_reason == "insufficient_precision"
    after = content.count("/api/v1/content/tasks")
    content.calls.clear()
    old_scan(service.task_repo, skills, state.theta.theta, state.used_task_ids)
    before = content.count("/api/v1/content/tasks")
    print(f"P-02 exhausted bank, 128 skills: probes {before} -> {after}")
    assert before == 256 and after == 16        # 128 + 128 (the any-task pass) -> 16 batches, the any-task pass asks nobody again


@pytest.mark.parametrize("seed", range(60))
def test_random_banks_pick_the_same_first_skill_as_the_scan(seed):
    rng = random.Random(seed)
    content = FakeContent(topics=3, subtopics_per_topic=5, skills_per_subtopic=3)        # 45 skills
    skills = content.l4(7)
    for sid in skills:
        if rng.random() < 0.45:
            continue                                                                       # no tasks
        n = rng.choice([1, 3, 8, 19, 20, 21, 40, 90])                                      # around the 20-row boundary of a single scan
        content.add_tasks(sid, [round(rng.uniform(-3.5, 3.5), 2) for _ in range(n)])
    exclude = [t["id"] for sid in skills for t in content.tasks.get(sid, [])[:2] if rng.random() < 0.5]
    order = skills[:]
    rng.shuffle(order)
    target = round(rng.uniform(-2.5, 2.5), 2)
    mp = pytest.MonkeyPatch()
    content.patch(mp)
    try:
        repo = TaskRepository()
        free = [sid for sid in order if any(t["id"] not in set(exclude) for t in content.tasks.get(sid, []))]
        scan_skill, _ = old_scan(repo, order, target, exclude)
        assert scan_skill == (free[0] if free else None)                                 # what the scan does: the first skill with a free task
        for limit in (200, 60, 25, 9):                  # a window cut at any size must not change the choice of the skill
            skill, task, empty = repo.pick_task_by_difficulty_target(order, target, exclude_ids=exclude, limit=limit)
            assert skill == scan_skill
            assert set(empty) <= set(order) - set(free)              # a skill reported empty really has no free task
            if task is not None:
                assert task.skill_id == skill and task.id not in exclude
                near = sorted((t for t in content.tasks[skill] if t["id"] not in set(exclude)), key=lambda t: abs(t["irt_difficulty"] - target))[:20]
                best = abs(near[0]["irt_difficulty"] - target)
                allowed = {t["id"] for t in near if abs(t["irt_difficulty"] - target) <= best + 0.1 + 1e-9}
                assert task.id in allowed                # a task of the near-target pool of THAT skill, as the scan would pick
    finally:
        mp.undo()


def test_the_precision_step_keeps_its_behaviour_when_the_bank_is_exhausted(monkeypatch):
    content = FakeContent()
    service, state = service_with(content, monkeypatch)
    state.used_task_ids = []
    assert service._pick_precision_targeting_task(state) is None and state.stop_reason == "insufficient_precision"


def test_a_failing_batch_call_raises_like_a_failing_single_probe(monkeypatch):
    content = FakeContent()
    for sid in content.l4(7):
        content.add_tasks(sid, [0.0])
    service, state = service_with(content, monkeypatch)
    content.down = True
    with pytest.raises(ConnectionError):
        service.task_repo.pick_task_by_difficulty_target(content.l4(7), 0.0)


def test_all_content_calls_of_two_consecutive_precision_answers_before_and_after(monkeypatch):
    """P-01 + P-02 together, as a student feels them: the HTTP calls to content-service of two answers in a row, 40 empty skills in front.
    Before = cache off + the skill-by-skill scan (origin/main); after = hierarchy cache on + 8 skills per call."""
    from src.core.config import get_settings

    def run(cached, batched):
        content = FakeContent(topics=4, subtopics_per_topic=8, skills_per_subtopic=4)
        skills = content.l4(7)
        for sid in skills[40:]:
            content.add_tasks(sid, [0.0, 0.3, 1.0])
        with pytest.MonkeyPatch.context() as mp:
            service, state = service_with(content, mp)
            mp.setattr(get_settings(), "knowledge_cache_ttl", 600 if cached else 0)
            mp.setattr(random, "shuffle", lambda seq: seq.sort(key=skills.index))
            if not batched:
                real = service.task_repo
                scan = lambda sid, target_b, exclude_ids: real.get_task_by_difficulty_target(sid, target_b, exclude_ids=exclude_ids)
                from tests.test_adaptive_diagnostic_policy import batch_api
                service.task_repo = SimpleNamespace(get_task_by_difficulty_target=real.get_task_by_difficulty_target,
                                                    pick_task_by_difficulty_target=batch_api(scan),
                                                    get_tasks_for_skill=real.get_tasks_for_skill)
            picked = []
            for _ in range(2):
                out = service._pick_precision_targeting_task(state)
                picked.append(out.skill_id)
                state.used_task_ids = state.used_task_ids + [out.id]
            return content.count(), picked

    clear_hierarchy_cache()
    before, picked_before = run(cached=False, batched=False)
    clear_hierarchy_cache()
    after, picked_after = run(cached=True, batched=True)
    print(f"\nP-01+P-02 two precision answers, 40 empty skills in front: content HTTP {before} -> {after}")
    assert picked_before == picked_after
    assert (before, after) == (2 * (1 + 41 + 3), (1 + 3) + 6 + 6)      # 90 -> 16: lists/context once, then only the 6 batches of each answer

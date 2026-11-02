"""WC-B P-01 / P-03: the knowledge hierarchy is read from content-service once per 10 minutes per process, not on every answer and every report row.

Counters are HTTP calls to content-service (the fake of tests/fake_content.py counts them).  «Before» is the same code with the cache switched off
(``knowledge_cache_ttl = 0`` - the behaviour of origin/main); the answers must be identical.  The tasks themselves are never cached."""
from __future__ import annotations

import http.cookiejar
import uuid
from types import SimpleNamespace

import httpx
import pytest

from src.api import analytics_router
from src.clients import content_client
from src.core.config import get_settings
from src.repositories import knowledge_repo
from src.repositories.knowledge_repo import KnowledgeRepository, SkillPrerequisiteRepository, TaskRepository, clear_hierarchy_cache
from tests.fake_content import FakeContent, Response


@pytest.fixture
def content(monkeypatch):
    return FakeContent().patch(monkeypatch)


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 1000.0
    monkeypatch.setattr(knowledge_repo, "_now", lambda: Clock.now)
    return Clock


def ttl(monkeypatch, seconds):
    monkeypatch.setattr(get_settings(), "knowledge_cache_ttl", seconds)


def answers_of(content, n=40):
    skills = content.l4(7)
    return [SimpleNamespace(
        skill_id=skills[i % len(skills)], task_id=f"t{i}", outcome=1.0 if i % 3 else 0.0, theta_after=0.1 * i, is_deep_scan=i % 7 == 0,
        answered_at=i) for i in range(n)]


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *a):
        return self

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def all(self):
        return self.rows


def teacher_report(content, rows):
    session = SimpleNamespace(id=uuid.uuid4(), grade_level=7)
    repo = KnowledgeRepository()
    return (analytics_router._build_hierarchical_tree(session, FakeDb(rows), repo),
            analytics_router._build_diagnostic_trajectory(session, FakeDb(rows), repo))


def test_a_teacher_report_of_40_answers_costs_the_unique_nodes_not_240_calls(content, monkeypatch):
    rows = answers_of(content, 40)                      # the 12 skills of the bank, 6 subtopics, 2 topics
    ttl(monkeypatch, 0)
    before_tree, before_traj = teacher_report(content, rows)
    off = content.count()
    content.calls.clear()
    ttl(monkeypatch, 600)
    clear_hierarchy_cache()
    after_tree, after_traj = teacher_report(content, rows)
    first = content.count()
    content.calls.clear()
    again_tree, again_traj = teacher_report(content, rows)
    second = content.count()

    assert (after_tree, after_traj) == (before_tree, before_traj) == (again_tree, again_traj)
    skills = len({r.skill_id for r in rows})
    print(f"\nP-03 report of 40 answers: HTTP {off} (cache off) -> {first} (first open) -> {second} (second open); {skills} skills in the report")
    assert off == 240                                    # 3 reads per answer in the tree + 3 in the trajectory
    assert first == skills + 6 + 2                        # the unique nodes: skills + their subtopics + topics
    assert second == 0


def test_one_answer_of_a_student_reads_each_node_once_per_ten_minutes(content, monkeypatch):
    """_set_context_for_skill is called at every task: skill + subtopic + topic = 3 reads, the same three for the next task of the same skill."""
    from src.domain.session_service import SessionService
    from src.domain.session_state import SessionState

    service = SessionService.__new__(SessionService)
    service.knowledge_repo = KnowledgeRepository()
    skills = content.l4(7)

    def ten_tasks():
        state = SessionState(session_id="s", student_id="st", grade_level=7)
        for i in range(10):
            service._set_context_for_skill(state, skills[i % 2])      # navigation inside one subtopic
        return state.current_skill_id, state.current_subtopic_id, state.current_topic_id

    ttl(monkeypatch, 0)
    before = ten_tasks()
    off = content.count()
    content.calls.clear()
    ttl(monkeypatch, 600)
    clear_hierarchy_cache()
    after = ten_tasks()
    on = content.count()
    assert after == before
    print(f"P-01 10 tasks of one subtopic: HTTP {off} -> {on}")
    assert off == 30 and on == 4         # 2 skills + 1 subtopic + 1 topic


def test_the_l4_list_and_the_prerequisites_are_cached_by_their_own_keys(content, monkeypatch):
    content.prereqs["G7_T0_S0_K0"] = [{"prerequisite_id": "G6_X", "criticality": 7, "weight": 0.5}, {"prerequisite_id": "G6_A", "criticality": 9, "weight": 1.0}]
    content.nodes["G8_L1"] = {"id": "G8_L1", "parent_id": None, "level": "L1", "name": "n", "class_level_start": 8, "sequence_order": 0}
    content.nodes["G8_K"] = {"id": "G8_K", "parent_id": None, "level": "L4", "name": "n", "name_ru": "n", "class_level_start": 8, "sequence_order": 0}
    repo, pre = KnowledgeRepository(), SkillPrerequisiteRepository()
    g7 = [n.id for n in repo.get_by_level_and_grade("L4", 7)]
    g8 = [n.id for n in repo.get_by_level_and_grade("L4", 8)]
    assert g7 != g8 and g8 == ["G8_K"]                                        # the key carries the grade: no other class's skills
    assert [n.id for n in repo.get_by_level_and_grade("L4", 7)] == g7 and content.count("/api/v1/content/skills") == 2
    hard = [p.prerequisite_id for p in pre.get_prerequisites("G7_T0_S0_K0", hard_only=True)]
    soft = [p.prerequisite_id for p in pre.get_prerequisites("G7_T0_S0_K0", hard_only=False)]
    assert hard == soft == ["G6_A", "G6_X"]                                    # the stable order of the deep scan is kept
    n = content.count()
    pre.get_prerequisites("G7_T0_S0_K0", hard_only=True)
    pre.get_prerequisites("G7_T0_S0_K0", hard_only=False)
    assert content.count() == n                                               # each (skill, hard_only) is its own key, both cached
    assert [c.id for c in repo.get_children("G7_T0")] == ["G7_T0_S0", "G7_T0_S1", "G7_T0_S2"]


def test_a_node_is_read_again_after_the_ttl(content, clock, monkeypatch):
    ttl(monkeypatch, 600)
    repo = KnowledgeRepository()
    repo.get_by_id("G7_T0")
    clock.now += 599
    repo.get_by_id("G7_T0")
    assert content.count() == 1
    clock.now += 2                                                            # 601 s: expired
    repo.get_by_id("G7_T0")
    assert content.count() == 2


def test_a_404_is_not_cached_and_a_node_that_appears_is_seen(content):
    repo = KnowledgeRepository()
    assert repo.get_by_id("NEW") is None and repo.get_by_id("NEW") is None
    assert content.count() == 2                                               # asked again each time
    content.nodes["NEW"] = {"id": "NEW", "parent_id": None, "level": "L4", "name": "n", "class_level_start": 7, "sequence_order": 0}
    assert repo.get_by_id("NEW").id == "NEW"


def test_an_error_is_not_cached_and_a_failed_refresh_drops_the_old_answer(content, clock, monkeypatch):
    ttl(monkeypatch, 600)
    repo = KnowledgeRepository()
    repo.get_by_id("G7_T0")
    clock.now += 700                                                          # expired
    content.down = True
    with pytest.raises(ConnectionError):
        repo.get_by_id("G7_T0")                                               # the refresh fails: the error reaches the caller
    content.down = False
    n = content.count()
    clock.now -= 700                                                          # even «back in time» no stale entry is left to be served
    assert repo.get_by_id("G7_T0").id == "G7_T0"
    assert content.count() == n + 1


def test_a_server_error_response_is_raised_and_not_stored(content, monkeypatch):
    repo = KnowledgeRepository()
    monkeypatch.setattr(knowledge_repo.content_client, "get", lambda path, **kw: Response({"detail": "boom"}, 503))
    with pytest.raises(RuntimeError):
        repo.get_children("G7_T0")
    monkeypatch.setattr(knowledge_repo.content_client, "get", content.get)
    assert [c.id for c in repo.get_children("G7_T0")][0] == "G7_T0_S0"


def test_nobody_can_change_what_the_next_caller_gets(content):
    repo = KnowledgeRepository()
    first = repo.get_by_id("G7_T0")
    first.name = "VANDAL"
    first.extra = [1, 2]
    again = repo.get_by_id("G7_T0")
    assert again.name == "name G7_T0" and not hasattr(again, "extra")
    kids = repo.get_children("G7_T0")
    kids.clear()
    assert len(repo.get_children("G7_T0")) == 3


def test_ttl_zero_switches_the_cache_off(content, monkeypatch):
    ttl(monkeypatch, 0)
    repo = KnowledgeRepository()
    for _ in range(3):
        repo.get_by_id("G7_T0")
    assert content.count() == 3


def test_tasks_are_never_cached(content):
    content.add_tasks("G7_T0_S0_K0", [0.0, 0.5])
    repo = TaskRepository()
    first = repo.get_tasks_for_skill("G7_T0_S0_K0", limit=5)
    content.tasks["G7_T0_S0_K0"] = []                                         # the bank deactivated them
    assert len(first) == 2 and repo.get_tasks_for_skill("G7_T0_S0_K0", limit=5) == []
    assert content.count("/api/v1/content/tasks") == 2


def test_the_unused_redis_ttl_setting_is_gone_and_the_new_one_defaults_to_ten_minutes():
    settings = get_settings()
    assert not hasattr(settings, "redis_task_cache_ttl") and settings.knowledge_cache_ttl == 600


def test_the_shared_content_client_keeps_no_cookies(monkeypatch):
    """LESSONS 80: one client serves every student and teacher; a Set-Cookie of one answer must not ride on the next request."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, json=[], headers={"set-cookie": "sid=teacher-1; Path=/"})

    real = httpx.Client
    monkeypatch.setattr(content_client, "_client", None)
    monkeypatch.setattr(content_client.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    content_client.get("/api/v1/content/skills")
    content_client.get("/api/v1/content/skills")
    assert seen == [None, None]
    monkeypatch.setattr(content_client, "_client", None)

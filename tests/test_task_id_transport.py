"""Task identity survives HTTP parsing in issuance and report consumers."""
from types import SimpleNamespace

import httpx
import pytest

from src.clients import content_client
from src.domain import report_generator
from src.repositories.knowledge_repo import TaskRepository


TASK_IDS = [
    "ordinary-task",
    "G11_TB_?_265",
    "G11_TB_?_267_а",
    "G11_TB_?_268_а",
    "task#fragment&query=value+plus",
    "literal%3F%25",
    "задача с пробелом",
]


@pytest.fixture(params=TASK_IDS)
def task_api(request, monkeypatch):
    task_id = request.param
    payload = {
        "id": task_id, "skill_id": "G7_SKILL", "question_text": "Solve x = 2",
        "question_latex": "$x = 2$", "answer_type": "mcq",
        "correct_answer": "2", "correct_answer_latex": "$2$",
        "answer_options": ["2", "1"], "answer_options_latex": ["$2$", "$1$"],
        "distractor_meta": [{"value": "1", "value_latex": "$1$",
                             "error_logic": "Incorrect value"}],
    }
    requests = []

    def serve(http_request):
        requests.append(http_request)
        # The API looks up a decoded path parameter, never a query or fragment.
        if (http_request.url.path != "/api/v1/content/tasks/" + task_id
                or http_request.url.query or http_request.url.fragment):
            return httpx.Response(404)
        return httpx.Response(200, json=payload)

    with httpx.Client(base_url="http://content.test", transport=httpx.MockTransport(serve)) as client:
        monkeypatch.setattr(content_client, "_client", client)
        yield task_id, payload, requests


def test_task_repository_preserves_exact_id(task_api):
    task_id, payload, requests = task_api
    task = TaskRepository().get_by_id(task_id)
    assert task is not None
    assert task.id == task_id
    assert task.question_latex == payload["question_latex"]
    assert len(requests) == 1


@pytest.mark.parametrize("consumer", ["errors", "live_enrichment", "deep_scan"])
def test_report_consumers_load_the_same_task(task_api, consumer):
    task_id, payload, requests = task_api
    answer = SimpleNamespace(id=1, task_id=task_id, skill_id="G7_SKILL", outcome=0.,
                             student_answer="1", eval_category="distractor",
                             phase="deep_scan", is_deep_scan=True)
    if consumer == "errors":
        result = report_generator._build_error_patterns([answer], {})[0]
    elif consumer == "live_enrichment":
        result = report_generator.refresh_error_patterns_live(
            [{"task_id": task_id, "student_answer": "1"}],
        )[0]
    else:
        trigger = SimpleNamespace(task_id=None, skill_id="G8_SKILL", outcome=0.,
                                  student_answer="1", eval_category="wrong",
                                  phase="navigation", is_deep_scan=False)
        chain = report_generator._reconstruct_root_cause_chains(
            [trigger, answer], {}, [], grade_level=8,
        )[0]
        result = chain["steps"][-1]
    assert result["task_id"] == task_id
    assert result["question_latex"] == payload["question_latex"]
    assert result["correct_answer"] == payload["correct_answer"]
    assert len(requests) == 1


def test_missing_task_remains_missing(monkeypatch):
    with httpx.Client(base_url="http://content.test", transport=httpx.MockTransport(
        lambda _: httpx.Response(404),
    )) as client:
        monkeypatch.setattr(content_client, "_client", client)
        assert TaskRepository().get_by_id("missing?task") is None

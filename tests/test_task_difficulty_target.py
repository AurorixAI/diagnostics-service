from unittest.mock import patch

from src.repositories.knowledge_repo import TaskRepository


def test_target_zero_is_forwarded_with_exclusions_before_pagination():
    """Zero is a valid theta, not an absent filter; previous task stays excluded."""
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{"id": "near", "irt_difficulty": 0.0},
                    {"id": "far", "irt_difficulty": 1.5}]

    with patch("src.repositories.knowledge_repo.content_client.get", return_value=Response()) as get:
        task = TaskRepository().get_task_by_difficulty_target(
            "skill", 0.0, exclude_ids=["used"]
        )
    assert task.id == "near"
    assert get.call_args.kwargs["params"] == {
        "skill_id": "skill", "target_b": 0.0, "exclude_ids": ["used"], "limit": 20
    }


def test_ordinary_skill_request_keeps_existing_api_contract():
    with patch("src.repositories.knowledge_repo.content_client.get") as get:
        get.return_value.json.return_value = []
        TaskRepository().get_tasks_for_skill("skill", limit=3)
    assert get.call_args.kwargs["params"] == {"skill_id": "skill", "limit": 3}


import logging
import math

import pytest


def _sent_params(target_b, **kw):
    with patch("src.repositories.knowledge_repo.content_client.get") as get:
        get.return_value.json.return_value = []
        TaskRepository().get_tasks_for_skill("skill", limit=3, target_b=target_b, **kw)
    return get.call_args.kwargs["params"]


@pytest.mark.parametrize("given,sent", [(4.7, 4.0), (4.0, 4.0), (-4.02, -4.0), (-4.0, -4.0), (0.0, 0.0), (-2.5, -2.5)])
def test_target_b_is_clamped_to_the_content_api_range(given, sent):
    """content-service GET /tasks has Query(ge=-4, le=4): anything outside would be a 422."""
    assert _sent_params(given)["target_b"] == sent


def test_nan_target_b_is_sent_as_the_neutral_zero_and_logged(caplog):
    # a target-less request is NOT neutral: content-service then orders by irt_difficulty ASC
    with caplog.at_level(logging.WARNING, logger="src.repositories.knowledge_repo"):
        params = _sent_params(math.nan)
    assert params == {"skill_id": "skill", "limit": 3, "target_b": 0.0}
    assert any("NaN" in r.message for r in caplog.records)


@pytest.mark.parametrize("given,sent", [(math.inf, 4.0), (-math.inf, -4.0)])
def test_infinite_target_b_is_clamped_to_the_bound(given, sent, caplog):
    with caplog.at_level(logging.WARNING, logger="src.repositories.knowledge_repo"):
        assert _sent_params(given)["target_b"] == sent
    assert not caplog.records


def test_difficulty_target_helper_sends_the_clamped_target_and_measures_distance_to_it():
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{"id": "near", "irt_difficulty": 3.9}, {"id": "far", "irt_difficulty": 0.0}]

    with patch("src.repositories.knowledge_repo.content_client.get", return_value=Response()) as get:
        task = TaskRepository().get_task_by_difficulty_target("skill", 4.7)
    assert get.call_args.kwargs["params"]["target_b"] == 4.0
    assert task.id == "near"


@pytest.mark.parametrize("given,sent", [(math.nan, 0.0), (math.inf, 4.0), (-math.inf, -4.0)])
def test_difficulty_target_helper_normalises_non_finite_targets_for_every_caller(given, sent):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{"id": "low", "irt_difficulty": -3.9}, {"id": "mid", "irt_difficulty": 0.1},
                    {"id": "high", "irt_difficulty": 3.9}]

    with patch("src.repositories.knowledge_repo.content_client.get", return_value=Response()) as get:
        task = TaskRepository().get_task_by_difficulty_target("skill", given, exclude_ids=["used"])
    assert get.call_args.kwargs["params"]["target_b"] == sent          # always sent: never the target-less path
    assert get.call_args.kwargs["params"]["exclude_ids"] == ["used"]
    assert task.id == {0.0: "mid", 4.0: "high", -4.0: "low"}[sent]     # distance measured to the normalised target
    with patch("src.repositories.knowledge_repo.content_client.get") as get:
        get.return_value.json.return_value = []
        assert TaskRepository().get_task_by_difficulty_target("skill", given) is None


def test_difficulty_target_helper_with_no_target_sends_none_and_picks_any_unused_task():
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{"id": "a", "irt_difficulty": 0.3}, {"id": "b", "irt_difficulty": -1.0}]

    with patch("src.repositories.knowledge_repo.content_client.get", return_value=Response()) as get:
        task = TaskRepository().get_task_by_difficulty_target("skill", None, exclude_ids=["used"])
    assert get.call_args.kwargs["params"] == {"skill_id": "skill", "limit": 20, "exclude_ids": ["used"]}
    assert task.id in {"a", "b"}
    with patch("src.repositories.knowledge_repo.content_client.get") as get:
        get.return_value.json.return_value = []
        assert TaskRepository().get_task_by_difficulty_target("skill", None) is None

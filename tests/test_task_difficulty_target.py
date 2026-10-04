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

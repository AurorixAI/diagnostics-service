"""Regression tests for the report task-data contract."""
from types import SimpleNamespace

from src.domain import report_generator


def test_error_pattern_keeps_canonical_values_and_display_latex(monkeypatch):
    task_payload = {
        "question_text": "Решите x/2 = 1",
        "question_latex": r"Решите $\dfrac{x}{2} = 1$",
        "answer_type": "mcq",
        "correct_answer": "2",
        "correct_answer_latex": "$2$",
        "answer_options": ["2", "1"],
        "distractor_meta": [
            {
                "value": "1",
                "value_latex": "$1$",
                "explanation": "Не умножили обе части на 2.",
                "explanation_latex": "Не умножили обе части на $2$.",
                "error_logic": "Оставили коэффициент 2 в знаменателе.",
                "error_logic_latex": "Оставили коэффициент $2$ в знаменателе.",
            },
        ],
    }

    class Response:
        status_code = 200

        def json(self):
            return task_payload

    from src.clients import content_client
    monkeypatch.setattr(content_client, "get", lambda _: Response())

    answer = SimpleNamespace(
        task_id="task-1", skill_id="skill-1", student_answer="1",
        outcome=0.0, eval_category="distractor", answered_at=None, id=1,
    )
    pattern = report_generator._build_error_patterns([answer], {"skill-1": {"name_ru": "Навык"}})[0]

    assert pattern["task_id"] == "task-1"
    assert pattern["question_text"] == task_payload["question_text"]
    assert pattern["question_latex"] == task_payload["question_latex"]
    assert pattern["answer_options"] == ["2", "1"]
    assert pattern["answer_options_latex"] == ["$2$", "$1$"]
    assert pattern["correct_answer"] == "2"
    assert pattern["correct_answer_latex"] == "$2$"
    assert pattern["distractor_explanation"] == "Оставили коэффициент 2 в знаменателе."
    assert pattern["distractor_explanation_latex"] == "Оставили коэффициент $2$ в знаменателе."


def test_error_pattern_reads_legacy_text_distractor_without_mutating_it(monkeypatch):
    task_payload = {
        "question_text": "Выберите значение",
        "question_latex": "Выберите значение",
        "answer_type": "mcq",
        "correct_answer": "2",
        "correct_answer_latex": "$2$",
        "answer_options": [],
        "distractor_meta": [
            {
                "text": "1/2",
                "text_latex": r"$\dfrac{1}{2}$",
                "error_logic": "Перепутан обратный коэффициент.",
                "error_logic_latex": "Перепутан обратный коэффициент.",
            },
        ],
    }

    class Response:
        status_code = 200

        def json(self):
            return task_payload

    from src.clients import content_client
    monkeypatch.setattr(content_client, "get", lambda _: Response())
    answer = SimpleNamespace(
        task_id="legacy-task", skill_id="skill-1", student_answer="1/2",
        outcome=0.0, eval_category="distractor", answered_at=None, id=1,
    )

    pattern = report_generator._build_error_patterns([answer], {"skill-1": {"name_ru": "Навык"}})[0]

    assert pattern["answer_options"] == ["2", "1/2"]
    assert pattern["answer_options_latex"] == ["$2$", r"$\dfrac{1}{2}$"]
    assert pattern["distractor_explanation"] == "Перепутан обратный коэффициент."
    assert pattern["distractor_explanation_latex"] == "Перепутан обратный коэффициент."
    assert task_payload["distractor_meta"][0]["text"] == "1/2"


def test_error_pattern_preserves_independent_answer_options_and_student_display(monkeypatch):
    task_payload = {
        "question_text": "Выберите вариант",
        "question_latex": "Выберите вариант",
        "answer_type": "mcq",
        "correct_answer": "2",
        "correct_answer_latex": "$2$",
        "answer_options": ["2", "1"],
        "answer_options_latex": ["$2$", "$1$"],
        # This distractor is deliberately not an answer_options replacement.
        "distractor_meta": [{"value": "3", "value_latex": "$3$"}],
    }

    class Response:
        status_code = 200

        def json(self):
            return task_payload

    from src.clients import content_client
    monkeypatch.setattr(content_client, "get", lambda _: Response())
    answer = SimpleNamespace(
        task_id="independent-options", skill_id="skill-1", student_answer="1",
        outcome=0.0, eval_category="wrong", answered_at=None, id=1,
    )

    pattern = report_generator._build_error_patterns([answer], {"skill-1": {"name_ru": "Навык"}})[0]

    assert pattern["answer_options"] == ["2", "1"]
    assert pattern["answer_options_latex"] == ["$2$", "$1$"]
    assert pattern["student_answer_latex"] == "$1$"


def test_error_pattern_enriches_exact_legacy_distractor_even_if_history_says_wrong(monkeypatch):
    """A historical category must not hide a known, exactly matched mistake."""
    task_payload = {
        "question_text": "Выберите значение",
        "question_latex": "Выберите значение",
        "answer_type": "mcq",
        "correct_answer": r"$\frac{5}{4}$",
        "correct_answer_latex": r"$\dfrac{5}{4}$",
        "answer_options": [r"$\frac{5}{4}$", r"$-\frac{5}{4}$"],
        "distractor_meta": [{
            "text": r"-\frac{5}{4}",
            "error_logic": "Потерян знак при преобразовании.",
            "error_logic_latex": "Потерян знак при преобразовании.",
        }],
    }

    class Response:
        status_code = 200

        def json(self):
            return task_payload

    from src.clients import content_client
    monkeypatch.setattr(content_client, "get", lambda _: Response())
    answer = SimpleNamespace(
        task_id="legacy-wrong", skill_id="skill-1", student_answer=r"$-\frac{5}{4}$",
        outcome=0.0, eval_category="wrong", answered_at=None, id=1,
    )

    pattern = report_generator._build_error_patterns([answer], {"skill-1": {"name_ru": "Навык"}})[0]

    assert pattern["eval_category"] == "wrong"  # append-only history is not rewritten
    assert pattern["distractor_explanation"] == "Потерян знак при преобразовании."

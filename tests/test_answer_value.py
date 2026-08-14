from types import SimpleNamespace

from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.answer_value import answer_value_key


def test_answer_value_key_removes_only_outer_math_delimiters():
    assert answer_value_key(" $88779$ ") == "88779"
    assert answer_value_key("$$ x + 1 $$") == "x + 1"
    assert answer_value_key(r"\dfrac{1}{2}") == r"\dfrac{1}{2}"


def test_mcq_display_wrapped_distractor_is_recorded_as_distractor():
    task = SimpleNamespace(
        correct_answer="$2$",
        answer_type="mcq",
        distractor_meta=[{"value": "1"}],
    )

    assert AnswerEvaluator().evaluate(task, "$1$") == (0.0, "distractor")

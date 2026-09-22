from types import SimpleNamespace

from src.domain.answer_evaluator import AnswerEvaluator, _sympy_equivalent


def _open_task(correct_answer: str, sympy_solution: str | None = None):
    return SimpleNamespace(
        correct_answer=correct_answer,
        sympy_solution=sympy_solution,
        answer_type="open",
        distractor_meta=[],
    )


def test_safe_symbolic_equivalence_keeps_supported_school_notation():
    evaluator = AnswerEvaluator()

    assert evaluator.evaluate(_open_task("2*x + 2"), "2(x + 1)") == (1.0, "correct")
    assert evaluator.evaluate(_open_task("3"), "√9") == (1.0, "correct")
    assert evaluator.evaluate(_open_task("pi"), "π") == (1.0, "correct")
    assert evaluator.evaluate(_open_task("1/2"), "0,5") == (1.0, "correct")


def test_symbolic_parser_rejects_python_syntax_before_sympy_evaluation():
    payloads = (
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "x.__class__",
        "[x for x in range(3)]",
        "lambda x: x",
    )

    for payload in payloads:
        assert _sympy_equivalent(payload, "0") is False


def test_symbolic_parser_rejects_unbounded_or_unsupported_identifiers():
    assert _sympy_equivalent("a" * 257, "0") is False
    assert _sympy_equivalent("unknown_function(1)", "0") is False
    assert _sympy_equivalent("9**999999999999", "0") is False

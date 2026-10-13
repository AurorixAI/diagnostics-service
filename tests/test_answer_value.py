from types import SimpleNamespace

from fractions import Fraction

import pytest

from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.answer_value import answer_value_key, answers_equivalent, display_student_answer, exact_number, report_answer_key


@pytest.mark.parametrize("first, second", [
    ("0,22", r"$\dfrac{11}{50}$"),
    ("$0.5$", "1/2"),
    ("3 4/9", r"$3\dfrac{4}{9}$"),
    (r"$3 \dfrac{4}{9}$", r"3\frac{4}{9}"),
    ("$[-4$; $2]$ и $[6$; $8)$", "$[-4; 2]$ и $[6; 8)$"),
    (r"$6\,000$", "6000"),
    (r"$(-\infty; 2)$", "(-∞; 2)"),
    (r"$\left(1; 2\right)$", "(1; 2)"),
    (r"-\dfrac{1}{2}", "-0,5"),
    (r"\dfrac{-1}{2}", "-1/2"),
    ("да", " Да "),
    ("$0{,}78^{-0{,}7}$", "$0.78^{-0.7}$"),
    (r"$\log_{0{,}2} 0{,}7$", r"$\log_{0.2} 0.7$"),
    (r"$\sin{\alpha}$", r"$\sin \alpha$"),
    (r"$\dfrac{1}{\cos^{2}{\alpha}}$", r"$\dfrac{1}{\cos^{2} \alpha}$"),
    (r"$\log_{2}{x}$", r"$\log_{2} x$"),
    ("Если $a = -4$, то $x \\in [-a; 4)$.", "Если $a = -4$, то $x \\in [-a; 4)$"),
    ("$25, 9, -39, -52;$", "$25, 9, -39, -52$"),
])
def test_answers_equivalent_recognises_one_value_in_two_notations(first, second):
    assert answers_equivalent(first, second)
    assert answers_equivalent(second, first)


@pytest.mark.parametrize("first, second", [
    ("1/3", "0,33"),
    ("3 4/9", "34/9"),
    ("(-∞; 2)", "(-∞; 2]"),
    ("x", "-x"),
    ("0,22", "0,23"),
    ("51\\%", "0,51"),
    ("2; 3", "3; 2"),
    ("1/0", "0"),
    ("", ""),
    ("$2$", "$2x$"),
    (r"\sqrt{2}", "2"),
    ("да", "нет"),
    (r"$\dfrac{\sqrt{2}}{2}$", r"$\sqrt{\dfrac{2}{2}}$"),
    ("1, 2", "1.2"),
    (r"$\log_{0.2} 0.7$", r"$\log_{0.7} 0.2$"),
    (r"$\sin \alpha$", r"$\sin 2\alpha$"),
    (r"$\sin{x}$", r"$\sin{y}$"),
    ("1.", "1.5"),
    (r"$x \in (4; -a]$", r"$x \in (4; -a)$"),
])
def test_answers_equivalent_never_merges_different_answers(first, second):
    assert not answers_equivalent(first, second)
    assert not answers_equivalent(second, first)


@pytest.mark.parametrize("value, expected", [
    ("7", Fraction(7)), ("-0,25", Fraction(-1, 4)), (r"$\dfrac{3}{8}$", Fraction(3, 8)),
    (r"$2\dfrac{1}{3}$", Fraction(7, 3)), (r"$-1\dfrac{1}{2}$", Fraction(-3, 2)), ("5 1/4", Fraction(21, 4)),
    (r"$60\,000$", Fraction(60000)), ("12 345", Fraction(12345)), (r"$0{,}5$", Fraction(1, 2)),
])
def test_exact_number_parses_unambiguous_numbers(value, expected):
    assert exact_number(value) == expected


@pytest.mark.parametrize("value", ["x + 1", "(1; 2)", "1, 2", "3 4", "50\\%", r"\sqrt{3}", "1/0", "", "2; 3"])
def test_exact_number_refuses_everything_else(value):
    assert exact_number(value) is None


def test_answer_value_key_normalizes_display_equivalent_math_values():
    assert answer_value_key(" $88779$ ") == "88779"
    assert answer_value_key("$$ x + 1 $$") == "x+1"
    assert answer_value_key(r"\dfrac{1}{2}") == r"\frac{1}{2}"


def test_mcq_display_wrapped_distractor_is_recorded_as_distractor():
    task = SimpleNamespace(
        correct_answer="$2$",
        answer_type="mcq",
        distractor_meta=[{"value": "1"}],
    )

    assert AnswerEvaluator().evaluate(task, "$1$") == (0.0, "distractor")


LATEX = r"$y = 2 \pm \sqrt{x - 1}$, $x \in [1; +\infty)$"


def test_display_answer_unwraps_a_python_repr_dict_with_escaped_backslashes():
    stored = repr({"text": LATEX, "is_correct": False})                    # backslashes doubled, quotes single
    assert "\\\\pm" in stored and stored.startswith("{'text'")
    assert display_student_answer(stored) == LATEX
    assert display_student_answer("  " + stored + "\n") == LATEX              # surrounding blanks


def test_display_answer_unwraps_a_json_dict():
    import json
    assert display_student_answer(json.dumps({"text": LATEX, "is_correct": True})) == LATEX
    assert display_student_answer('{"text": "x = 5"}') == "x = 5"


@pytest.mark.parametrize("raw", [
    "x = 5", "$\\frac{1}{2}$", "", "   ", "{1; 2}", "{x | x>0}", "{1, 2, 3}", "{}", "{-3; 5}", "{x \\in R}",
    "{'text': 'unterminated", "{'text': }", "{'a': 1}", "{'text': 5}", "{'text': ''}", "{'text': None}",
    '{"text": 7}', "[{'text': 'x'}]", "x {'text': 'y'}",
    "{'text': __import__('os').getcwd()}",                           # never evaluated
    "{'text': 'a'} + {'text': 'b'}",
])
def test_display_answer_leaves_everything_else_unchanged(raw):
    assert display_student_answer(raw) == raw


def test_display_answer_passes_non_strings_through_and_caps_the_input():
    assert display_student_answer(None) is None and display_student_answer(5) == 5
    long_dict = repr({"text": "x" * 3000, "is_correct": False})
    assert len(long_dict) > 2000 and display_student_answer(long_dict) == long_dict
    nested = "{'text': " + "[" * 500 + "1" + "]" * 500 + "}"                 # deep nesting must not raise
    assert display_student_answer(nested) == nested


# ── report-side matching of a stored answer to a repaired task ─────────────────

@pytest.mark.parametrize("stored, current", [
    ("x^3 < y^3", "$x^{3} < y^{3}$"),                    # prod session b5b3e418 / ds_llm_c93d5c1c9ba6 after wave w35
    ("a_2", "a_{2}"), ("$a_{2}$", "a_2"), ("x^{3}", "x^3"), ("x^{ 3 }", "x^3"), ("e^{x}", "e^x"),
    (r"\dfrac{1}{2}", r"\frac{1}{2}"), ("$ x ^ 3 $", "x^{3}"), ("x_{i}^{2}", "x_i^2"),
])
def test_report_key_treats_single_token_braces_dollars_and_dfrac_as_equal(stored, current):
    assert report_answer_key(stored) == report_answer_key(current)


@pytest.mark.parametrize("first, second", [
    ("x^{13}", "x^13"), ("x^{13}", "x^1 3"), ("x^{13}", "x^3"), ("a_{12}", "a_1 2"), ("x^{-1}", "x^-1"),
    (r"x^{\alpha}", r"x^\alpha"), ("x^{3}", "x^4"),
])
def test_report_key_never_unwraps_a_multi_character_group(first, second):
    assert report_answer_key(first) != report_answer_key(second)


def test_scoring_key_is_unchanged_the_report_key_is_separate():
    assert answer_value_key("x^3 < y^3") != answer_value_key("$x^{3} < y^{3}$")     # answer-time grading untouched
    assert answer_value_key("$ 5 $") == report_answer_key("$5$") == "5"


@pytest.mark.parametrize("value, expected", [
    (None, ""), ("", ""), ("   ", ""), ("$$", ""), ("$ $", ""),
    ("x^{}", "x^{}"), ("x^{ }", "x^{}"),                         # an empty group is not a single token
    ("x^{{3}}", "x^{{3}}"), ("x^{3}{4}", "x^3{4}"),              # nested / consecutive groups: only the plain single group
    ("x^{_}", "x^{_}"), ("x^{;}", "x^{;}"),                      # underscore / punctuation is not a character of the answer
    ("x^{α}", "x^α"), ("a_{п}", "a_п"),                          # a single non-ASCII letter is a character
    ("x^{3}", "x^3"), ("x_{i}^{2}", "x_i^2"), ("e^{x}+e^{-x}", "e^x+e^{-x}"),
    ("10^{5}", "10^5"), ("10^{15}", "10^{15}"), ("2^{n}-1", "2^n-1"),
    ("\\left(x^{2}\\right)", "(x^2)"), ("\\frac{a^{2}}{b}", "\\frac{a^2}{b}"),
])
def test_report_key_edge_cases(value, expected):
    assert report_answer_key(value) == expected


def test_report_key_is_idempotent_and_does_not_collapse_different_values():
    for value in ("$x^{3} < y^{3}$", "x^{13}", "a_{12}", "x^{-1}", r"\dfrac{1}{2}", "e^{x}"):
        assert report_answer_key(report_answer_key(value)) == report_answer_key(value)
    assert len({report_answer_key(v) for v in ("x^3", "x^13", "x^{13}", "x_3", "x^-3", "x^{-3}")}) >= 5


# ── report key: Unicode spellings of old snapshots vs the LaTeX of the repaired bank (DIAG-3) ─────────────────────

@pytest.mark.parametrize("snapshot, bank", [
    # prod 13.10: G9_TB_17_2_1 (options shown as Unicode, distractor_meta in LaTeX)
    ("$π/45$", r"$\dfrac{\pi}{45}$"), ("$π/8$", r"$\dfrac{\pi}{8}$"), ("$π/4$", r"$\dfrac{\pi}{4}$"), ("$45π$", r"$45\pi$"),
    # prod 13.10: G9_TB_21_252_4, every wrong option and the correct one
    ("x = -π/2 + 2πk, k ∈ Z", r"$x = -\dfrac{\pi}{2} + 2\pi k, k \in \mathbb{Z}$"),
    ("x = -4π + 2πk, k ∈ Z", r"$x = -4\pi + 2\pi k, k \in \mathbb{Z}$"),
    ("x = -5π/2 + πk, k ∈ Z", r"$x = -\dfrac{5\pi}{2} + \pi k, k \in \mathbb{Z}$"),
    ("x = -5π + 2πk, k ∈ Z", r"$x = -5\pi + 2\pi k, k \in \mathbb{Z}$"),
    # one symbol, two spellings
    ("π", r"\pi"), ("2π", r"2\pi"), ("∞", r"\infty"), ("(-∞; 3]", r"(-\infty; 3]"), ("x ∈ (0; 1)", r"x \in (0; 1)"),
    ("x ∉ A", r"x \notin A"), ("x ≤ 5", r"x \le 5"), ("x ≤ 5", r"x \leq 5"), (r"x \le 5", r"x \leq 5"),
    ("x ≥ 5", r"x \ge 5"), ("x ≥ 5", r"x \geq 5"), ("a ≠ 0", r"a \ne 0"), ("a ≠ 0", r"a \neq 0"), ("x<=5", "x ≤ 5"), ("x>=5", "x ≥ 5"),
    ("2·3", r"2 \cdot 3"), ("2⋅3", r"2\cdot3"), ("2×3", r"2 \times 3"), ("−3", "-3"), ("a − b", "a - b"),
    ("±1", r"\pm 1"), ("∅", r"\emptyset"), ("∅", r"\varnothing"), ("α", r"\alpha"), ("sin α", r"\sin \alpha"), ("2β + γ", r"2\beta + \gamma"),
    ("30°", r"30^{\circ}"), ("30°", r"30^\circ"), ("x²", "x^{2}"), ("x²", "x^2"), ("(x+1)³", "(x+1)^3"),
    ("tg x", r"\operatorname{tg} x"), ("ctg 2x", r"\operatorname{ctg}2x"), ("arctg 1", r"\operatorname{arctg} 1"),
    ("arcsin x", r"\arcsin x"), ("lg 2", r"\lg 2"), ("max", r"\max"),
    # number sets: Unicode, \mathbb, and a bare letter only right after a membership sign
    ("ℤ", r"\mathbb{Z}"), ("ℝ", r"\mathbb R"), ("ℕ", r"\mathbb{N}"), ("ℚ", r"\mathbb{ Q }"),
    ("k ∈ Z", r"k \in \mathbb{Z}"), ("k ∈ ℤ", r"k \in \mathbb{Z}"), ("n∈Z", r"n \in Z"), ("x ∈ R", r"x \in \mathbb{R}"),
    ("0 ∈ N", r"0 \in \mathbb{N}"), ("x ∉ Z", r"x \notin \mathbb{Z}"),
    # square roots of one token
    ("√3", r"\sqrt{3}"), ("√3", r"\sqrt3"), ("√12", r"\sqrt{12}"), ("√x", r"\sqrt{x}"), ("3√2", r"3\sqrt{2}"),
    ("√(x+1)", r"\sqrt{x+1}"), ("√3/2", r"\dfrac{\sqrt{3}}{2}"), ("-√2/2", r"-\dfrac{\sqrt{2}}{2}"),
    ("(-∞; -√2/2) ∪ (√2/2; +∞)", r"(-\infty; -\dfrac{\sqrt{2}}{2}) \cup (\dfrac{\sqrt{2}}{2}; +\infty)"),
    # a fraction of two single atoms
    ("1/2", r"\frac{1}{2}"), ("1/2", r"\dfrac{1}{2}"), ("-3/4", r"-\dfrac{3}{4}"), ("π/45", r"\frac{\pi}{45}"), ("5π/2", r"\frac{5\pi}{2}"),
    ("x/2", r"\frac{x}{2}"), ("2x/3", r"\frac{2x}{3}"), ("1/x", r"\frac{1}{x}"), ("a/b", r"\dfrac{a}{b}"), ("1/√2", r"\frac{1}{\sqrt{2}}"),
    ("π / 6", r"\frac{\pi}{6}"), ("sin(π/6)", r"\sin\left(\dfrac{\pi}{6}\right)"), ("x^{1/2}", r"x^{\frac{1}{2}}"),
    ("(1/2; 3]", r"(\frac{1}{2}; 3]"), ("x = 1/2", r"x = \frac{1}{2}"),
    ("x = π/6, 5π/6", r"x = \frac{\pi}{6}, \frac{5\pi}{6}"), ("1/2; 3/4", r"\frac{1}{2}; \frac{3}{4}"),
    ("±π/3 + 2πk", r"\pm\dfrac{\pi}{3} + 2\pi k"),
])
def test_report_key_merges_unicode_and_latex_spellings_of_the_same_value(snapshot, bank):
    assert report_answer_key(snapshot) == report_answer_key(bank)
    assert report_answer_key(bank) == report_answer_key(snapshot)


@pytest.mark.parametrize("first, second", [
    # a different number / symbol
    ("π/4", r"\frac{\pi}{2}"), ("π/4", r"\frac{4}{\pi}"), ("1/2", r"\frac{2}{1}"), ("1/2", r"\frac{1}{3}"), ("a/b", "b/a"),
    ("5π/2", r"\frac{5}{2\pi}"), ("√3", r"\sqrt{2}"), ("√3", "3"), ("α", "β"), ("30°", "30"), ("x²", "x^3"), ("x³", "x^{23}"),
    # same value, different notation: the key never parses or simplifies
    ("2π/3", r"\frac{2}{3}\pi"),            # 2π/3 is (2π)/3, \frac{2}{3}\pi is 2/3 times π: equal in value, not in notation
    ("1/2", "0,5"), ("1/2", "0.5"), ("-π/2", r"\frac{-\pi}{2}"), ("1 2/3", r"1\frac{2}{3}"),
    # a mixed number is not the fraction of its digits (found on the real bank: 24 groups such as `1 3/25` vs `\dfrac{13}{25}`)
    ("1 3/25", r"\dfrac{13}{25}"), ("1 3/25", "13/25"), ("4 1/48", r"\frac{41}{48}"), ("-2 5/7", r"-\dfrac{25}{7}"),
    (r"1\,3/25", r"\frac{13}{25}"), ("2 1/2", r"\frac{21}{2}"),
    ("1 125/200", "1125/200"),               # thousands grouping or a mixed number? unknowable, so the fraction is not recognised
    # composite numerator / denominator are not unfolded (and must not raise)
    ("(x+1)/2", r"\frac{x+1}{2}"), ("x/2 + 1", r"\frac{x+1}{2}"), ("2πk/3", r"\frac{2\pi}{3}k"), ("1/(2x)", r"\frac{1}{2x}"),
    ("x^2/2", r"\frac{x^2}{2}"), ("a/bc", r"\frac{a}{b}c"),
    # a slash that is not a plain fraction of two atoms
    ("1/2x", r"\frac{1}{2x}"), ("1/2x", r"\frac{1}{2}x"), ("1/2π", r"\frac{1}{2\pi}"), ("x/2y", r"\frac{x}{2y}"),
    ("1/2/3", r"\frac{1}{2}/3"), ("x^1/2", r"x^{\frac{1}{2}}"), ("x^-1/2", r"x^{-\frac{1}{2}}"), ("0.5/2", r"\frac{5}{2}"),
    ("1,5/2", r"\frac{5}{2}"), ("3/4,5", r"\frac{3}{4},5"), ("sin 1/2", r"\sin\frac{1}{2}"), ("30°/2", r"\frac{30^{\circ}}{2}"),
    # a number set only right after a membership sign
    ("Z", r"\mathbb{Z}"), ("Z = 5", r"\mathbb{Z} = 5"), ("Z ∈ A", r"\mathbb{Z} \in A"), ("k ∈ Zx", r"k \in \mathbb{Z}x"),
    ("x ∈ z", r"x \in \mathbb{Z}"), ("x ∈ Z", "x ∈ R"), ("x ∈ Z", "x ∈ N"), ("x ∉ Z", r"x \in \mathbb{Z}"),
    ("ℤ", "ℝ"), (r"\mathbb{Z}", r"\mathbb{N}"), ("M ∈ Z", "M ∈ M"),
    # relations and signs
    (r"x \le 5", "x < 5"), ("x ≤ 5", "x < 5"), ("x ≤ 5", "x ≥ 5"), ("x ≥ 5", "x > 5"), ("a ≠ 0", "a = 0"), ("-1", "±1"), ("−1", "±1"),
    ("x ∈ A", "x ∉ A"), ("∞", "-∞"), ("(1; 2)", "(1; 2]"), ("2·3", "23"), ("a·b", "a+b"), ("<=", "<"),
    # square roots: a radicand that is a guess stays unmatched
    ("√2x", r"\sqrt{2x}"), ("√2x", r"\sqrt{2}x"), ("√12", r"\sqrt{1}2"), ("√x²", r"\sqrt{x^2}"), ("√(x+1)", r"\sqrt{x}+1"),
    ("√12.5", r"\sqrt{12.5}"),
    # functions and Greek letters that are not the same name / glyph
    ("tg x", "ctg x"), ("tg x", r"\operatorname{ctg} x"), ("sin x", "cos x"), ("arcsin x", r"\arccos x"), (r"\phi", "φ"), (r"\varepsilon", "ε"),
    ("sin² x", r"\sin x^2"),
])
def test_report_key_keeps_different_notations_and_values_apart(first, second):
    assert report_answer_key(first) != report_answer_key(second)


@pytest.mark.parametrize("value", [
    "", "/", "//", "1/", "/2", "√", "√(", "√()", "√(x", "()/2", "(/)", "∈", "∈ Z", "x ∈", r"\mathbb", r"\mathbb{", r"\frac{", r"\frac{1}{",
    r"\sqrt", r"\sqrt{", "^{", "1,", ", 2", "1, 2/3", "·", "−", "<=", "<=>", "1/2" * 400, "√" * 50, "x" * 5000 + "/" + "y" * 5000,
])
def test_report_key_never_raises_on_odd_input(value):
    assert isinstance(report_answer_key(value), str)


def test_report_key_stays_idempotent_with_the_new_spellings():
    for value in (r"$\dfrac{\pi}{45}$", "π/45", "x = -5π/2 + πk, k ∈ Z", r"k \in \mathbb{Z}", "√3/2", r"\sqrt3", "x ≤ 5", "x <= 5", "30°",
                  "x²", "1/2x", "(x+1)/2", "x = π/6, 5π/6", "1,5/2", r"\operatorname{tg} x", "−1", "2·3", "ℝ"):
        once = report_answer_key(value)
        assert report_answer_key(once) == once


def test_report_key_decides_a_comma_between_digits_by_the_space_after_it():
    """`π/6, 5π/6` is a list; `1,5/2` is the decimal 1,5 over 2 and `6,5π/6` cannot be told apart from it."""
    assert report_answer_key("1/2, 3/4") == report_answer_key(r"\frac{1}{2}, \frac{3}{4}")
    assert report_answer_key("1,5/2") != report_answer_key("1, 5/2")
    assert report_answer_key("1/2,5") != report_answer_key("1/2, 5")
    assert "" not in report_answer_key("1/2, 3/4")                 # the internal list marker never leaks into a key


def test_report_key_only_widens_what_the_old_key_did_not_know():
    """Old report keys that were equal stay equal (whitespace, `$`, \\dfrac, single-token braces)."""
    for first, second in [
        ("x^3 < y^3", "$x^{3} < y^{3}$"), ("x ^ 3", "x^{3}"), (r"\dfrac{1}{2}", r"\frac {1} {2}"), ("a_{2}", "a_2"), ("1 / 2", "1/2"),
        ("x \\in [1; 2]", "x\\in[1;2]"), ("π / 45", "π/45"), ("5 π / 2", "5π/2"), (r"\sqrt{ 3 }", r"\sqrt{3}"),
        ("1 000", "1000"), (r"1\,000", "1000"), ("1 3", "13"),     # a gap between digits stays invisible outside a fraction
    ]:
        assert report_answer_key(first) == report_answer_key(second)


def test_scoring_key_ignores_the_new_equivalences():
    """Grading at answer time keeps `answer_value_key`: Unicode and LaTeX spellings are still different there."""
    for first, second in [("π/45", r"\frac{\pi}{45}"), ("k ∈ Z", r"k \in \mathbb{Z}"), ("x ≤ 5", r"x \le 5"), ("√3", r"\sqrt{3}")]:
        assert answer_value_key(first) != answer_value_key(second)
        assert report_answer_key(first) == report_answer_key(second)

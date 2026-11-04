from types import SimpleNamespace as NS
from src.domain import report_plan
from src.domain.report_generator import _build_skill_blocks, _build_deterministic_summary

def test_low_alpha_without_wrong_answers_never_creates_a_correction_plan():
    strong, weak, critical = _build_skill_blocks({'G10_T05': {'alpha': .4}}, [],
        {'G10_T05': {'name_ru': 'Показательные функции'}}, [NS(outcome=1), NS(outcome=1)])
    assert weak == critical == []
    assert report_plan.build_plan_candidates([], [], {'G10_T05': {'alpha': .4}}) == []   # the plan is made of wrong answers only

def test_an_observed_wrong_answer_preserves_the_gap_block():
    _, weak, _ = _build_skill_blocks({'G10_T05': {'alpha': .4}}, [],
        {'G10_T05': {'name_ru': 'Показательные функции'}},
        [NS(outcome=1, topic_id='G10_T05'), NS(outcome=0, topic_id='G10_T05')])
    assert weak[0]['skill_id'] == 'G10_T05'

def test_error_free_summary_describes_strengths_without_inventing_remediation():
    text = _build_deterministic_summary(status_label='Выше уровня класса',grade_level=10,
        score_pct=100,boundary={'breakpoint_skills': []},chains=[],
        strong_skills=[{'skill_name_ru': 'Функции'}])
    assert 'затруднения не зафиксированы' in text
    assert 'Функции' in text
    assert 'коррекц' not in text.lower() and 'первопричин' not in text.lower()

def test_summary_keeps_observed_errors_and_confirmed_prerequisites():
    args=dict(status_label='Частичные пробелы',grade_level=10,score_pct=40,
        boundary={'breakpoint_skills':['Логарифмы']},strong_skills=[])
    observed = _build_deterministic_summary(**args,chains=[])
    assert 'Зафиксированы ключевые затруднения: Логарифмы' in observed and 'Коррекцию' in observed
    confirmed = _build_deterministic_summary(**args,chains=[{'root_gap_skill_name':'Дроби'}])
    assert 'Углублённая проверка подтвердила первопричину: «Дроби»' in confirmed

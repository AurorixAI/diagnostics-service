from types import SimpleNamespace as NS
from src.domain.report_generator import _build_skill_blocks, _build_deterministic_summary, _build_plan_candidates

def test_low_alpha_without_wrong_answers_never_creates_a_correction_plan():
    strong, weak, critical = _build_skill_blocks({'G10_T05': {'alpha': .4}}, [],
        {'G10_T05': {'name_ru': 'Показательные функции'}}, [NS(outcome=1), NS(outcome=1)])
    assert weak == critical == []
    assert _build_plan_candidates([], critical, weak, []) == []

def test_an_observed_wrong_answer_preserves_the_gap_block():
    _, weak, _ = _build_skill_blocks({'G10_T05': {'alpha': .4}}, [],
        {'G10_T05': {'name_ru': 'Показательные функции'}},
        [NS(outcome=1, topic_id='G10_T05'), NS(outcome=0, topic_id='G10_T05')])
    assert weak[0]['skill_id'] == 'G10_T05'

def test_error_free_summary_describes_strengths_without_inventing_remediation():
    text = _build_deterministic_summary(class_equivalent='начало 11 класса',grade_level=10,
        score_pct=100,boundary={'breakpoint_skills': []},chains=[],
        strong_skills=[{'skill_name_ru': 'Функции'}])
    assert 'затруднения не зафиксированы' in text
    assert 'Функции' in text
    assert 'коррекц' not in text.lower() and 'первопричин' not in text.lower()

def test_summary_keeps_observed_errors_and_confirmed_prerequisites():
    args=dict(class_equivalent='конец 9 класса',grade_level=10,score_pct=40,
        boundary={'breakpoint_skills':['Логарифмы']},strong_skills=[])
    observed = _build_deterministic_summary(**args,chains=[])
    assert 'Зафиксированы ключевые затруднения: Логарифмы' in observed and 'Коррекцию' in observed
    confirmed = _build_deterministic_summary(**args,chains=[{'root_gap_skill_name':'Дроби'}])
    assert 'Deep Scan подтвердил первопричину: «Дроби»' in confirmed

import pytest
from src.domain.session_service import SessionService
from src.domain.report_generator import REPORT_SCHEMA_VERSION

@pytest.mark.parametrize('version,current',[(2,False),(REPORT_SCHEMA_VERSION,True)])
def test_public_report_recognizes_the_same_schema_as_the_worker(version,current):
    service=object.__new__(SessionService)
    session=NS(id='session',student_id='student',phase='completed',grade_level=10,
        theta=1.8,theta_se=.35,overall_level='above_grade',topic_breakdown={},weak_skills=[],stop_reason='classification_confident')
    report=NS(report_json={'error_patterns':[]},report_schema_version=version,generation_status='ready',generation_stage='done',generation_attempts=1)
    service.session_repo=NS(get_by_id=lambda _:session)
    service.answer_repo=NS(get_session_answers=lambda _:[])
    service.report_repo=NS(get_by_session=lambda _:report)
    result=service.get_report_data('session')
    assert result['report_generation']['is_current_schema']==current
    assert result['report_json']==report.report_json

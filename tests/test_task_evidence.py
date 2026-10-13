"""Content edits cannot re-grade issued tasks or replace historical context."""
import copy
import json
from types import SimpleNamespace as NS
import pytest
from src.clients import content_client
from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.report_generator import _build_error_patterns, refresh_error_patterns_live
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from src.domain.task_evidence import capture_task, read_task, task_object


def task(**kw):
    values=dict(id='evidence?task',skill_id='G7_S',question_text='Old condition',question_latex='$x=2$',
                question_image_url='/old-figure.svg',correct_answer='2',correct_answer_latex='$2$',
                answer_type='mcq',sympy_solution=None,answer_options=['2','1'],answer_options_latex=['$2$','$1$'],
                distractor_meta=[{'value':'1','value_latex':'$1$','error_logic':'Old explanation'}],
                irt_discrimination=1.,irt_difficulty=-.5,irt_guessing=.25)
    return NS(**{**values,**kw})


def state():
    return SessionState(session_id='evidence-session',student_id='synthetic',grade_level=7,
                        current_task_id='evidence?task',current_skill_id='G7_S',current_topic_id='G7_T')


def answer(snapshot=None,**kw):
    return NS(**{**dict(id='answer-1',task_id='evidence?task',skill_id='G7_S',student_answer='1',outcome=0.,
                    eval_category='distractor',answered_at=None,task_snapshot=snapshot),**kw})


def test_issued_restore_ignores_new_bank_text_options_key_and_image():
    service=SessionService.__new__(SessionService);st=state();original=task()
    first=service._task_to_out(original,st)
    st=SessionState.from_dict(json.loads(json.dumps(st.to_dict())))
    changed=task(question_text='New condition',question_latex='$x=99$',correct_answer='99',
                 answer_options=['99','2'],answer_options_latex=['$99$','$2$'],question_image_url='/new.svg')
    service.task_repo=NS(get_by_id=lambda _:pytest.fail('resume must not fetch live bank'))
    resumed=service._current_task_from_state(st)
    assert resumed==first
    assert service._task_to_out(changed,st)==first
    saved=task_object(st.current_task_snapshot,original.id)
    assert AnswerEvaluator().evaluate(saved,'2')[0]==1
    assert AnswerEvaluator().evaluate(saved,'99')[0]==0
    assert saved.irt_difficulty==-.5


def test_snapshot_is_detached_from_source_and_next_issuance():
    service=SessionService.__new__(SessionService);st=state();source=task()
    service._task_to_out(source,st);saved=copy.deepcopy(st.current_task_snapshot)
    source.distractor_meta[0]['error_logic']='Changed outside state'
    next_source=task(id='next');service._task_to_out(next_source,st)
    assert read_task(saved,'evidence?task')['distractor_meta'][0]['error_logic']=='Old explanation'
    assert st.current_task_snapshot['task']['id']=='next'


@pytest.mark.parametrize('edit',['key','id','hash','version','no_provenance','empty_provenance','non_string_provenance'])
def test_corrupt_or_foreign_evidence_is_rejected(edit):
    snapshot=capture_task(task(),['2','1'],['$2$','$1$'],'mcq')
    if edit=='key':snapshot['task']['correct_answer']='99'
    elif edit=='id':snapshot['task']['id']='foreign'
    elif edit=='hash':snapshot['sha256']='invalid'
    elif edit=='version':snapshot['version']=99
    elif edit=='no_provenance':del snapshot['provenance']
    elif edit=='empty_provenance':snapshot['provenance']='  '
    else:snapshot['provenance']=7
    with pytest.raises(ValueError):read_task(snapshot,'evidence?task')


def test_an_unknown_or_future_provenance_label_does_not_blank_the_question():
    # integrity is identity + hash; the label is informational (a mixed deploy must not lose questions)
    snapshot=capture_task(task(),['2','1'],['$2$','$1$'],'mcq',provenance='some_future_label')
    assert read_task(snapshot,'evidence?task')['correct_answer']==task().correct_answer
    snapshot['task']['correct_answer']='99'                     # tampering is still caught by the hash
    with pytest.raises(ValueError):read_task(snapshot,'evidence?task')


def test_open_input_and_alternative_image_fields_survive_snapshot():
    source=task(question_image_url=None,image_url='/alias.svg')
    snapshot=capture_task(source,None,None,'open')
    payload=read_task(snapshot,source.id)
    assert payload['display_options'] is None and payload['display_options_latex'] is None
    assert payload['question_image_url']=='/alias.svg'


def test_error_report_uses_snapshot_and_exact_display_order_without_network(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:pytest.fail('report must not read live bank'))
    snapshot=capture_task(task(),['1','2'],['$1$','$2$'],'mcq')
    result=_build_error_patterns([answer(snapshot)],{})[0]
    assert result['question_latex']=='$x=2$' and result['correct_answer']=='2'
    assert result['answer_options']==['1','2'] and result['answer_options_latex']==['$1$','$2$']
    assert result['distractor_explanation']=='Old explanation'
    assert result['content_provenance']=='issued' and result['answer_id']=='answer-1'


def bank_response(status=200,**kw):
    payload=dict(id='evidence?task',skill_id='G7_S',question_text='Live condition',question_latex='$x=3$',
                 correct_answer='3',correct_answer_latex='$3$',answer_type='mcq',
                 answer_options=['3','1'],answer_options_latex=['$3$','$1$'],
                 distractor_meta=[{'value':'1','value_latex':'$1$','error_logic':'Live explanation'}])
    payload.update(kw)
    return NS(status_code=status,json=lambda:payload)


def test_null_snapshot_falls_back_to_live_bank_and_is_marked(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:bank_response())
    result=_build_error_patterns([answer()],{})[0]
    assert result['context_source']=='live_bank' and result['content_provenance']=='unavailable'
    assert result['question_latex']=='$x=3$' and result['correct_answer']=='3'
    assert result['answer_options']==['3','1'] and result['answer_options_latex']==['$3$','$1$']
    assert result['distractor_explanation']=='Live explanation' and result['answer_type']=='mcq'


def test_snapshot_wins_over_live_bank_and_is_marked(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:pytest.fail('snapshot present: no bank read'))
    result=_build_error_patterns([answer(capture_task(task(),['1','2'],['$1$','$2$'],'mcq'))],{})[0]
    assert result['context_source']=='snapshot'


def test_backfilled_snapshot_is_readable_and_reported_as_snapshot(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:pytest.fail('snapshot present: no bank read'))
    snap=capture_task(task(),['1','2'],['$1$','$2$'],'mcq',provenance='legacy_bank_backfill')
    result=_build_error_patterns([answer(snap)],{})[0]
    assert result['context_source']=='snapshot' and result['content_provenance']=='legacy_bank_backfill'


@pytest.mark.parametrize('failure',['404','500','raises'])
def test_null_snapshot_and_unavailable_bank_stays_unknown(monkeypatch,failure):
    def fake(_):
        if failure=='raises':raise RuntimeError('bank down')
        return NS(status_code=int(failure),json=lambda:{})
    monkeypatch.setattr(content_client,'get_task',fake)
    result=_build_error_patterns([answer()],{})[0]
    assert result['question_latex'] is None and result['correct_answer'] is None
    assert result['answer_options']==[] and result['context_source']=='unavailable'


def test_legacy_cached_context_is_used_only_when_bank_unavailable_and_not_mutated(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:NS(status_code=404,json=lambda:{}))
    old=[{'task_id':'evidence?task','student_answer':'1','question_latex':'Old proof',
          'correct_answer':'Old key','answer_options':['Old key','1']}]
    before=copy.deepcopy(old)
    result=_build_error_patterns([answer()],{},old)[0]
    assert result['question_latex']=='Old proof' and result['correct_answer']=='Old key'
    assert result['content_provenance']=='legacy_report_context' and result['context_source']=='previous_report'
    assert old==before
    returned=refresh_error_patterns_live(old);returned[0]['answer_options'].append('Mutation')
    assert old==before


def test_ambiguous_legacy_context_is_not_attributed_to_an_answer(monkeypatch):
    monkeypatch.setattr(content_client,'get_task',lambda _:NS(status_code=404,json=lambda:{}))
    duplicate={'task_id':'evidence?task','student_answer':'1','correct_answer':'Uncertain'}
    result=_build_error_patterns([answer()],{},[duplicate,duplicate])[0]
    assert result['correct_answer'] is None and result['content_provenance']=='unavailable'


def test_old_redis_state_deserializes_without_inventing_snapshot():
    old=state().to_dict();old.pop('current_task_snapshot')
    assert SessionState.from_dict(old).current_task_snapshot is None

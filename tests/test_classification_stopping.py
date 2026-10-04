import copy
import math

import numpy as np
import pytest

from src.domain.alpha_engine import ThetaState, level_confidence, _THETA_GRID
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from src.domain.navigators.skill_navigator import SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator


def posterior(theta, se):
    weights = np.exp(-.5*((_THETA_GRID-theta)/se)**2)
    weights /= weights.sum()
    return ThetaState(theta=theta, se=se, posterior=weights.tolist())


def ready_state(theta=.2, se=.35, **kwargs):
    state = SessionState(session_id='s', student_id='u', grade_level=10,
                         phase='navigation', items_answered=20,
                         section_ids=['a','b','c','d','e'],
                         covered_section_ids=['a','b','c','d','e'])
    state.theta = posterior(theta, se)
    for key,value in kwargs.items(): setattr(state,key,value)
    return state


@pytest.mark.parametrize('theta',[-1.5,.2,1.8])
def test_confident_level_stops_at_twenty_with_se_above_strict_target(theta):
    service=object.__new__(SessionService)
    state=ready_state(theta=theta)
    assert level_confidence(state.theta) >= .9
    assert service._should_stop(state)
    assert state.stop_reason=='classification_confident'


@pytest.mark.parametrize('overrides',[
    {'items_answered':19},
    {'covered_section_ids':['a','b','c','d']},
    {'is_in_deep_scan':True},
])
def test_early_classification_keeps_minimum_coverage_and_probe_gates(overrides):
    service=object.__new__(SessionService);state=ready_state(**overrides)
    assert not service._should_stop(state)
    assert state.stop_reason is None


def test_borderline_level_and_high_se_continue():
    service=object.__new__(SessionService)
    assert not service._should_stop(ready_state(theta=1.1))
    assert not service._should_stop(ready_state(theta=1.8,se=.401))


def test_strict_precision_remains_a_separate_reason():
    service=object.__new__(SessionService);state=ready_state(theta=1.1,se=.29)
    assert service._should_stop(state)
    assert state.stop_reason=='precision_reached'


def test_pending_critical_probe_blocks_both_early_rules_and_marks_hard_cap():
    service=object.__new__(SessionService);state=ready_state(se=.20)
    assert not service._should_stop(state,pending_critical_probe=True)
    state.items_answered=42
    assert service._should_stop(state,pending_critical_probe=True)
    assert state.stop_reason=='max_items_reached' and state.deep_scan_incomplete


def critical_state(skill_count=1,importance=8):
    state=ready_state()
    subtopics=SubtopicNavigator.create('topic',5,[SubtopicEntry('sub','topic',0,importance)])
    skills=SkillNavigator.create('sub',[SkillEntry('skill'+str(i),'sub',i,float(i)) for i in range(skill_count)])
    state.current_subtopic_nav=subtopics.to_dict();state.current_skill_nav=skills.to_dict()
    return state


def test_failed_critical_skill_is_previewed_without_mutating_navigation():
    service=object.__new__(SessionService);state=critical_state()
    before=copy.deepcopy(state.to_dict())
    assert service._has_pending_critical_probe(state,False)
    assert state.to_dict()==before
    assert not service._has_pending_critical_probe(state,True)


def test_critical_search_continues_until_failed_skill_boundary_is_resolved():
    service=object.__new__(SessionService);state=critical_state(skill_count=3)
    assert service._has_pending_critical_probe(state,False)
    assert not service._has_pending_critical_probe(critical_state(importance=7),False)


def test_non_navigation_answers_do_not_invent_a_pending_scan():
    service=object.__new__(SessionService)
    for phase in ['warmup','precision_targeting','deep_scan']:
        state=critical_state();state.phase=phase
        assert not service._has_pending_critical_probe(state,False)


def test_boundary_cells_match_normal_interval_probability():
    state=posterior(0.,1.)
    expected=.5*(math.erf(1/math.sqrt(2))-math.erf(-.5/math.sqrt(2)))
    assert abs(level_confidence(state)-expected)<.002
    state=posterior(1.,.35)
    assert abs(level_confidence(state)-.5)<.001


@pytest.mark.parametrize('weights', [[1.], [float('nan')]*61, [-1.]*61, [0.]*61])
def test_invalid_posterior_cannot_claim_confident_classification(weights):
    assert level_confidence(ThetaState(theta=1.8,se=.35,posterior=weights))==0

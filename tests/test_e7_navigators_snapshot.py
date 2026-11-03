"""Wave E7 / DU-01 (before any refactor of the three navigators): the dict of ``to_dict()`` is stored in the JSON of live sessions
(``SessionState.topic_navigator_states`` / ``current_subtopic_nav`` / ``current_skill_nav``), so its keys and values must stay exactly as they are.
``navigators_to_dict_golden.json`` was produced by the code of d7627e7: 3 navigators x sizes 0,1,2,3,5,8 x 7 answer sequences, ``to_dict()`` after every move."""
import json
import pathlib

import pytest

from src.domain.navigators.skill_navigator import SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicNavigator
from src.domain.navigators.topic_navigator import TopicNavigator
from tests.navigators_scenarios import all_runs

GOLDEN = json.loads((pathlib.Path(__file__).parent / "fixtures" / "navigators_to_dict_golden.json").read_text(encoding="utf-8"))
CLASSES = {"topic": TopicNavigator, "subtopic": SubtopicNavigator, "skill": SkillNavigator}


def test_every_step_of_every_run_serialises_as_before():
    runs = all_runs()
    assert set(runs) == set(GOLDEN)
    for name, steps in runs.items():
        assert json.loads(json.dumps(steps)) == GOLDEN[name], name


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_a_stored_state_loads_and_serialises_back_to_the_same_dict(name):
    cls = CLASSES[name.split("-")[0]]
    for stored in GOLDEN[name]:
        assert cls.from_dict(json.loads(json.dumps(stored))).to_dict() == stored


def test_the_keys_of_each_navigator_are_the_stored_ones():
    first = {name.split("-")[0]: steps[0] for name, steps in GOLDEN.items() if name.endswith("-1-Y") is False}
    assert set(first["topic"]) == {"section_id", "topics", "cursor", "lo", "hi", "tested", "results", "exhausted"}
    assert set(first["subtopic"]) == {"topic_id", "topic_importance", "subtopics", "cursor", "lo", "hi", "tested", "results", "scores",
                                      "exhausted", "boundary_subtopic_id"}
    assert set(first["skill"]) == {"subtopic_id", "skills", "cursor", "lo", "hi", "tested", "results", "exhausted", "failing_skill_id"}


def test_an_exhausted_navigator_has_lo_above_hi():
    for name, steps in GOLDEN.items():
        for step in steps:
            if step["exhausted"]:
                assert step["lo"] > step["hi"], name

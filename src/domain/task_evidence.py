"""Content used for one answer; no second copy/version row in the live bank."""
from __future__ import annotations
import copy
import hashlib
import json
from types import SimpleNamespace

TASK_FIELDS = (
    'id', 'skill_id', 'question_text', 'question_latex', 'question_image_url',
    'answer_type', 'correct_answer', 'correct_answer_latex', 'sympy_solution',
    'answer_options', 'answer_options_latex', 'distractor_meta',
    'irt_discrimination', 'irt_difficulty', 'irt_guessing',
)


def _digest(task: dict) -> str:
    return hashlib.sha256(json.dumps(task, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def capture_task(task, options, options_latex, answer_type, *, provenance='issued') -> dict:
    payload = {key: copy.deepcopy(getattr(task, key, None)) for key in TASK_FIELDS}
    payload['question_image_url'] = (payload['question_image_url']
                                     or getattr(task, 'image_url', None)
                                     or getattr(task, 'figure_url', None))
    for key in ('irt_discrimination', 'irt_difficulty', 'irt_guessing'):
        if payload[key] is not None:
            payload[key] = float(payload[key])
    # These are the actual displayed choices/order, not a re-shuffle at report time.
    payload['display_options'] = list(options) if options is not None else None
    payload['display_options_latex'] = list(options_latex) if options_latex is not None else None
    payload['display_answer_type'] = answer_type
    return {'version': 1, 'provenance': provenance, 'task': payload, 'sha256': _digest(payload)}


def read_task(snapshot, task_id: str) -> dict | None:
    if snapshot is None:
        return None
    # ``provenance`` is a label ('issued', 'legacy_answer_lookup', 'legacy_bank_backfill', 'bank_refresh', ...):
    # an unknown future value must not blank a question, so only its presence is required here; integrity
    # is the identity + hash check below.
    if (not isinstance(snapshot, dict) or snapshot.get('version') != 1
            or not isinstance(snapshot.get('provenance'), str) or not snapshot['provenance'].strip()
            or not isinstance(snapshot.get('task'), dict)):
        raise ValueError('Invalid task evidence envelope')
    payload = snapshot['task']
    if payload.get('id') != task_id or snapshot.get('sha256') != _digest(payload):
        raise ValueError('Task evidence identity/hash mismatch')
    return copy.deepcopy(payload)


def task_object(snapshot, task_id: str):
    payload = read_task(snapshot, task_id)
    return SimpleNamespace(**payload) if payload is not None else None


# Fields a content repair can change and a report shows (explanations, key, options, question).  Never
# refreshed: id, skill_id, answer_type, the IRT parameters and ``display_*`` - the last ones record the
# item that was issued and exactly what the student saw (choices, their order and LaTeX).
REFRESHED_FIELDS = (
    'question_text', 'question_latex', 'question_image_url', 'correct_answer', 'correct_answer_latex',
    'sympy_solution', 'answer_options', 'answer_options_latex', 'distractor_meta',
)
# Replaced only when no integrity flag is raised (see ``integrity_flags``): they define what was asked and
# what counted as correct when the stored outcome was decided.
KEY_AND_QUESTION_FIELDS = (
    'question_text', 'question_latex', 'question_image_url', 'correct_answer', 'correct_answer_latex', 'sympy_solution',
)


def _blank(value) -> str:
    return str(value or '').strip()


def live_task_problem(live_task) -> str | None:
    """Why a live bank task must not be copied into a snapshot (None when it may)."""
    if getattr(live_task, 'is_active', True) is False:
        return 'inactive_task'
    if not (_blank(getattr(live_task, 'question_text', None)) or _blank(getattr(live_task, 'question_latex', None))):
        return 'invalid_live_task'
    if not _blank(getattr(live_task, 'correct_answer', None)):
        return 'invalid_live_task'
    return None


def refresh_snapshot(snapshot, task_id: str, live_task, *, source: str, refreshed_at: str, keep_key_and_question: bool = False):
    """Copy of ``snapshot`` whose report-facing fields come from the current bank task.

    Returns ``(new_snapshot, changed_fields)``; ``new_snapshot`` is ``None`` when nothing would change.
    With ``keep_key_and_question`` the key and the question stay as they were when the student answered.
    ``display_*`` (what the student saw) and everything of the answer row (outcome, student_answer) are
    never touched.  ``provenance`` becomes ``bank_refresh`` - an honest label: no longer exactly issued
    content.  Metadata sits next to ``sha256`` (which covers ``task`` only, as in the backfill script) so
    adding it cannot invalidate ``read_task``; every refresh appends to ``refresh_history`` the hash and
    provenance it replaced, so a second refresh never loses the issued ones.
    """
    old_payload = read_task(snapshot, task_id)
    if old_payload is None:
        raise ValueError('No snapshot to refresh')
    payload = copy.deepcopy(old_payload)
    for key in REFRESHED_FIELDS:
        if keep_key_and_question and key in KEY_AND_QUESTION_FIELDS:
            continue
        value = getattr(live_task, key, None)
        if key == 'question_image_url':
            value = value or getattr(live_task, 'image_url', None) or getattr(live_task, 'figure_url', None)
        payload[key] = copy.deepcopy(value)
    changed = [key for key in payload if payload[key] != old_payload.get(key)]
    if not changed:
        return None, []
    history = list(snapshot.get('refresh_history') or [])
    history.append({
        'at': refreshed_at,
        'source': source,
        'previous_sha256': snapshot.get('sha256'),
        'previous_provenance': snapshot.get('provenance'),
        'changed_fields': changed,
        'kept_key_and_question': bool(keep_key_and_question),
    })
    refreshed = {
        **{k: v for k, v in snapshot.items() if k not in ('task', 'sha256', 'provenance', 'refresh_history')},
        'version': 1,
        'provenance': 'bank_refresh',
        'task': payload,
        'sha256': _digest(payload),
        'refresh_history': history,
    }
    return refreshed, changed


def integrity_flags(old_payload: dict, new_payload: dict, student_answer, outcome) -> list:
    """Reasons a refresh could make the report contradict the stored verdict (empty list = safe).

    * ``key_changed`` - the correct answer is another value than when the student answered;
    * ``student_answer_equals_new_key_but_outcome<1`` - the stored answer is the NEW key, yet it was
      graded wrong;
    * ``new_key_not_in_display_options`` - the new key is not among the choices the student saw;
    * ``question_changed`` - the question text / LaTeX differs.
    """
    from src.domain.answer_value import display_student_answer, report_answer_key

    flags = []
    old_key = report_answer_key(old_payload.get('correct_answer'))
    new_key = report_answer_key(new_payload.get('correct_answer'))
    if old_key != new_key:
        flags.append('key_changed')
    try:
        graded_below_one = float(outcome) < 1
    except (TypeError, ValueError):
        graded_below_one = True
    if new_key and graded_below_one and report_answer_key(display_student_answer(student_answer)) == new_key:
        flags.append('student_answer_equals_new_key_but_outcome<1')
    shown = old_payload.get('display_options')
    if isinstance(shown, list) and shown and new_key and new_key not in {report_answer_key(o) for o in shown}:
        flags.append('new_key_not_in_display_options')
    if (_blank(old_payload.get('question_text')), _blank(old_payload.get('question_latex'))) != (
        _blank(new_payload.get('question_text')), _blank(new_payload.get('question_latex'))
    ):
        flags.append('question_changed')
    return flags

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
    if (not isinstance(snapshot, dict) or snapshot.get('version') != 1
            or snapshot.get('provenance') not in ('issued', 'legacy_answer_lookup', 'legacy_bank_backfill', 'bank_refresh')
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
# refreshed: id, skill_id, answer_type and the IRT parameters - they describe the item that was issued.
REFRESHED_FIELDS = (
    'question_text', 'question_latex', 'question_image_url', 'correct_answer', 'correct_answer_latex',
    'sympy_solution', 'answer_options', 'answer_options_latex', 'distractor_meta',
)


def refresh_snapshot(snapshot, task_id: str, live_task, options, options_latex, *, source: str, refreshed_at: str):
    """Copy of ``snapshot`` whose report-facing fields come from the current bank task.

    Returns ``(new_snapshot, info)``; ``new_snapshot`` is ``None`` when nothing would change.
    The displayed choices are what the student actually saw and are replaced only when the freshly
    built options carry the same values in the same order (then just their LaTeX is refreshed);
    otherwise they are kept and ``info['display_options_kept']`` is set.  Outcome and the student's
    answer live on the answer row and are never part of a snapshot.  ``provenance`` becomes
    ``bank_refresh`` - an honest label: this is no longer the exactly issued content.
    """
    old_payload = read_task(snapshot, task_id)
    if old_payload is None:
        raise ValueError('No snapshot to refresh')
    payload = copy.deepcopy(old_payload)
    for key in REFRESHED_FIELDS:
        value = getattr(live_task, key, None)
        if key == 'question_image_url':
            value = value or getattr(live_task, 'image_url', None) or getattr(live_task, 'figure_url', None)
        payload[key] = copy.deepcopy(value)
    old_options = payload.get('display_options')
    kept = False
    if (list(old_options) if old_options is not None else None) == (list(options) if options is not None else None):
        payload['display_options_latex'] = list(options_latex) if options_latex is not None else None
    else:
        kept = True
    changed = [key for key in payload if payload[key] != old_payload.get(key)]
    if not changed:
        return None, {'changed_fields': [], 'display_options_kept': kept}
    refreshed = {
        'version': 1,
        'provenance': 'bank_refresh',
        'task': payload,
        'sha256': _digest(payload),
        'refresh': {
            'source': source,
            'refreshed_at': refreshed_at,
            'previous_provenance': snapshot.get('provenance'),
            'previous_sha256': snapshot.get('sha256'),
            'changed_fields': changed,
            'display_options_kept': kept,
        },
    }
    return refreshed, {'changed_fields': changed, 'display_options_kept': kept}

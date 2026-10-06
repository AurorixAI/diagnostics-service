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
            or snapshot.get('provenance') not in ('issued', 'legacy_answer_lookup', 'legacy_bank_backfill')
            or not isinstance(snapshot.get('task'), dict)):
        raise ValueError('Invalid task evidence envelope')
    payload = snapshot['task']
    if payload.get('id') != task_id or snapshot.get('sha256') != _digest(payload):
        raise ValueError('Task evidence identity/hash mismatch')
    return copy.deepcopy(payload)


def task_object(snapshot, task_id: str):
    payload = read_task(snapshot, task_id)
    return SimpleNamespace(**payload) if payload is not None else None

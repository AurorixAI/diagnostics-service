"""Wave A / A4 (diagnostic): the report read.

S-02 the invite code (a capability) travels in the X-Diagnostic-Invite-Code header, not in the URL;
S-03 `GET /sessions/{id}/report` is behind the failed-lookup brake like the other public entries - and a valid read
(the finished page polls it every few seconds) costs nothing.
J-01 no production report dumps in the repository or in the image.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import router as diag_router
from src.core.abuse_limit import FAILS_PER_MINUTE, counters
from src.core.database import get_db

ROOT = Path(__file__).resolve().parent.parent
CODE = "A4REPORT01"
SESSION_ID = uuid.uuid4()
URL = f"/api/v1/diagnostic/sessions/{SESSION_ID}/report"
TOO_MANY_CODE = "TOO_MANY_ATTEMPTS"


class _Query:
    def __init__(self, session):
        self._session = session

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._session


class _Db:
    def __init__(self, session):
        self._session = session

    def query(self, *_a, **_k):
        return _Query(self._session)


@pytest.fixture
def api(monkeypatch):
    session = SimpleNamespace(
        id=SESSION_ID, invite_code=CODE, student_id=uuid.uuid4(), grade_level=9, phase="completed", created_at=None,
    )
    seen = {"capability_codes": []}

    async def capability(code, **kwargs):
        seen["capability_codes"].append(code)
        return {"status": "completed"}

    class Service:
        def get_report_data(self, session_id):
            return {"session_id": str(session_id), "report_generation": {"status": "ready"}}

    monkeypatch.setattr(diag_router, "validate_invite_capability", capability)
    app = FastAPI()
    app.include_router(diag_router.router, prefix="/api/v1")
    app.dependency_overrides[diag_router._service] = lambda: Service()
    app.dependency_overrides[get_db] = lambda: _Db(session)
    client = TestClient(app)
    client.seen = seen
    return client


def read(client, code=CODE, ip="203.0.113.7", **kw):
    headers = {"X-Real-IP": ip}
    if code is not None:
        headers["X-Diagnostic-Invite-Code"] = code
    return client.get(URL, headers=headers, **kw)


# ── S-02 ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_s02_the_report_is_read_with_the_invite_code_in_the_header(api):
    r = read(api)
    assert r.status_code == 200 and r.json()["session_id"] == str(SESSION_ID)
    assert api.seen["capability_codes"] == [CODE]
    # the URL of the request carries nothing
    assert "invite_code" not in str(r.request.url) and CODE not in str(r.request.url)


def test_s02_a_page_loaded_before_the_deploy_still_reads_with_the_query_code(api):
    r = api.get(URL, params={"invite_code": CODE}, headers={"X-Real-IP": "203.0.113.7"})
    assert r.status_code == 200


def test_s02_no_code_at_all_is_not_found_not_a_server_error(api):
    assert read(api, code=None).status_code == 404
    assert read(api, code="WRONGCODE9").status_code == 404


def test_s02_the_header_wins_over_a_query_code(api):
    r = api.get(URL, params={"invite_code": "WRONGCODE9"}, headers={"X-Real-IP": "203.0.113.7", "X-Diagnostic-Invite-Code": CODE})
    assert r.status_code == 200


# ── S-03 ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_s03_wrong_codes_for_a_session_are_braked_per_address(api):
    for i in range(FAILS_PER_MINUTE.count):
        assert read(api, code=f"WRONG{i:05d}").status_code == 404
    refused = read(api, code="WRONG99999")
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == TOO_MANY_CODE
    assert 1 <= int(refused.headers["Retry-After"]) <= 60
    # the address that walks waits even with the right code ...
    assert read(api).status_code == 429
    # ... another address does not
    assert read(api, ip="198.51.100.9").status_code == 200


def test_s03_a_class_polling_its_ready_reports_is_never_braked(api):
    """40 reads per student x 30 students behind one NAT: 1200 valid reads cost nothing."""
    for _ in range(1200):
        assert read(api, ip="203.0.113.50").status_code == 200


def test_s03_one_mistyped_code_does_not_hurt_a_class(api):
    for i in range(5):
        assert read(api, code=f"TYPO{i:06d}", ip="203.0.113.60").status_code == 404
    assert read(api, ip="203.0.113.60").status_code == 200


# ── J-01 ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout
    except FileNotFoundError:  # a container without git: the working-tree checks above still hold
        return ""


def _ignore_lines(name):
    path = ROOT / name
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()


def test_j01_report_dumps_are_neither_in_git_nor_in_the_image():
    assert "backups/" in _ignore_lines(".gitignore")
    assert "backups/" in _ignore_lines(".dockerignore")
    assert not (ROOT / "backups").exists() or not any((ROOT / "backups").rglob("*.json"))
    tracked = _git("ls-files", "backups")
    if _git("rev-parse", "--is-inside-work-tree").strip() == "true":
        assert tracked.strip() == ""

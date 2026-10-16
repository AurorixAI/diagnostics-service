"""#77: the public invite-code entry must not be a brute-force oracle.

The code (8 characters, 31-letter alphabet) is a capability and the public endpoints answer differently for an
unknown and a known code.  auth-service cannot throttle by the student's address (we call it server-to-server), so
diagnostic-service budgets FAILED lookups per client address, caps the volume per address and per code, and answers
429 + Retry-After.  A class behind one school NAT opening valid codes must not notice.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api import router as diag_router
from src.core import abuse_limit, access
from src.core.abuse_limit import (
    ATTEMPTS_PER_MINUTE,
    CODE_PER_HOUR,
    FAILS_PER_HOUR,
    FAILS_PER_MINUTE,
    client_ip,
    code_key,
    counters,
    limit_bucket,
)

TOO_MANY = "Слишком много попыток. Подождите минуту и попробуйте снова."
GRADE = 9
TASK = {
    "task_id": "T1", "skill_id": "S1", "topic_id": "TP1", "question_text": "2+2", "answer_type": "numeric",
    "phase": "warmup", "items_answered": 0, "items_max": 42,
}


def code_of(i: int) -> str:
    return f"CLS{i:05d}"


def student_of(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


def _invite(i: int, status: str = "confirmed", expires_in: timedelta = timedelta(hours=1)) -> dict:
    return {
        "status": status, "student_id": student_of(i), "class_level": GRADE,
        "expires_at": (datetime.now(timezone.utc) + expires_in).isoformat(),
    }


@pytest.fixture
def api(monkeypatch):
    """The three public endpoints with a scripted auth-service and a service that has no attempt yet."""
    invites: dict[str, dict] = {code_of(i): _invite(i) for i in range(60)}
    calls = {"auth": 0}

    class AuthProjection:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url):
            calls["auth"] += 1
            invite = invites.get(unquote(str(url).rsplit("/", 1)[1]))
            return httpx.Response(404) if invite is None else httpx.Response(200, json=dict(invite))

    class Service:
        session_repo = SimpleNamespace(get_by_invite_code=lambda code: None)

        def get_active_session(self, code):
            return None

        def create_session(self, **kwargs):
            return uuid.uuid4(), dict(TASK)

    monkeypatch.setattr(access.httpx, "AsyncClient", AuthProjection)
    app = FastAPI()
    app.include_router(diag_router.router, prefix="/api/v1")
    app.dependency_overrides[diag_router._service] = lambda: Service()
    with TestClient(app) as client:
        client.invites, client.calls = invites, calls
        yield client


def resolve(client, code, ip="203.0.113.7"):
    return client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": code}, headers={"X-Real-IP": ip})


def active(client, code, ip="203.0.113.7"):
    return client.get("/api/v1/diagnostic/sessions/active", params={"invite_code": code}, headers={"X-Real-IP": ip})


def create(client, code, student_id, ip="203.0.113.7", grade=GRADE):
    return client.post(
        "/api/v1/diagnostic/sessions",
        json={"student_id": student_id, "grade_level": grade, "invite_code": code},
        headers={"X-Real-IP": ip},
    )


def guess(n: int) -> str:
    return f"NOPE{n:05d}"


# ── the client address ───────────────────────────────────────────────────────────────────────────────────

def _req(headers=None, peer="10.0.0.9"):
    return SimpleNamespace(headers={k.lower(): v for k, v in (headers or {}).items()}, client=SimpleNamespace(host=peer))


class TestClientAddress:
    def test_real_ip_wins_and_forwarded_for_is_never_trusted(self):
        assert client_ip(_req({"X-Real-IP": "198.51.100.4", "X-Forwarded-For": "1.2.3.4"})) == "198.51.100.4"
        assert client_ip(_req({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})) == "10.0.0.9"

    def test_garbage_real_ip_falls_back_to_the_peer(self):
        assert client_ip(_req({"X-Real-IP": "not-an-ip"})) == "10.0.0.9"

    def test_ipv6_by_its_64_and_mapped_ipv4_as_ipv4(self):
        assert limit_bucket("2001:db8:1:2:aaaa::1") == limit_bucket("2001:db8:1:2:bbbb::2") == "2001:db8:1:2::/64"
        assert limit_bucket("2001:db8:1:3::1") != limit_bucket("2001:db8:1:2::1")
        assert limit_bucket("::ffff:203.0.113.7") == "203.0.113.7"

    def test_the_code_never_becomes_a_key(self):
        key = code_key("A2TEST0001")
        assert "A2TEST0001" not in key and len(key) == len(code_key("x" * 50_000))


class _Clock:
    def __init__(self, monkeypatch):
        self.now = 1000.0
        monkeypatch.setattr(abuse_limit, "_now", lambda: self.now)


class _BrokenRedis:
    def eval(self, *args, **kwargs):
        raise ConnectionError("redis is down")

    def pipeline(self):
        raise ConnectionError("redis is down")


class TestCounters:
    def test_window_counts_and_expires(self, monkeypatch):
        clock = _Clock(monkeypatch)
        assert counters.hit("k", 60) == (1, 60)
        clock.now += 20
        assert counters.hit("k", 60) == (2, 40)
        assert counters.peek("k") == (2, 40)
        clock.now += 41
        assert counters.peek("k") == (0, 0)

    def test_redis_down_falls_back_to_memory_with_one_warning(self, caplog):
        counters.use_redis(_BrokenRedis())
        with caplog.at_level("WARNING", logger="diagnostic_service.abuse_limit"):
            for _ in range(4):
                counters.hit("k", 60)
        assert counters.peek("k")[0] == 4
        assert len([r for r in caplog.records if "abuse_limit_redis_unavailable" in r.getMessage()]) == 1

    @pytest.mark.skipif(not os.getenv("RATE_LIMIT_REDIS_URL"), reason="set RATE_LIMIT_REDIS_URL to run against a real Redis")
    def test_real_redis_script(self):
        import redis

        client = redis.from_url(os.environ["RATE_LIMIT_REDIS_URL"], decode_responses=True)
        client.delete("rlt:k")
        counters.use_redis(client)
        try:
            assert counters.hit("rlt:k", 60)[0] == 1
            count, ttl = counters.hit("rlt:k", 60)
            assert count == 2 and 0 < ttl <= 60
            assert counters.peek("rlt:k")[0] == 2 and counters.peek("rlt:none") == (0, 0)
        finally:
            client.delete("rlt:k")

    def test_memory_does_not_grow_without_bound(self, monkeypatch):
        monkeypatch.setattr(abuse_limit, "_MEMORY_SOFT_LIMIT", 50)
        monkeypatch.setattr(abuse_limit, "_MEMORY_HARD_LIMIT", 100)
        for i in range(1000):
            counters.hit(f"flood:{i}", 3600)
        assert len(counters._memory) <= 100


# ── a class behind one NAT ───────────────────────────────────────────────────────────────────────────────

class TestLegitimateClassIsNotLockedOut:
    def test_thirty_students_open_their_codes_in_one_minute_from_one_address(self, api):
        """by-invite (no attempt yet: 404 SESSION_NOT_FOUND is the normal answer) + create a session, x 30."""
        for i in range(30):
            lookup = resolve(api, code_of(i))
            assert lookup.status_code == 404 and lookup.json()["detail"]["code"] == "SESSION_NOT_FOUND"
            started = create(api, code_of(i), student_of(i))
            assert started.status_code == 201, (i, started.text)

    def test_page_reloads_and_restores_are_not_failures(self, api):
        for _ in range(3):
            for i in range(20):
                assert resolve(api, code_of(i)).status_code == 404
                assert active(api, code_of(i)).status_code == 404

    def test_a_few_mistyped_codes_in_the_class_are_fine(self, api):
        for n in range(5):
            assert resolve(api, guess(n)).status_code == 403
        for i in range(30):
            assert create(api, code_of(i), student_of(i)).status_code == 201

    def test_expired_and_used_invites_are_states_not_guesses(self, api):
        api.invites[code_of(0)] = _invite(0, status="expired", expires_in=timedelta(hours=-1))
        api.invites[code_of(1)] = _invite(1, status="completed")
        api.invites[code_of(2)] = _invite(2, status="pending")
        for _ in range(FAILS_PER_MINUTE.count + 5):
            assert create(api, code_of(0), student_of(0)).status_code in (409, 410)
            assert create(api, code_of(1), student_of(1)).status_code == 409
            assert create(api, code_of(2), student_of(2)).status_code == 409
        # the budget of failed lookups is untouched: a valid code still opens
        assert create(api, code_of(3), student_of(3)).status_code == 201


# ── the brute force ─────────────────────────────────────────────────────────────────────────────────────

class TestGuessingIsBudgeted:
    def test_the_twenty_first_wrong_code_in_a_minute_is_refused(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            assert resolve(api, guess(n)).status_code == 403
        refused = resolve(api, guess(999))
        assert refused.status_code == 429
        assert refused.json()["detail"] == {"code": "TOO_MANY_ATTEMPTS", "message": TOO_MANY, "action": "retry"}
        assert 1 <= int(refused.headers["Retry-After"]) <= 60

    def test_a_walk_reaches_auth_service_only_budget_times(self, api):
        """Auth-service sees at most the failure budget of a single address, however long the walk goes."""
        for n in range(500):
            resolve(api, guess(n))
        assert api.calls["auth"] == FAILS_PER_MINUTE.count

    def test_a_valid_code_from_the_same_address_waits_too(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n))
        assert resolve(api, code_of(0)).status_code == 429

    def test_another_address_is_not_affected(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n))
        assert resolve(api, code_of(0), ip="198.51.100.9").status_code == 404

    def test_all_three_entries_share_the_budget(self, api):
        resolve(api, guess(1)), active(api, guess(2)), create(api, guess(3), student_of(0))
        for n in range(FAILS_PER_MINUTE.count - 3):
            resolve(api, guess(10 + n))
        for refused in (resolve(api, code_of(0)), active(api, code_of(0)), create(api, code_of(0), student_of(0))):
            assert refused.status_code == 429

    def test_the_budget_comes_back(self, api, monkeypatch):
        clock = _Clock(monkeypatch)
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n))
        assert resolve(api, code_of(0)).status_code == 429
        clock.now += 61
        assert resolve(api, code_of(0)).status_code == 404

    def test_the_hour_budget_holds_when_the_minute_budget_is_respected(self, api, monkeypatch):
        clock = _Clock(monkeypatch)
        spent = 0
        while spent < FAILS_PER_HOUR.count:
            for _ in range(FAILS_PER_MINUTE.count):
                if spent == FAILS_PER_HOUR.count:
                    break
                assert resolve(api, guess(spent)).status_code == 403
                spent += 1
            clock.now += 61
        refused = resolve(api, code_of(0))
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) > 60
        assert "мин" in refused.json()["detail"]["message"]

    def test_a_known_code_with_another_student_or_grade_is_a_guess_too(self, api):
        for n in range(FAILS_PER_MINUTE.count // 2):
            assert create(api, code_of(0), student_of(1)).status_code == 403          # INVITE_STUDENT_MISMATCH
            assert create(api, code_of(0), student_of(0), grade=GRADE + 1).status_code == 403  # INVITE_GRADE_MISMATCH
        assert resolve(api, code_of(5)).status_code == 429

    def test_spoofed_forwarded_for_does_not_open_a_new_bucket(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            response = api.get(
                "/api/v1/diagnostic/sessions/by-invite", params={"invite_code": guess(n)},
                headers={"X-Real-IP": "203.0.113.7", "X-Forwarded-For": f"10.{n}.0.1"},
            )
            assert response.status_code == 403
        refused = api.get(
            "/api/v1/diagnostic/sessions/by-invite", params={"invite_code": code_of(0)},
            headers={"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "192.0.2.77"},
        )
        assert refused.status_code == 429

    def test_ipv6_addresses_of_one_subscriber_share_a_bucket(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n), ip=f"2001:db8:5:6:{n:x}::1")
        assert resolve(api, code_of(0), ip="2001:db8:5:6:ffff::9").status_code == 429
        assert resolve(api, code_of(0), ip="2001:db8:5:7::9").status_code == 404


class TestVolumeCaps:
    def test_one_code_is_capped_per_hour_from_every_address(self, api):
        for n in range(CODE_PER_HOUR.count):
            assert resolve(api, code_of(0), ip=f"198.51.100.{n % 250 + 1}").status_code == 404
        refused = resolve(api, code_of(0), ip="192.0.2.200")
        assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 60
        assert resolve(api, code_of(1), ip="192.0.2.200").status_code == 404  # another code is untouched

    def test_a_flood_from_one_address_is_capped_above_a_class(self, api):
        ok = 0
        for n in range(ATTEMPTS_PER_MINUTE.count + 5):
            response = resolve(api, code_of(n % 50))
            if response.status_code == 429:
                break
            ok += 1
        assert ok == ATTEMPTS_PER_MINUTE.count
        assert response.status_code == 429 and "Retry-After" in response.headers


class TestNothingLeaks:
    def test_a_429_carries_no_student_data_and_not_the_code(self, api):
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n))
        refused = resolve(api, code_of(7))
        assert refused.status_code == 429
        assert code_of(7) not in refused.text and student_of(7) not in refused.text

    def test_the_code_is_not_logged_when_a_lookup_is_refused(self, api, caplog):
        for n in range(FAILS_PER_MINUTE.count):
            resolve(api, guess(n))
        with caplog.at_level(logging.DEBUG):
            assert resolve(api, code_of(7)).status_code == 429
        # what the SERVICE logs (the test client's own httpx log line has the URL by construction)
        service_log = " ".join(r.getMessage() for r in caplog.records if r.name != "httpx")
        assert code_of(7) not in service_log and guess(1) not in service_log
        assert "invite_lookup_refused" in service_log

    def test_a_valid_lookup_is_unchanged(self, api):
        started = create(api, code_of(4), student_of(4))
        assert started.status_code == 201
        body = started.json()
        assert set(body) == {"session_id", "first_task"} and body["first_task"]["task_id"] == "T1"

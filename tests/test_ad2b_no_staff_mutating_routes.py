"""AD-2b: no mutating route of diagnostic-service reads the cookie of a staff member - so the source check of mutating requests (auth-service AD-2, exam-service AD-2b) is not
needed here, and this test is what keeps that true.

Today the two mutating routes (``POST /sessions``, ``POST /sessions/{id}/answer``) are held by the invitation code / the session of the student; the cookie of a staff member is
read by the GET analytics only (``require_diagnostic_staff``, ``require_student_report_access``). The day a route that CHANGES something depends on the staff cookie, this test
fails: that route then needs the source check (copy ``exam-service/src/core/origin_guard.py`` and its guard test), not a change of this test.
"""
import inspect

from fastapi.routing import APIRoute
from fastapi.security.base import SecurityBase

from src.core import access
from src.main import app

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Names that mean «the cookie / credential of a staff member is read», in a dependency or in a handler.
STAFF_CALLS = {access.require_diagnostic_staff, access.require_student_report_access}
STAFF_NAMES = ("require_diagnostic_staff", "require_student_report_access", "_forward_auth_headers", "DiagnosticActor", "request.cookies", "Cookie(", "\"cookie\"", "\"authorization\"", "/auth/me")


def _calls(dependant):
    found, direct = set(), bool(dependant.cookie_params)
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(sub.call)
        inner, inner_direct = _calls(sub)
        found |= inner
        direct = direct or inner_direct
    return found, direct


def _routes():
    return [route for route in app.routes if isinstance(route, APIRoute)]


def _staff_reading(route):
    """Why the route reads a staff credential (empty list = it does not)."""
    calls, direct = _calls(route.dependant)
    calls |= {d.dependency for d in route.dependencies}
    why = [f"depends on {getattr(c, '__name__', c)}" for c in calls if c in STAFF_CALLS]
    why += [f"credential dependency {type(c).__name__}" for c in calls if isinstance(c, SecurityBase)]
    if direct:
        why.append("declares a cookie parameter")
    for call in [route.endpoint, *calls]:  # the handler AND the source of every dependency under it
        try:
            source = inspect.getsource(call)
        except (OSError, TypeError):
            continue
        why += [f"{getattr(call, '__name__', call)} mentions {name}" for name in STAFF_NAMES if name in source]
    return why


def test_the_detector_sees_the_staff_routes_it_is_meant_to_find():
    """The test must not be blind: the GET analytics DO read the staff cookie and the detector says so."""
    reports = [r for r in _routes() if r.path == "/api/v1/analytics/students/{student_id}/report"]
    assert reports and _staff_reading(reports[0])


# The mutating routes of diagnostic-service, EXACTLY (method + full path). Both are held by the invitation code / the session of the student.
KNOWN_MUTATING = {
    ("POST", "/api/v1/diagnostic/sessions"),
    ("POST", "/api/v1/diagnostic/sessions/{session_id}/answer"),
}


def test_the_mutating_routes_are_exactly_the_known_ones():
    """Not «look for the bad» but «know the good» (R3 V-1): a staff check can hide in a wrapper dependency, a helper, a header read - no detector names them all. So ANY new
    mutating route fails here with a question, whatever it reads."""
    mutating = {(m, r.path) for r in _routes() for m in r.methods & MUTATING}
    assert mutating == KNOWN_MUTATING, (
        f"the mutating routes changed: new {sorted(mutating - KNOWN_MUTATING)}, gone {sorted(KNOWN_MUTATING - mutating)}. Does a new one need the source check of mutating "
        f"requests (Origin/Referer/Sec-Fetch-Site) because a staff member's cookie decides there? If yes, copy exam-service/src/core/origin_guard.py + its guard test. "
        f"If it is held by an invitation code / a student's session, add it to KNOWN_MUTATING with the reason."
    )


def test_no_mutating_route_depends_on_the_cookie_of_a_staff_member():
    offenders = {f"{m} {r.path}": _staff_reading(r) for r in _routes() for m in sorted(r.methods & MUTATING) if _staff_reading(r)}
    assert not offenders, (
        f"a route that CHANGES something now reads the staff cookie: {offenders}. Give it the source check of mutating requests "
        f"(copy exam-service/src/core/origin_guard.py + tests/test_ad2b_origin_guard.py) - do not just edit this test."
    )

"""Callback warnings never include invite capabilities or exception URLs."""
import logging
import httpx
import pytest
from uvicorn.logging import AccessFormatter
from src.core import auth_client
from src.core.middleware import DiagnosticCapabilityLogFilter


@pytest.mark.parametrize("network_error", [False, True])
def test_failed_callback_logs_safe_session_id_without_invite(monkeypatch, caplog, network_error):
    code = "SECRET-CAPABILITY"
    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, url, **_kwargs):
            if network_error: raise httpx.ConnectError(f"Failed request {url}")
            return httpx.Response(503)
    monkeypatch.setattr(auth_client.httpx, "Client", Client)
    monkeypatch.setattr(auth_client, "_internal_headers", lambda: {"X-Internal-Service-Token": "test-only"})
    with caplog.at_level(logging.WARNING, logger=auth_client.__name__):
        assert auth_client.notify_complete(code, "safe-session-id", {}) is False
    assert "safe-session-id" in caplog.text
    assert code not in caplog.text
    assert "/internal/diagnostic/" not in caplog.text


@pytest.mark.parametrize("url", [
    "/api/v1/auth/diagnostic/SECRET-CAPABILITY",
    "/api/v1/internal/diagnostic/SECRET-CAPABILITY/complete",
    "/api/v1/diagnostic/sessions/by-invite?invite_code=SECRET-CAPABILITY&other=1",
    "/api/v1/diagnostic/sessions/session-id/report?invite_code=SECRET-CAPABILITY",
])
def test_http_and_access_log_filters_redact_capability_but_keep_route(url):
    record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: GET %s", (url,), None)
    assert DiagnosticCapabilityLogFilter().filter(record)
    assert "SECRET-CAPABILITY" not in record.getMessage()
    assert "[redacted]" in record.getMessage()
    assert "HTTP Request: GET" in record.getMessage()


@pytest.mark.parametrize("url", [
    "/api/v1/auth/diagnostic/SECRET-CAPABILITY",
    "/api/v1/internal/diagnostic/SECRET-CAPABILITY/complete",
    "/api/v1/diagnostic/sessions/by-invite?invite_code=SECRET-CAPABILITY",
    "/api/v1/diagnostic/sessions/session-id/report?invite_code=SECRET-CAPABILITY",
])
def test_uvicorn_access_formatter_still_formats_filtered_arguments(url):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1234", "GET", url, "1.1", 200), None)
    DiagnosticCapabilityLogFilter().filter(record)
    formatted = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False).format(record)
    assert "SECRET-CAPABILITY" not in formatted
    assert "[redacted]" in formatted and "200" in formatted and "GET" in formatted
    assert len(record.args) == 5


def test_httpx_url_object_and_status_keep_printf_types():
    record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: %s %s %d",
        ("GET", httpx.URL("http://auth/api/v1/auth/diagnostic/SECRET-CAPABILITY"), 200), None)
    DiagnosticCapabilityLogFilter().filter(record)
    assert "SECRET-CAPABILITY" not in record.getMessage()
    assert record.args[-1] == 200 and "[redacted]" in record.getMessage()


def test_mapping_format_arguments_remain_valid():
    record = logging.LogRecord("httpx", logging.INFO, "", 0, "%(url)s %(status)d",
        ({"url": "/api/v1/auth/diagnostic/SECRET-CAPABILITY", "status": 503},), None)
    DiagnosticCapabilityLogFilter().filter(record)
    assert "SECRET-CAPABILITY" not in record.getMessage()
    assert "[redacted]" in record.getMessage() and "503" in record.getMessage()

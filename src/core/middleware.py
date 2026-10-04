"""
Diagnostic Service — Shared middleware.

  • RequestIDMiddleware  — attaches / generates X-Request-ID per request
  • configure_logging()  — sets up structlog JSON logging (prod) or pretty (dev)
"""
from __future__ import annotations

import logging
import re
import sys
import uuid

import httpx

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class DiagnosticCapabilityLogFilter(logging.Filter):
    """Keep route/status evidence while removing public invite capabilities."""
    _path = re.compile(r'(/(?:api/v1/)?(?:auth/|internal/)?diagnostic/)(?!sessions(?:/|\b))[^/?\s\"\x27]+')
    _query = re.compile(r'([?&]invite_code=)[^&\s\"\x27]+')

    @classmethod
    def _redact(cls, value):
        if not isinstance(value, (str, httpx.URL)):
            return value
        return cls._query.sub(r'\1[redacted]', cls._path.sub(r'\1[redacted]', str(value)))

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Uvicorn AccessFormatter unpacks the five original arguments.
            # Preserve them; redact paths and HTTPX URL objects in place.
            if not record.args:
                record.msg = self._redact(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(self._redact(value) for value in record.args)
            elif isinstance(record.args, dict):
                record.args = {key: self._redact(value) for key, value in record.args.items()}
        return True


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Propagate or generate X-Request-ID and bind it to structlog context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# structlog configuration
# ---------------------------------------------------------------------------

def configure_logging(is_development: bool = False) -> None:
    """Call once at application startup."""
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_development:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(DiagnosticCapabilityLogFilter())
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn.access", "gunicorn.access"):
        logging.getLogger(name).addFilter(DiagnosticCapabilityLogFilter())

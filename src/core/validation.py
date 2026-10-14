"""Diagnostic Service - the 422 response of a request that failed validation.

FastAPI's default handler returns ``exc.errors()`` as is, and every item carries the offending ``input``: a 20 MB
answer that is rejected for being too long came back as a 20 MB response (and a rejected invite code or
free-text field is echoed to whoever sent it).  Same ``{"detail": [...]}`` shape, minus what the client sent.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_MAX_ERRORS = 50
_MAX_TEXT = 200


def _clip(value: Any) -> Any:
    return value[:_MAX_TEXT] if isinstance(value, str) else value


def public_validation_errors(errors: list) -> list:
    """``type``, ``loc``, ``msg`` and ``url`` of each error; ``ctx`` only as far as it holds numeric limits
    (``max_length``...) - never ``input``, never the exception objects that ``ctx`` may carry."""
    result = []
    for error in errors[:_MAX_ERRORS]:
        item = {
            "type": _clip(error.get("type")),
            "loc": [_clip(part) for part in error.get("loc", ())],
            "msg": _clip(error.get("msg")),
        }
        if error.get("url"):
            item["url"] = error["url"]
        ctx = {key: value for key, value in (error.get("ctx") or {}).items()
               if isinstance(value, (int, float)) and not isinstance(value, bool)}
        if ctx:
            item["ctx"] = ctx
        result.append(item)
    return result


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(public_validation_errors(exc.errors()))})

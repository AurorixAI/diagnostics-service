"""
ALGO — Diagnostic Service v1
FastAPI application entry point. Port 8002.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from contextlib import asynccontextmanager

import sqlalchemy
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.core.config import get_settings
from src.core.middleware import RequestIDMiddleware, configure_logging
from src.core.validation import validation_exception_handler
from src.api.router import router as diagnostic_router
from src.api.analytics_router import router as analytics_router

settings = get_settings()
configure_logging(is_development=settings.is_development)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )
    # Docker starts migration_runner before it launches any Uvicorn worker.
    # Keep the switch for direct local ``uvicorn`` development only.
    if os.getenv("RUN_MIGRATIONS_IN_LIFESPAN", "true").lower() == "true":
        try:
            from src.core.migration_runner import main as migrate
            await asyncio.to_thread(migrate)
        except Exception:
            log.exception("Alembic migration failed during startup")
            raise

    # The database table is the report queue.  A durable worker loop makes a
    # report request survive a web-process restart; each job is row-locked in
    # ``process_next_report_job`` so multiple replicas remain safe.
    from src.domain.auth_sync_jobs import process_next_auth_completion_sync
    from src.domain.report_jobs import process_next_report_job

    stop_report_worker = asyncio.Event()

    async def report_worker() -> None:
        while not stop_report_worker.is_set():
            did_report_work = await asyncio.to_thread(process_next_report_job)
            did_sync_work = await asyncio.to_thread(process_next_auth_completion_sync)
            did_work = did_report_work or did_sync_work
            try:
                await asyncio.wait_for(
                    stop_report_worker.wait(),
                    timeout=0.2 if did_work else 2.0,
                )
            except asyncio.TimeoutError:
                pass

    worker_task = asyncio.create_task(report_worker(), name="diagnostic-report-worker")
    yield

    stop_report_worker.set()
    worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await worker_task
    log.info("Diagnostic Service shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# 422 without the rejected input: a long answer must not be echoed back at its full size.
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnostic_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

# Prometheus metrics at /metrics
Instrumentator(excluded_handlers=["/metrics", "/health/live", "/health/ready"]).instrument(app).expose(app)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/health/live", tags=["System"], summary="Liveness probe")
def health_live():
    """Always returns 200 — no dependency checks (for K8s/Docker liveness)."""
    return {"status": "alive"}


@app.get("/version", tags=["System"], summary="Deployed release metadata")
def release_version():
    """Return non-secret metadata for the exact deployed diagnostic release."""
    return {
        "service": "diagnostic-service",
        "app_version": settings.app_version,
        "release_sha": os.getenv("RELEASE_SHA", "unknown"),
        "release_ref": os.getenv("RELEASE_REF", "unknown"),
        "released_at": os.getenv("RELEASED_AT", "unknown"),
    }


@app.get("/health/ready", tags=["System"], summary="Readiness probe")
def health_ready():
    """Returns 200 if DB + Redis are reachable, 503 otherwise."""
    from src.core.database import engine
    from src.core.redis_client import get_redis_client

    db_ok = True
    redis_ok = True

    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception as exc:
        log.warning("Readiness DB check failed: %s", exc)
        db_ok = False

    try:
        get_redis_client().ping()
    except Exception as exc:
        log.warning("Readiness Redis check failed: %s", exc)
        redis_ok = False

    ready = db_ok and redis_ok
    payload = {
        "status": "ready" if ready else "not_ready",
        "version": settings.app_version,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/health", tags=["System"], summary="Health check (legacy)")
def health():
    """Backward-compatible — delegates to readiness check."""
    return health_ready()

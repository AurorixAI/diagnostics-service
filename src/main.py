"""
ALGO — Diagnostic Service v1
FastAPI application entry point. Port 8002.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sqlalchemy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.core.config import get_settings
from src.core.middleware import RequestIDMiddleware, configure_logging
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
    try:
        import subprocess
        target = "head" if settings.standalone else "001_diag_tables"
        result = subprocess.run(
            ["alembic", "upgrade", target],
            capture_output=True, text=True, check=True
        )
        log.info("Alembic migrations applied (target=%s):\n%s", target, result.stdout)
    except subprocess.CalledProcessError as exc:
        log.error("Alembic migration FAILED:\n%s\n%s", exc.stdout, exc.stderr)
    except Exception as exc:
        log.warning("Alembic migration skipped: %s", exc)

    yield

    log.info("Diagnostic Service shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

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

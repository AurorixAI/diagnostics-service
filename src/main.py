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

from src.core.config import get_settings
from src.api.router import router as diagnostic_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )
    # Run Alembic migrations on startup
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        log.info("Alembic migrations applied")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnostic_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
def health():
    """Liveness + dependency check."""
    from src.core.database import engine
    from src.core.redis_client import get_redis_client

    db_ok = "ok"
    redis_ok = "ok"

    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception as exc:
        log.warning("DB health check failed: %s", exc)
        db_ok = "error"

    try:
        get_redis_client().ping()
    except Exception as exc:
        log.warning("Redis health check failed: %s", exc)
        redis_ok = "error"

    overall = "healthy" if db_ok == "ok" and redis_ok == "ok" else "degraded"
    return {
        "status": overall,
        "version": settings.app_version,
        "database": db_ok,
        "redis": redis_ok,
    }

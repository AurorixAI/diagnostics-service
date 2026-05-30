"""Diagnostic Service — Configuration"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "ALGO Diagnostic Service"
    app_version: str = "1.0.0"
    app_env: str = Field(default="production", pattern="^(development|production|testing)$")
    debug: bool = False

    # Database — own DB for sessions/answers
    database_url: str = "postgresql://algo:algo_password@localhost:5432/algo_v1"
    # Content Service — HTTP read API (replaces direct content-db connection)
    content_service_url: str = "http://content-service:8004"

    # Redis — session state (JSON, no Pickle)
    redis_url: str = "redis://localhost:6379"
    redis_session_ttl: int = 7200   # 2 hours
    redis_task_cache_ttl: int = 600  # 10 minutes

    # Gemini AI (stubbed in Phase 1)
    gemini_api_key: str = ""
    gemini_model_eval: str = "gemini-2.0-flash"
    gemini_model_report: str = "gemini-2.0-flash"

    # Algorithm parameters
    warmup_items: int = 3
    max_items: int = 25
    se_threshold: float = 0.30
    deep_scan_importance_threshold: int = 8
    deep_scan_max_items: int = 6
    mastery_threshold: float = 0.6   # min fraction correct to move UP a topic

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    # Auth Service callback URL — for notifying invite status changes
    auth_service_url: str = Field(default="http://localhost:8000")

    # Standalone mode: True  → service owns its own Postgres, runs ALL migrations
    #                  False → connects to monolith DB, runs ONLY owned-table migrations (001)
    standalone: bool = Field(default=True)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()

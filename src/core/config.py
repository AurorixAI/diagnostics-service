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
    app_env: str = Field(default="production", pattern="^(development|staging|production|testing)$")
    debug: bool = False

    # Database — own DB for sessions/answers
    database_url: str = "postgresql://algo:algo_password@localhost:5432/algo_v1"
    # Content Service — HTTP read API (replaces direct content-db connection)
    content_service_url: str = "http://content-service:8004"

    # Redis — session state (JSON, no Pickle)
    redis_url: str = "redis://localhost:6379"
    redis_session_ttl: int = 7200   # 2 hours
    redis_task_cache_ttl: int = 600  # 10 minutes

    # Gemini AI
    gemini_api_key: str = ""
    gemini_model_eval: str = "gemini-2.0-flash"
    gemini_model_report: str = "gemini-2.0-flash"

    # Azure OpenAI / DeepSeek API
    # Credentials must be supplied through the environment.  Never ship a
    # deployable service with an embedded model key.
    azure_deepseek_api_key: str = ""
    azure_deepseek_endpoint: str = ""
    azure_deepseek_model: str = "deepseek-v4-flash"

    # Algorithm parameters
    # A short, cross-section baseline prevents a precise-looking theta from
    # being inferred from one curricular area only.  Every currently supported
    # grade has at most five L1 sections.
    warmup_items: int = 5
    min_items: int = 12
    max_items: int = 42
    se_threshold: float = 0.30
    classification_min_items: int = Field(default=20, ge=1)
    classification_se_threshold: float = Field(default=0.40, gt=0)
    classification_confidence_threshold: float = Field(default=0.90, gt=0, le=1)
    min_section_coverage: int = 5
    deep_scan_importance_threshold: int = 8
    deep_scan_max_items: int = 6
    # Per-SESSION cap on Deep Scan items (env DEEP_SCAN_SESSION_BUDGET). Deep-scan
    # items do not update theta but use up max_items, so unbounded scanning costs
    # accuracy.  A scan cannot start, and a running one stops, once the session's
    # total reaches this value.  The per-scan cap (deep_scan_max_items) still applies.
    deep_scan_session_budget: int = Field(default=6, ge=0)  # sweep 2026-10-07: largest value with accuracy within noise and +0.3 items
    mastery_threshold: float = 0.6   # min fraction correct to move UP a topic

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Auth Service callback URL — for notifying invite status changes
    auth_service_url: str = Field(default="http://localhost:8000")
    # Shared only with auth-service. Required for all mutable internal
    # callbacks; public diagnostic invite codes are never accepted there.
    internal_service_token: str = ""

    # Standalone mode: True  → service owns its own Postgres, runs ALL migrations
    #                  False → connects to monolith DB, runs ONLY owned-table migrations (001)
    standalone: bool = Field(default=True)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()

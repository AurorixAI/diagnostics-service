"""Diagnostic Service — Configuration"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

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
    # ── Deep Scan variants (DIAG-1 stage 2) ──────────────────────────────────
    # Three independent switches, all overridable from the environment.  The defaults are
    # variant OC15 (owner-approved 2026-10-12): offset 1.5 + 2 confirmation probes, trigger
    # mode unchanged.  Evidence: tools/sim_results/rootcause_stage2_summary.txt, 7 grades x
    # n=1500, paired bootstrap vs the old defaults - false root-cause claims -1.3 pp pooled
    # (G10 11.7% -> 4.6%), accuracy and test length unchanged.  The pre-OC15 behaviour is
    # DEEP_SCAN_PROBE_DIFFICULTY_OFFSET=0.0 and DEEP_SCAN_CONFIRM_PROBES=1.
    #
    # DEEP_SCAN_PROBE_DIFFICULTY_OFFSET: a Deep Scan probe is the unused item whose
    # IRT difficulty is nearest to b = theta - offset (1.5 -> easier probes; 0 -> theta).
    # Only Deep Scan probes are affected; measurement items still target theta.
    deep_scan_probe_difficulty_offset: float = Field(default=1.5, allow_inf_nan=False)
    # DEEP_SCAN_CONFIRM_PROBES: a probed skill is declared a gap only after this many
    # wrong answers on different items of that skill.  A correct answer at any point
    # closes the branch (skill mastered).  A skill that runs out of unused items (or
    # of budget) before confirmation is NOT a gap; it is recorded as unconfirmed.
    # Every extra item counts toward deep_scan_max_items, the session budget and
    # max_items exactly like a first probe.  1 = one wrong answer is a gap (pre-OC15 rule).
    deep_scan_confirm_probes: int = Field(default=2, ge=1)
    # DEEP_SCAN_TRIGGER_MODE: which failed L3 starts a scan.
    #   "importance"  - L3 importance >= deep_scan_importance_threshold (current rule);
    #   "hard_prereq" - the failed L3 has at least one HARD prerequisite edge,
    #                   whatever its importance.
    deep_scan_trigger_mode: Literal["importance", "hard_prereq"] = "importance"
    # ── Deep Scan trigger discrimination (DIAG-1 stage 3b) ───────────────────────
    # The defaults reproduce the previous behaviour exactly.  Measured on the stage-3a baseline:
    # the current rule fires for 93-100 % of students with and without a gap because ONE wrong
    # answer in an important L3 fails it; the rules below ask for more evidence.
    #
    # DEEP_SCAN_TRIGGER_RULE: what a FAILED L3 (score < mastery) must also show to start a scan; it is
    # applied on top of the DEEP_SCAN_TRIGGER_MODE gate (importance / hard prerequisite), not instead of it.
    #   "current" - nothing more (a failing skill is enough);
    #   "d1"      - >= 2 wrong answers in the L3, or 1 when the L3 has a single L4 skill;
    #   "d2"      - residual sum(p_hat - x) over the L3's answers >= DEEP_SCAN_RESIDUAL_MIN, where p_hat is the
    #               3PL probability of a correct answer at the theta BEFORE that answer (x = 1 correct, 0 wrong):
    #               the student did worse than the model expected, not merely failed an L3.
    deep_scan_trigger_rule: Literal["current", "d1", "d2"] = "current"
    # gt=0 on purpose: 0 does NOT switch the rule off (a residual >= 0 would fire for most failed visits; "off" is
    # DEEP_SCAN_TRIGGER_RULE=current), unlike PROBE_MIN_P and HARD_PREREQ_MIN_GRADE where 0 means "off".
    deep_scan_residual_min: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    # DEEP_SCAN_PROBE_MIN_P (D3): a Deep Scan probe whose expected probability of a correct answer
    # (3PL at the student's current theta and the selected item's parameters) is below this value is
    # not spent: the skill is skipped like a skill without an unused item.  0 = off.
    deep_scan_probe_min_p: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    # DEEP_SCAN_HARD_PREREQ_MIN_GRADE (DIAG-1 grade gate): with TRIGGER_MODE="hard_prereq", the grade
    # from which that mode applies.  A session whose grade_level is below this value uses the default
    # mode ("importance") instead.  0 = no grade limit (hard_prereq in every grade, the previous behaviour).
    # Frozen per session like the other Deep Scan flags.
    deep_scan_hard_prereq_min_grade: int = Field(default=0, ge=0, le=11)
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

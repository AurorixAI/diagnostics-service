"""
Diagnostic Service — Gemini AI Client

Fire-and-forget: errors are logged but NEVER raised (don't break the CAT flow).
Uses google-generativeai SDK (API key auth), not Vertex AI.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.core.config import get_settings

log = logging.getLogger(__name__)


def call_gemini(prompt: str, model: Optional[str] = None, temperature: float = 0.4, max_tokens: int = 1024) -> Optional[str]:
    """
    Calls Gemini and returns text response.
    Returns None on any error — callers must handle gracefully.
    """
    settings = get_settings()
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        log.warning("GEMINI_API_KEY not set — skipping AI call")
        return None

    mdl = model or settings.gemini_model_report

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        client = genai.GenerativeModel(
            model_name=mdl,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        response = client.generate_content(prompt)
        return response.text.strip() if response.text else None
    except Exception as exc:
        log.warning("Gemini call failed (fire-and-forget): %s", exc)
        return None

"""
Diagnostic Service — AI Client (Azure OpenAI / DeepSeek Primary, Gemini Fallback)
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Optional

from src.core.config import get_settings

log = logging.getLogger(__name__)


SERVICE = "diagnostic"
_OFF_VALUES = {"false", "0", "no", "off", "disabled"}


def narrative_enabled() -> bool:
    """The ONE place where REPORT_NARRATIVE_ENABLED is read (default: on).

    Only an explicit "false" / "0" / "no" / "off" switches paid narrative calls off.
    """
    value = str(get_settings().report_narrative_enabled or "").strip().lower()
    return value not in _OFF_VALUES


def _log_paid_call(purpose: str, provider: str, model: str, started: float, ok: bool) -> None:
    """One line per paid request.  Never the prompt, the response or any student data."""
    log.info(
        "paid_llm_call service=%s purpose=%s provider=%s model=%s duration_ms=%d ok=%s",
        SERVICE, purpose, provider, model, int((time.monotonic() - started) * 1000), "true" if ok else "false",
    )


def call_gemini(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.45,
    max_tokens: int = 1024,
    purpose: str = "report_narrative",
) -> Optional[str]:
    """
    Calls Azure OpenAI / DeepSeek to generate diagnostic report narrative.
    Falls back to Gemini if Azure fails.
    Returns None on any error (fire-and-forget).
    """
    settings = get_settings()
    if not narrative_enabled():
        log.info("paid_llm_call skipped: REPORT_NARRATIVE_ENABLED is off (service=%s purpose=%s)", SERVICE, purpose)
        return None

    # 1. Primary: Azure OpenAI / DeepSeek
    azure_key = settings.azure_deepseek_api_key.strip()
    azure_url = settings.azure_deepseek_endpoint.strip()
    if azure_key and azure_url:
        started = time.monotonic()
        ok = False
        try:
            import requests

            payload = {
                "model": settings.azure_deepseek_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            headers = {
                "Content-Type": "application/json",
                "api-key": azure_key,
                "Authorization": f"Bearer {azure_key}"
            }
            resp = requests.post(azure_url, json=payload, headers=headers, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                if text:
                    ok = True
                    log.info("Successfully generated report narrative via Azure OpenAI/DeepSeek (%d chars)", len(text))
                    return text
            else:
                log.warning("Azure OpenAI returned HTTP %d: %s", resp.status_code, resp.text[:300])
        except Exception as exc:
            log.warning("Azure OpenAI call failed: %s — trying Gemini fallback...", exc)
        finally:
            _log_paid_call(purpose, "azure", settings.azure_deepseek_model, started, ok)

    # 2. Fallback: Gemini AI
    gemini_key = settings.gemini_api_key.strip()
    if not gemini_key:
        log.warning("Neither Azure nor Gemini API keys available for narrative generation")
        return None

    gemini_model = model or settings.gemini_model_report
    started = time.monotonic()
    ok = False
    try:
        import google.generativeai as genai

        genai.configure(api_key=gemini_key)
        client = genai.GenerativeModel(
            model_name=gemini_model,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        response = client.generate_content(prompt)
        text = response.text.strip() if response.text else None
        ok = bool(text)
        return text
    except Exception as exc:
        log.warning("Gemini call failed: %s", exc)
        return None
    finally:
        _log_paid_call(purpose, "gemini", gemini_model, started, ok)

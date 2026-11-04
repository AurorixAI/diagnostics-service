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
_ON_VALUES = {"", "true", "1", "yes", "on", "enabled"}

# One request to either provider.  Without a limit a hung provider holds the report worker (and its slot) for good.
LLM_REQUEST_TIMEOUT_S = 120


class TruncatedText(str):
    """A model answer that was cut off at ``max_tokens`` (``finish_reason`` = length).  It is a ``str`` - what came back - but a caller that
    asks the same question again with the same limit gets the same cut-off text and pays again: the report generator does not repeat it."""

    truncated = True


def narrative_enabled() -> bool:
    """The ONE place where REPORT_NARRATIVE_ENABLED is read (default: on).

    Only an explicit "false" / "0" / "no" / "off" switches paid narrative calls off.
    """
    value = str(get_settings().report_narrative_enabled or "").strip().lower()
    return value not in _OFF_VALUES


def llm_configured() -> bool:
    """A model can be called at all: an Azure key + endpoint, or a Gemini key (the same conditions ``call_gemini`` checks)."""
    settings = get_settings()
    azure = settings.azure_deepseek_api_key.strip() and settings.azure_deepseek_endpoint.strip()
    return bool(azure or settings.gemini_api_key.strip())


def warn_if_switch_unrecognised() -> bool:
    """Startup check: a value that is neither a known "on" nor a known "off" keeps the model ON (fail-open) - say so loudly.

    Returns True when a warning was logged.
    """
    raw = str(get_settings().report_narrative_enabled or "")
    value = raw.strip().lower()
    if value in _OFF_VALUES or value in _ON_VALUES:
        return False
    log.warning(
        "REPORT_NARRATIVE_ENABLED has an unrecognised value %r: treated as ON (paid report calls are ENABLED). "
        "Use false/0/no/off to switch them off.", raw[:40],
    )
    return True


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
            resp = requests.post(azure_url, json=payload, headers=headers, timeout=LLM_REQUEST_TIMEOUT_S)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                if data["choices"][0].get("finish_reason") == "length":
                    # cut off at max_tokens: not valid JSON.  Marked, so that the caller does not ask again with the same limit.
                    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
                    log.warning(
                        "Azure OpenAI answer was cut off at max_tokens=%s (purpose=%s, completion_tokens=%s, chars=%d)",
                        max_tokens, purpose, usage.get("completion_tokens"), len(text),
                    )
                    text = TruncatedText(text)
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
        response = client.generate_content(prompt, request_options={"timeout": LLM_REQUEST_TIMEOUT_S})
        text = response.text.strip() if response.text else None
        ok = bool(text)
        try:
            reason = response.candidates[0].finish_reason
            if text and getattr(reason, "name", str(reason)) in ("MAX_TOKENS", "2"):
                log.warning("Gemini answer was cut off at max_output_tokens=%s (purpose=%s, chars=%d)", max_tokens, purpose, len(text))
                text = TruncatedText(text)
        except Exception:
            pass
        return text
    except Exception as exc:
        log.warning("Gemini call failed: %s", exc)
        return None
    finally:
        _log_paid_call(purpose, "gemini", gemini_model, started, ok)

"""N03b-1 R3: the request timeout of the Gemini fallback is an option the REAL library takes (the other tests use a stand-in)."""
import inspect
import re

from src.core import gemini_client


def test_the_installed_library_takes_request_options_in_generate_content():
    import google.generativeai as genai                      # no stand-in here: this module has no fake wire

    assert getattr(genai, "__version__", "") not in ("", None)
    parameters = inspect.signature(genai.GenerativeModel.generate_content).parameters
    assert "request_options" in parameters, "the pinned library no longer takes request_options: the timeout would be a TypeError"
    assert parameters["request_options"].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_client_passes_exactly_that_option():
    source = inspect.getsource(gemini_client.call_gemini)
    assert re.search(r'generate_content\(prompt, request_options=\{"timeout": LLM_REQUEST_TIMEOUT_S\}\)', source)

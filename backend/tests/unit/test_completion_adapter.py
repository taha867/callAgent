"""voice/adapters/llm/completion.py's CompletionAdapter Protocol + get_completion_adapter()
factory. No real Gemini/OpenAI API call in CI — mirrors verification/adapters/
otp_delivery's "no real SMS vendor in CI" discipline via a FakeCompletionAdapter test
double.
"""

from typing import Any

import pytest

from src.voice import config as voice_config
from src.voice.adapters.llm import get_completion_adapter


class FakeCompletionAdapter:
    """Satisfies the CompletionAdapter Protocol structurally (duck-typed, no explicit
    inheritance needed) — the same shape LogOtpDeliveryAdapter satisfies OtpDeliveryAdapter."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        self.calls.append((system_prompt, user_prompt))
        return self._response


async def test_fake_adapter_satisfies_protocol_shape():
    adapter = FakeCompletionAdapter({"summary": "All resolved."})
    result = await adapter.complete_json(system_prompt="be concise", user_prompt="summarize")
    assert result == {"summary": "All resolved."}
    assert adapter.calls == [("be concise", "summarize")]


def test_get_completion_adapter_returns_gemini_adapter_when_configured(monkeypatch):
    monkeypatch.setattr(voice_config.voice_settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(voice_config.voice_settings, "GEMINI_API_KEY", "fake-key-for-test")

    adapter = get_completion_adapter()

    from src.voice.adapters.llm.gemini_completion import GeminiCompletionAdapter

    assert isinstance(adapter, GeminiCompletionAdapter)


def test_get_completion_adapter_returns_openai_adapter_when_configured(monkeypatch):
    monkeypatch.setattr(voice_config.voice_settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(voice_config.voice_settings, "OPENAI_API_KEY", "fake-key-for-test")

    adapter = get_completion_adapter()

    from src.voice.adapters.llm.openai_completion import OpenAICompletionAdapter

    assert isinstance(adapter, OpenAICompletionAdapter)


def test_get_completion_adapter_raises_for_unimplemented_provider(monkeypatch):
    monkeypatch.setattr(voice_config.voice_settings, "LLM_PROVIDER", "groq_llm")

    with pytest.raises(ValueError, match="groq_llm"):
        get_completion_adapter()


def test_get_completion_adapter_asserts_api_key_present(monkeypatch):
    monkeypatch.setattr(voice_config.voice_settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(voice_config.voice_settings, "GEMINI_API_KEY", None)

    with pytest.raises(AssertionError, match="GEMINI_API_KEY"):
        get_completion_adapter()


def test_get_completion_adapter_asserts_openai_api_key_present(monkeypatch):
    monkeypatch.setattr(voice_config.voice_settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(voice_config.voice_settings, "OPENAI_API_KEY", None)

    with pytest.raises(AssertionError, match="OPENAI_API_KEY"):
        get_completion_adapter()

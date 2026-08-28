"""LLM provider selection — see stt/__init__.py's module docstring for the pattern this
mirrors. Gemini/Groq free tiers are IMPLEMENTATION_PLAN.md's default cost strategy; OpenAI
is a third, paid option (added on direct request, not part of the $0-recurring-spend demo
default) for whoever already holds an OpenAI key. None of the three is the vendor Phase 4/5's
adversarial-resistance hardening re-verifies against (that's Claude, Phase 6), per the phase
file's own Notes section.

Deliberately does NOT take the current system prompt as a constructor argument — Groq's
service has no such parameter, and the prompt changes per turn as verification_level/claim
context evolve (spec §0.3 of .claude/specs/phase-2-backend-spec.md). voice/pipeline.py
carries the current prompt as the first message in the per-call `LLMContext` instead
(portable across both providers), never by reconstructing this service.
"""

from typing import Any

from pipecat.services.llm_service import LLMService

from src.voice.adapters.llm.completion import CompletionAdapter
from src.voice.config import voice_settings


def get_llm_service() -> LLMService[Any]:
    if voice_settings.LLM_PROVIDER == "groq_llm":
        from pipecat.services.groq.llm import GroqLLMService

        assert voice_settings.GROQ_API_KEY, "GROQ_API_KEY is required when LLM_PROVIDER=groq_llm"
        return GroqLLMService(
            api_key=voice_settings.GROQ_API_KEY,
            settings=GroqLLMService.Settings(model="llama-3.3-70b-versatile"),
        )

    if voice_settings.LLM_PROVIDER == "openai":
        from pipecat.services.openai.llm import OpenAILLMService

        assert voice_settings.OPENAI_API_KEY, "OPENAI_API_KEY is required when LLM_PROVIDER=openai"
        return OpenAILLMService(
            api_key=voice_settings.OPENAI_API_KEY,
            settings=OpenAILLMService.Settings(model="gpt-4o-mini"),
        )

    from pipecat.services.google.llm import GoogleLLMService

    assert voice_settings.GEMINI_API_KEY, "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"
    return GoogleLLMService(
        api_key=voice_settings.GEMINI_API_KEY,
        settings=GoogleLLMService.Settings(model="gemini-3.6-flash"),
    )


def get_completion_adapter() -> CompletionAdapter:
    """Phase 3 — the out-of-band adapter completion.py's module docstring describes.
    Deliberately a factory (not a direct construction) so calls/activities.py::
    generate_call_summary never imports a vendor SDK directly, and so tests can
    monkeypatch this one function rather than needing a real Gemini API key — mirrors
    verification/adapters/otp_delivery/__init__.py::get_otp_delivery_adapter's pattern,
    including raising for a provider with no adapter implemented yet."""
    if voice_settings.LLM_PROVIDER == "gemini":
        from src.voice.adapters.llm.gemini_completion import GeminiCompletionAdapter

        assert voice_settings.GEMINI_API_KEY, "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"
        return GeminiCompletionAdapter(api_key=voice_settings.GEMINI_API_KEY)

    if voice_settings.LLM_PROVIDER == "openai":
        from src.voice.adapters.llm.openai_completion import OpenAICompletionAdapter

        assert voice_settings.OPENAI_API_KEY, "OPENAI_API_KEY is required when LLM_PROVIDER=openai"
        return OpenAICompletionAdapter(api_key=voice_settings.OPENAI_API_KEY)

    raise ValueError(
        f"no CompletionAdapter implemented for LLM_PROVIDER={voice_settings.LLM_PROVIDER!r}"
    )

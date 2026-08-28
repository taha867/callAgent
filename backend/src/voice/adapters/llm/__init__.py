"""LLM provider selection — see stt/__init__.py's module docstring for the pattern this
mirrors. Gemini/Groq free tiers per IMPLEMENTATION_PLAN.md's cost strategy — neither is the
vendor Phase 4/5's adversarial-resistance hardening re-verifies against (that's Claude,
Phase 6), per the phase file's own Notes section.

Deliberately does NOT take the current system prompt as a constructor argument — Groq's
service has no such parameter, and the prompt changes per turn as verification_level/claim
context evolve (spec §0.3 of .claude/specs/phase-2-backend-spec.md). voice/pipeline.py
carries the current prompt as the first message in the per-call `LLMContext` instead
(portable across both providers), never by reconstructing this service.
"""

from typing import Any

from pipecat.services.llm_service import LLMService

from src.voice.config import voice_settings


def get_llm_service() -> LLMService[Any]:
    if voice_settings.LLM_PROVIDER == "groq_llm":
        from pipecat.services.groq.llm import GroqLLMService

        assert voice_settings.GROQ_API_KEY, "GROQ_API_KEY is required when LLM_PROVIDER=groq_llm"
        return GroqLLMService(
            api_key=voice_settings.GROQ_API_KEY,
            settings=GroqLLMService.Settings(model="llama-3.3-70b-versatile"),
        )

    from pipecat.services.google.llm import GoogleLLMService

    assert voice_settings.GEMINI_API_KEY, "GEMINI_API_KEY is required when LLM_PROVIDER=gemini"
    return GoogleLLMService(
        api_key=voice_settings.GEMINI_API_KEY,
        settings=GoogleLLMService.Settings(model="gemini-2.0-flash"),
    )

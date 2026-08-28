"""STT provider selection — CLAUDE.md §2.7's swappable-adapter pattern. Each concrete
service is a real Pipecat `STTService` `FrameProcessor` (confirmed via direct package
introspection — `WhisperSTTService`/`GroqSTTService` both subclass `STTService`), placed
directly into `voice/pipeline.py`'s `Pipeline([...])` list — there is no custom Protocol to
implement here, Pipecat's own base class already is the common interface. The demo-vendor
swap (Phase 6) is choosing a different branch below and setting the matching API key, never
a change to `voice/pipeline.py` itself.
"""

from pipecat.services.stt_service import STTService

from src.voice.config import voice_settings


def get_stt_service() -> STTService:
    if voice_settings.STT_PROVIDER == "groq_whisper":
        from pipecat.services.groq.stt import GroqSTTService

        return GroqSTTService(api_key=voice_settings.GROQ_API_KEY)

    from pipecat.services.whisper.stt import WhisperSTTService

    # Self-hosted, CPU-friendly default model — IMPLEMENTATION_PLAN.md's $0-forever demo
    # tier. Phase 6's production swap is a paid-vendor STT service, not a bigger local model.
    return WhisperSTTService(settings=WhisperSTTService.Settings(model="base"))

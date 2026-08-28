"""VoiceConfig — a domain that genuinely needs its own settings gets its own small
BaseSettings subclass instead of bloating src/config.py (CLAUDE.md §2.8), same pattern as
src/verification/config.py. `BACKEND_SOFT_WAIT_MS` (the spec §2.2.1 holding-phrase
threshold) stays on the global Config — voice/pipeline.py is simply its second consumer,
not a reason to duplicate it here (.claude/specs/phase-2-backend-spec.md decision 0.6).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    STT_PROVIDER: str = "whisper"  # "whisper" | "groq_whisper"
    TTS_PROVIDER: str = "piper"  # "piper" (only demo-tier option this phase)
    LLM_PROVIDER: str = "gemini"  # "gemini" | "groq_llm" | "openai"
    TELEPHONY_PROVIDER: str = "browser"  # "browser" (only demo-tier option this phase)

    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    TARGET_TURN_P95_MS: int = 1500
    MODEL_TIMEOUT_MS: int = 5000
    MAX_HOLDING_PHRASES_PER_OPERATION: int = 1
    MAX_CONSECUTIVE_LOW_STT_TURNS: int = 3  # spec §8.9
    STT_LOW_CONFIDENCE_THRESHOLD: float = 0.55
    MAX_ADVERSARIAL_STREAK: int = 3  # spec §2.2.2 rule 9 — persistent adversarial input

    # The browser-demo transport has no real inbound call to trigger a workflow start —
    # voice_server.py starts one for a fixed demo customer/claim via the existing,
    # kill-switch-gated POST /calls endpoint (see backend/voice_server.py).
    VOICE_DEMO_CUSTOMER_ID: str | None = None
    VOICE_DEMO_CLAIM_ID: str | None = None
    BACKEND_BASE_URL: str = "http://localhost:8001"


voice_settings = VoiceConfig()  # type: ignore[call-arg]

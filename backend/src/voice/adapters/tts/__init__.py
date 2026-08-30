"""TTS provider selection — see stt/__init__.py's module docstring for the pattern this
mirrors. Piper is the only demo-tier option this phase (spec's own note that open-source
Arabic TTS quality is a placeholder, evaluated against a community Arabic Piper voice, not
production-final)."""

from pathlib import Path

from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.tts_service import TTSService

# PiperTTSService defaults download_dir to Path.cwd() — inside this project that meant the
# *.onnx voice model files landing directly in backend/ (see .gitignore's own note on this).
# Pinning an explicit, container-home-relative directory keeps them out of the working
# directory and gives docker-compose.yml's voice service a stable path to mount a volume
# over, so the ~145MB/voice download survives a container rebuild instead of repeating it.
_PIPER_DOWNLOAD_DIR = Path.home() / ".cache" / "piper"


def get_tts_service(*, language: str = "en") -> TTSService:
    # Community Arabic Piper voice for Arabic turns; English default otherwise. Both are
    # self-hosted, $0-forever — IMPLEMENTATION_PLAN.md's demo tier.
    voice = "ar_JO-kareem-medium" if language == "ar" else "en_US-ryan-high"
    return PiperTTSService(
        settings=PiperTTSService.Settings(voice=voice), download_dir=_PIPER_DOWNLOAD_DIR
    )

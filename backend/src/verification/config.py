"""VerificationConfig — a domain that genuinely needs its own settings gets its own small
BaseSettings subclass instead of bloating src/config.py (CLAUDE.md §2.8). Defaults mirror
verification/constants.py's module constants; spec §10.3.2's own text says these "must
remain configurable after load and carrier testing."
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.verification.constants import (
    MAX_AUTH_ATTEMPTS,
    MAX_OTP_ATTEMPTS,
    MAX_OTP_SENDS_PER_SESSION,
    OTP_LOCKOUT_MINUTES,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
)


class VerificationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    MAX_AUTH_ATTEMPTS: int = MAX_AUTH_ATTEMPTS
    OTP_TTL_SECONDS: int = OTP_TTL_SECONDS
    MAX_OTP_SENDS_PER_SESSION: int = MAX_OTP_SENDS_PER_SESSION
    MAX_OTP_ATTEMPTS: int = MAX_OTP_ATTEMPTS
    OTP_RESEND_COOLDOWN_SECONDS: int = OTP_RESEND_COOLDOWN_SECONDS
    OTP_LOCKOUT_MINUTES: int = OTP_LOCKOUT_MINUTES

    # "log_only" is the only adapter this phase ships — see
    # verification/adapters/otp_delivery/. A real SMS vendor is a Phase 6 paid-vendor swap.
    OTP_DELIVERY_PROVIDER: str = "log_only"


verification_settings = VerificationConfig()  # type: ignore[call-arg]

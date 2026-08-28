from src.exceptions import CallAgentError


class VerificationError(CallAgentError):
    """Root of the verification exception family."""


class AuthFactorNotConfiguredError(VerificationError):
    """No CustomerAuthFactor row exists for the requested factor_type."""


class OtpResendCooldownError(VerificationError):
    """A resend was requested before OTP_RESEND_COOLDOWN_SECONDS elapsed since the last."""


class OtpSendLimitExceededError(VerificationError):
    """MAX_OTP_SENDS_PER_SESSION already reached for this call session."""


class OtpChallengeNotFoundError(VerificationError):
    pass


class OtpExpiredError(VerificationError):
    pass


class OtpLockedError(VerificationError):
    """MAX_OTP_ATTEMPTS already exceeded — locked_until has not yet passed."""

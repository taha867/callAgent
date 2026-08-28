"""Imports only `enum` — nothing else, same discipline as src/calls/constants.py (this
module is read from inside sandboxed workflow code via calls/activities.py's authentication
stage). The five OTP values are re-declared as configurable fields on
verification/config.py::VerificationConfig — these module constants are just their
defaults, per spec §10.3.2's "these values are deployment defaults and must remain
configurable" (.claude/specs/phase-1-backend-spec.md §6.1).
"""

from enum import StrEnum


class VerificationLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


MAX_AUTH_ATTEMPTS = 2  # spec §10.4

# spec §10.3.2
OTP_TTL_SECONDS = 180
MAX_OTP_SENDS_PER_SESSION = 2
MAX_OTP_ATTEMPTS = 3
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_LOCKOUT_MINUTES = 30

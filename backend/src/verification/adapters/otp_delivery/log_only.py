"""LogOtpDeliveryAdapter — the only OTP delivery adapter this phase ships (no real SMS
vendor exists yet, per .claude/specs/phase-1-backend-spec.md decision 0.7). Logs only that
a code was sent, never the code itself — spec §36 rule 18 / §10.3.2: never log OTP values.

`get_last_sent_code_for_testing` is a deliberate, narrow seam: the Phase 1 fake/text
conversation harness (tests/integration/test_phase1_e2e.py) has no real SMS channel to read
an OTP from, so it needs *some* way to complete an OTP-verification branch end-to-end. This
module-level dict is process-local plain Python state — never persisted, never logged, and
never read by any production code path (verification/service.py never calls this accessor;
only test code does). It is not exposed through the Temporal workflow at all, sandboxed or
otherwise, avoiding the sandbox-import/non-determinism concerns a workflow-level debug query
would raise.
"""

import logging

logger = logging.getLogger("verification.otp_delivery")

_last_sent_codes: dict[str, str] = {}


class LogOtpDeliveryAdapter:
    async def send(self, *, phone_e164: str, code: str) -> None:
        logger.info("OTP dispatched to %s", _mask_phone(phone_e164))
        _last_sent_codes[phone_e164] = code


def get_last_sent_code_for_testing(phone_e164: str) -> str | None:
    """Test-only. See module docstring."""
    return _last_sent_codes.get(phone_e164)


def _mask_phone(phone_e164: str) -> str:
    return f"***{phone_e164[-4:]}" if len(phone_e164) >= 4 else "***"

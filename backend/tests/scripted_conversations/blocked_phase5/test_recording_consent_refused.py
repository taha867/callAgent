"""AdversarialScenarioId.RECORDING_CONSENT_REFUSED — blocked on Phase 5. No RecordingConsent
model exists in src/privacy/ yet; "RECORDING_CONSENT_REFUSED" is a reserved, unhandled name
in calls/constants.py::FUTURE_GLOBAL_INTERRUPTS."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — no src.privacy.RecordingConsent model exists yet.",
    strict=True,
)
def test_refusing_recording_consent_under_a_consent_required_campaign_is_honored():
    from src.privacy.models import RecordingConsent  # noqa: F401

"""AdversarialScenarioId.DSAR_REQUEST — blocked on Phase 5 (.claude/specs/phase-4-backend-spec.md
§0.3): no PrivacyRequest model or DSAR handling service exists anywhere in src/privacy/ yet
(confirmed via read-only exploration — that package currently holds only the redaction
pipeline). strict=True so this mechanically FAILS the day Phase 5 ships PrivacyRequest and
someone forgets to remove this marker, per phases/phase-4-demo-hardening.md's own two-strike
discipline of never leaving a known gap silently unenforced.
"""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — no src.privacy.PrivacyRequest (DSAR) model/service exists yet.",
    strict=True,
)
def test_dsar_request_is_routed_and_acknowledged():
    from src.privacy.service import handle_dsar_request  # noqa: F401

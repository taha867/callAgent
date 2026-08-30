"""AdversarialScenarioId.LEGAL_SENSITIVITY_EVIDENCE_HOLD — blocked on Phase 5. src/risk/
(legal-sensitivity routing + evidence preservation, per CLAUDE.md §2.1) does not exist yet;
"LEGAL_SENSITIVITY_DETECTED" is a reserved, unhandled name in
calls/constants.py::FUTURE_GLOBAL_INTERRUPTS."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — src.risk (legal-sensitivity/evidence-preservation domain) "
    "does not exist yet.",
    strict=True,
)
def test_a_legal_sensitivity_flag_creates_an_evidence_preservation_hold():
    from src.risk import service  # noqa: F401

"""AdversarialScenarioId.VULNERABLE_CUSTOMER_DISCLOSURE — blocked on Phase 5. src/risk/
does not exist yet; DispositionCode.CUSTOMER_VULNERABILITY_INDICATED is enum-only with no
producer, and "CUSTOMER_VULNERABILITY_INDICATED" is a reserved, unhandled name in
calls/constants.py::FUTURE_GLOBAL_INTERRUPTS."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — src.risk (vulnerability routing domain) does not exist yet.",
    strict=True,
)
def test_a_vulnerability_disclosure_routes_to_specialist_support():
    from src.risk import service  # noqa: F401

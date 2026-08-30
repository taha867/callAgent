"""AdversarialScenarioId.FRAUD_SIGNAL_COVERT_ROUTING — blocked on Phase 5. src/risk/ (the
fraud/SIU routing domain per CLAUDE.md §2.1) does not exist at all yet — confirmed via
read-only exploration; DispositionCode.FRAUD_SUSPECTED is enum-only with no producer."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — src.risk (fraud/SIU routing domain) does not exist yet.",
    strict=True,
)
def test_a_fraud_signal_routes_to_siu_without_tipping_off_the_caller():
    from src.risk import service  # noqa: F401

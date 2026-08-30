"""AdversarialScenarioId.COMMUNICATION_SUPPRESSION_REQUEST — blocked on Phase 5.
"COMMUNICATION_SUPPRESSION_REQUEST" is a reserved name in
calls/constants.py::FUTURE_GLOBAL_INTERRUPTS (not yet wired into the workflow), and no
CommunicationSuppression model/service exists anywhere."""

import pytest


@pytest.mark.xfail(
    reason="Blocked on Phase 5 — COMMUNICATION_SUPPRESSION_REQUEST is a reserved, unhandled "
    "FUTURE_GLOBAL_INTERRUPTS name; no CommunicationSuppression model/service exists yet.",
    strict=True,
)
def test_never_call_me_again_is_honored_on_future_campaigns():
    from src.customers.service import register_communication_suppression  # noqa: F401

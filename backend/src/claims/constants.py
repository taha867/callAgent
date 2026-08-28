"""ClaimStage plus everything derived from it that must stay importable from inside
sandboxed Temporal workflow code — RetrySchedulerWorkflow (campaigns/workflows.py, Batch 13)
calls get_status_criticality() directly for spec §6.9's critical-status override.

ClaimStage lives here, not in claims/models.py, for exactly that reason: claims/models.py
imports SQLAlchemy, which is not sandbox-safe (mirrors why src.calls.constants and
src.actions.constants each import "only enum" — see their own docstrings). models.py
imports ClaimStage from here, same as any other of this module's consumers.
"""

from enum import StrEnum


class ClaimStage(StrEnum):
    """All 18 statuses from spec §13, in journey order (A: registration, B: assessment,
    C: approval, D: repair, E: financial, F: closure, plus the 3 exception statuses)."""

    CLAIM_REGISTERED = "CLAIM_REGISTERED"
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING"
    DOCUMENTS_RECEIVED = "DOCUMENTS_RECEIVED"
    SURVEYOR_ASSIGNED = "SURVEYOR_ASSIGNED"
    INSPECTION_SCHEDULED = "INSPECTION_SCHEDULED"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"
    REPAIR_APPROVAL_PENDING = "REPAIR_APPROVAL_PENDING"
    REPAIR_AUTHORIZED = "REPAIR_AUTHORIZED"
    VEHICLE_RECEIVED_AT_GARAGE = "VEHICLE_RECEIVED_AT_GARAGE"
    REPAIR_IN_PROGRESS = "REPAIR_IN_PROGRESS"
    ADDITIONAL_APPROVAL_REQUIRED = "ADDITIONAL_APPROVAL_REQUIRED"
    REPAIR_COMPLETED = "REPAIR_COMPLETED"
    SETTLEMENT_APPROVED = "SETTLEMENT_APPROVED"
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    CLAIM_CLOSED = "CLAIM_CLOSED"
    CLAIM_DELAYED = "CLAIM_DELAYED"
    CLAIM_DECLINED = "CLAIM_DECLINED"
    ADDITIONAL_INFORMATION_REQUIRED = "ADDITIONAL_INFORMATION_REQUIRED"


# spec §13 Journey E — "higher authentication may be required for financial detail." Used by
# claims/service.py::get_disclosable_status() to redact settlement_amount below Level 2.
FINANCIAL_STAGES: frozenset[ClaimStage] = frozenset(
    {ClaimStage.SETTLEMENT_APPROVED, ClaimStage.PAYMENT_INITIATED}
)

# spec §6.9's critical-status override — used by RetrySchedulerWorkflow after the final
# automated attempt to decide NORMAL (digital channel/close) vs. ACTION_REQUIRED (human
# follow-up task) vs. URGENT (priority human follow-up).
_ACTION_REQUIRED_STAGES: frozenset[ClaimStage] = frozenset(
    {
        ClaimStage.ADDITIONAL_APPROVAL_REQUIRED,
        ClaimStage.ADDITIONAL_INFORMATION_REQUIRED,
        ClaimStage.SETTLEMENT_APPROVED,
    }
)
_URGENT_STAGES: frozenset[ClaimStage] = frozenset({ClaimStage.CLAIM_DECLINED})


def get_status_criticality(stage: ClaimStage) -> str:
    """Pure lookup — "NORMAL" | "ACTION_REQUIRED" | "URGENT"."""
    if stage in _URGENT_STAGES:
        return "URGENT"
    if stage in _ACTION_REQUIRED_STAGES:
        return "ACTION_REQUIRED"
    return "NORMAL"

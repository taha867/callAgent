"""create_complaint() — task 7, idempotent (spec §10.6.4) create that computes both SLA
due-at timestamps deterministically inside the same idempotent operation closure, so a
retried creation never recomputes a different deadline on replay (the first successful
computation is what the idempotency record freezes and returns). Per CLAUDE.md §2.4,
acknowledgment_due_at/resolution_due_at are never client-supplied — there is no parameter
for either; this function is the only place that computes them.

Starting complaints/workflows.py::ComplaintSlaMonitorWorkflow is the CALLER's job, not
this function's — calls/workflows.py starts it as an ABANDON-policy child (live-call path),
complaints/router.py starts it as a plain top-level workflow via a Temporal client
(dashboard/API path). This function only ever performs the DB write.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.complaints.config import ComplaintsConfig
from src.complaints.models import Complaint
from src.idempotency import idempotent


async def create_complaint(
    session: AsyncSession,
    *,
    key: str,
    correlation_id: str,
    claim_id: str,
    source_call_id: str,
    complaint_category: str,
    customer_statement_summary: str,
    severity: str,
    preferred_contact_method: str,
    now: datetime,
    config: ComplaintsConfig,
    customer_expected_resolution: str | None = None,
) -> dict[str, Any]:
    async def _operation() -> dict[str, Any]:
        complaint = Complaint(
            claim_id=claim_id,
            source_call_id=source_call_id,
            complaint_category=complaint_category,
            customer_statement_summary=customer_statement_summary,
            customer_expected_resolution=customer_expected_resolution,
            severity=severity,
            preferred_contact_method=preferred_contact_method,
            acknowledgment_due_at=now + timedelta(hours=config.ACKNOWLEDGMENT_SLA_HOURS),
            resolution_due_at=now + timedelta(days=config.RESOLUTION_SLA_DAYS),
            sla_source="INSURER_CONFIGURED",
        )
        session.add(complaint)
        await session.flush()
        return {
            "id": complaint.id,
            "claim_id": complaint.claim_id,
            "source_call_id": complaint.source_call_id,
            "complaint_category": complaint.complaint_category,
            "customer_statement_summary": complaint.customer_statement_summary,
            "customer_expected_resolution": complaint.customer_expected_resolution,
            "severity": complaint.severity,
            "preferred_contact_method": complaint.preferred_contact_method,
            "status": complaint.status,
            "acknowledgment_due_at": complaint.acknowledgment_due_at.isoformat(),
            "resolution_due_at": complaint.resolution_due_at.isoformat(),
            "sla_source": complaint.sla_source,
            "created_at": complaint.created_at.isoformat(),
        }

    return await idempotent(
        session,
        key=key,
        correlation_id=correlation_id,
        operation_name="create_complaint",
        payload={
            "claim_id": claim_id,
            "complaint_category": complaint_category,
            "customer_statement_summary": customer_statement_summary,
            "severity": severity,
        },
        operation=_operation,
    )

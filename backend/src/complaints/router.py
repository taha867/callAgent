"""POST /complaints, GET /complaints/{complaintId} — spec §27's Complaints section.

POST /complaints also starts ComplaintSlaMonitorWorkflow (spec §18.1), same as
calls/workflows.py's COMPLAINT_REQUEST branch does for the live-call path — but as a plain
top-level workflow via a Temporal client (src/temporal_client.py), not an ABANDON-policy
child, since a FastAPI route never runs inside a workflow context and cannot use
workflow.start_child_workflow. Safe to connect via settings.TEMPORAL_HOST here specifically
because a router handler never runs inside a test's ephemeral time-skipping Temporal server
the way an activity might — see src/temporal_client.py's module docstring.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.complaints import service as complaints_service
from src.complaints.config import ComplaintsConfig
from src.complaints.dependencies import valid_complaint
from src.complaints.models import Complaint
from src.complaints.schemas import ComplaintCreate, ComplaintRead
from src.complaints.workflows import ComplaintSlaMonitorInput, ComplaintSlaMonitorWorkflow
from src.config import settings
from src.database import get_db
from src.temporal_client import get_temporal_client

router = APIRouter()


@router.post("", response_model=ComplaintRead)
async def create_complaint(
    body: ComplaintCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> ComplaintRead:
    result = await complaints_service.create_complaint(
        db,
        key=f"{body.source_call_id}-COMPLAINT-{body.claim_id}",
        correlation_id=body.source_call_id,
        claim_id=body.claim_id,
        source_call_id=body.source_call_id,
        complaint_category=body.complaint_category,
        customer_statement_summary=body.customer_statement_summary,
        severity=body.severity,
        preferred_contact_method=body.preferred_contact_method,
        now=datetime.now(UTC).replace(tzinfo=None),
        config=ComplaintsConfig(),
        customer_expected_resolution=body.customer_expected_resolution,
    )

    client = await get_temporal_client()
    await client.start_workflow(
        ComplaintSlaMonitorWorkflow.run,
        ComplaintSlaMonitorInput(
            complaint_id=result["id"],
            claim_id=body.claim_id,
            acknowledgment_due_at=datetime.fromisoformat(result["acknowledgment_due_at"]),
            resolution_due_at=datetime.fromisoformat(result["resolution_due_at"]),
        ),
        id=f"complaint-sla-{result['id']}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    return ComplaintRead(**result)


@router.get("/{complaint_id}", response_model=ComplaintRead)
async def get_complaint(complaint: Annotated[Complaint, Depends(valid_complaint)]) -> Complaint:
    return complaint

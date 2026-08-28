"""ComplaintCreate/ComplaintRead — CLAUDE.md §2.4: acknowledgment_due_at/resolution_due_at
are never client-supplied, so ComplaintCreate has no field for either; only ComplaintRead
does, computed server-side by complaints/service.py::create_complaint.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComplaintCreate(BaseModel):
    claim_id: str
    source_call_id: str
    complaint_category: str
    customer_statement_summary: str
    severity: str  # LOW | MEDIUM | HIGH
    preferred_contact_method: str  # PHONE | EMAIL | SMS
    customer_expected_resolution: str | None = None


class ComplaintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: str
    source_call_id: str
    complaint_category: str
    customer_statement_summary: str
    customer_expected_resolution: str | None
    severity: str
    preferred_contact_method: str
    status: str
    acknowledgment_due_at: datetime
    resolution_due_at: datetime
    sla_source: str
    created_at: datetime

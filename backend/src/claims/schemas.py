"""ClaimStatusRead (Batch 6) plus the rest of this domain's read schemas for
claims/router.py (Batch 9, spec §27's Claims section)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.claims.constants import ClaimStage


class ClaimStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: str
    claim_stage: ClaimStage
    current_owner: str | None
    status_timestamp: datetime
    next_expected_event: str | None
    expected_by: datetime | None
    customer_action_required: bool
    customer_action_code: str | None
    delay_flag: bool
    approved_customer_message_key: str | None
    language: str
    # spec §13 Journey E — withheld below Level 2, see claims/service.py::get_disclosable_status
    settlement_amount: Decimal | None


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    policy_id: str
    customer_id: str
    garage_id: str | None
    claim_stage: ClaimStage
    current_owner: str | None
    status_timestamp: datetime
    next_expected_event: str | None
    expected_by: datetime | None
    customer_action_required: bool
    customer_action_code: str | None
    delay_flag: bool
    approved_customer_message_key: str | None
    language: str
    settlement_amount: Decimal | None
    created_at: datetime


class ClaimStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: str
    from_stage: ClaimStage | None
    to_stage: ClaimStage
    event_timestamp: datetime
    note: str | None


class ClaimDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: str
    document_type: str
    status: str
    requested_at: datetime
    received_at: datetime | None


class RepairGarageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    phone_e164: str | None
    address: str | None

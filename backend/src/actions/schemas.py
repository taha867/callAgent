"""ActionCreate/ActionRead, EscalationCreate/EscalationRead — CLAUDE.md §2.4's three-schema
pattern (Create/Read/Update), Update omitted here since neither entity is ever edited
through the dashboard in Phase 1 (status transitions are a later-phase feature, same as
complaints/service.py's own scope note).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.actions.constants import ActionCode


class ActionCreate(BaseModel):
    claim_id: str
    action_code: ActionCode
    summary: str
    source_call_id: str | None = None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: str
    action_code: ActionCode
    summary: str
    status: str
    created_at: datetime


class EscalationCreate(BaseModel):
    call_id: str
    reason: str
    context_snapshot: dict[str, Any] = {}


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    call_id: str
    reason: str
    status: str
    created_at: datetime

"""Mostly read endpoints (CLAUDE.md §2.2: "mutation happens via workflow signals, not
PUT/PATCH") — spec §27's Calls section, trimmed to what this Temporal-native architecture
actually needs. `POST /calls/{callId}/outcome` and `POST /calls/{callId}/callback` from
spec §27's generic REST sketch are intentionally not built: the structured outcome (spec
§23) is written directly by calls/activities.py::finalize_outcome inside the workflow, and
a callback is created the same way (actions/service.py::schedule_callback) — neither needs
a client to POST it back over HTTP, so building that route would be dead code with no
caller. See .claude/specs/phase-1-backend-spec.md §13.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.calls.dependencies import valid_call_attempt
from src.calls.models import CallAttempt
from src.calls.schemas import CallAttemptRead, CallSessionInput, StartCallInput, StartCallOutput
from src.calls.workflows import CallSessionWorkflow
from src.config import settings
from src.kill_switch import require_outbound_enabled
from src.temporal_client import get_temporal_client

router = APIRouter()


@router.get("/{call_id}", response_model=CallAttemptRead)
async def get_call_attempt(
    attempt: Annotated[CallAttempt, Depends(valid_call_attempt)],
) -> CallAttempt:
    return attempt


@router.get("/{call_id}/outcome", response_model=CallAttemptRead)
async def get_call_outcome(
    attempt: Annotated[CallAttempt, Depends(valid_call_attempt)],
) -> CallAttempt:
    """Spec §23's structured outcome record IS the CallAttempt row — see this module's
    docstring for why there's no separate write-back endpoint."""
    return attempt


@router.post(
    "",
    response_model=StartCallOutput,
    dependencies=[Depends(require_outbound_enabled("ai_automation"))],
)
async def start_call(body: StartCallInput) -> StartCallOutput:
    call_id = body.call_id or f"CALL-{uuid.uuid4()}"
    client = await get_temporal_client()
    workflow_id = f"call-session-{body.customer_id}"
    await client.start_workflow(
        CallSessionWorkflow.run,
        CallSessionInput(
            call_id=call_id,
            customer_id=body.customer_id,
            claim_id=body.claim_id,
            simulated_answer_result=body.simulated_answer_result,
        ),
        id=workflow_id,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    return StartCallOutput(call_id=call_id, workflow_id=workflow_id)

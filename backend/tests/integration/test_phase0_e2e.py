"""The Phase 0 exit-criteria proof: fake call -> disposition -> AuditEvent row -> visible
via a raw DB query.

Per .claude/specs/phase-0-backend-spec.md decision 3, this test owns its own Temporal
workflow and worker — Phase0SmokeWorkflow is defined HERE, never in src/calls/, and is
never registered in worker.py. worker.py's job in Phase 0 is only to prove the process
boots and connects (see worker.py's own docstring); this test is what proves the full
chain (Temporal worker boots -> workflow runs -> activity executes -> DB write commits ->
row is queryable) actually works end to end.
"""

from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from temporalio import workflow
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

with workflow.unsafe.imports_passed_through():
    from src.audit.models import AuditEvent
    from src.calls.activities import RecordAuditEventInput, record_audit_event
    from src.calls.constants import DispositionCode


class Phase0SmokeInput(BaseModel):
    customer_id: str
    claim_id: str
    correlation_id: str


class Phase0SmokeOutput(BaseModel):
    disposition_code: DispositionCode
    audit_event_id: str


@workflow.defn
class Phase0SmokeWorkflow:
    @workflow.run
    async def run(self, inp: Phase0SmokeInput) -> Phase0SmokeOutput:
        audit_event_id = await workflow.execute_activity(
            record_audit_event,
            RecordAuditEventInput(
                decision="STATUS_DELIVERED",
                reason_code="PHASE0_SMOKE",
                action_taken=DispositionCode.SUCCESS_STATUS_DELIVERED.value,
                call_id=inp.claim_id,
                correlation_id=inp.correlation_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
        return Phase0SmokeOutput(
            disposition_code=DispositionCode.SUCCESS_STATUS_DELIVERED,
            audit_event_id=audit_event_id,
        )


_SANDBOX_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("pydantic", "src")
)


@pytest.mark.integration
async def test_fake_call_produces_disposition_and_audit_row(
    seeded_db, db_session_committed, temporal_env
):
    task_queue = "phase0-smoke"
    async with Worker(
        temporal_env.client,
        task_queue=task_queue,
        workflows=[Phase0SmokeWorkflow],
        activities=[record_audit_event],
        workflow_runner=_SANDBOX_RUNNER,
    ):
        result = await temporal_env.client.execute_workflow(
            Phase0SmokeWorkflow.run,
            Phase0SmokeInput(
                customer_id="CUST-DEMO-001",
                claim_id="CLM-DEMO-001",
                correlation_id="phase0-smoke-1",
            ),
            id="phase0-smoke-1",
            task_queue=task_queue,
        )

    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED

    row = await db_session_committed.execute(
        select(AuditEvent).where(AuditEvent.correlation_id == "phase0-smoke-1")
    )
    event = row.scalar_one()
    assert event.decision == "STATUS_DELIVERED"
    assert event.action_taken == DispositionCode.SUCCESS_STATUS_DELIVERED.value
    assert event.call_id == "CLM-DEMO-001"
    assert event.id == result.audit_event_id

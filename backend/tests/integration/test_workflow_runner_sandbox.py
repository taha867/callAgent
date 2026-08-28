"""Proves src.workflow_runner.SANDBOXED_WORKFLOW_RUNNER — the configuration worker.py now
uses for every real registered workflow — actually lets a workflow module import `src`
symbols (here src.calls.constants.DispositionCode) and execute, before any of Phase 1's
real state-machine logic exists to obscure a sandbox-restriction failure under unrelated
debugging noise. See .claude/specs/phase-1-backend-implementation-plan.md Batch 4.
"""

from datetime import timedelta

import pytest
from pydantic import BaseModel
from temporalio import workflow
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from src.calls.constants import DispositionCode
    from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER


class _SandboxProbeOutput(BaseModel):
    disposition_code: DispositionCode


@workflow.defn
class _SandboxProbeWorkflow:
    """Test-local only — never registered in worker.py, mirroring
    tests/integration/test_phase0_e2e.py's Phase0SmokeWorkflow pattern."""

    @workflow.run
    async def run(self) -> _SandboxProbeOutput:
        # Touches src.calls.constants from inside sandboxed workflow code — this is exactly
        # the import path CallSessionWorkflow (Batch 11) will need.
        return _SandboxProbeOutput(disposition_code=DispositionCode.SUCCESS_STATUS_DELIVERED)


@pytest.mark.integration
async def test_worker_boots_and_executes_a_workflow_importing_src_under_the_shared_sandbox(
    temporal_env,
):
    task_queue = "workflow-runner-sandbox-probe"
    async with Worker(
        temporal_env.client,
        task_queue=task_queue,
        workflows=[_SandboxProbeWorkflow],
        activities=[],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    ):
        result = await temporal_env.client.execute_workflow(
            _SandboxProbeWorkflow.run,
            id="workflow-runner-sandbox-probe-1",
            task_queue=task_queue,
            execution_timeout=timedelta(seconds=30),
        )

    assert result.disposition_code == DispositionCode.SUCCESS_STATUS_DELIVERED

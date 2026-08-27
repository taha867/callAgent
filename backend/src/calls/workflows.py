"""CallSessionWorkflow — a literal typed stub. Never registered in worker.py.

Per .claude/specs/phase-0-backend-spec.md decision 3 / §8: CallSession/CallAttempt
modeling and the Master Call State Machine are Phase 1's deliverable ("Deterministic
Core"). This stub exists so the shape (typed Pydantic input/output, one @workflow.run
method) is settled before Phase 1 fills it in — it is deliberately empty, not partially
implemented.
"""

from pydantic import BaseModel
from temporalio import workflow


class CallSessionInput(BaseModel):
    call_id: str
    customer_id: str
    claim_id: str


class CallSessionOutput(BaseModel):
    call_id: str
    disposition_code: str


@workflow.defn
class CallSessionWorkflow:
    @workflow.run
    async def run(self, inp: CallSessionInput) -> CallSessionOutput:
        raise NotImplementedError(
            "Phase 1 — Master Call State Machine, spec §3. This stub is intentionally "
            "unimplemented and is never registered in worker.py."
        )

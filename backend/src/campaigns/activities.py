"""check_call_eligibility_activity, get_status_criticality_activity — task 4/9.
Activities aren't sandboxed and aren't replayed, so they may freely use the real wall
clock (datetime.now()) — unlike workflow code, which must use workflow.now()
(CLAUDE.md §2.6). campaigns/service.py::check_call_eligibility itself stays
framework-agnostic (takes `at` as a plain parameter, per
.claude/specs/phase-1-backend-implementation-plan.md's corrections §3) — this activity is
the one place that decides what "now" means for an eligibility check.
"""

from datetime import UTC, datetime

from pydantic import BaseModel
from temporalio import activity

from src.campaigns import service as campaigns_service
from src.campaigns.schemas import CallEligibility
from src.claims.constants import ClaimStage, get_status_criticality
from src.database import get_session_factory


class CheckEligibilityInput(BaseModel):
    customer_id: str
    claim_id: str


@activity.defn(name="check_call_eligibility")
async def check_call_eligibility(inp: CheckEligibilityInput) -> CallEligibility:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await campaigns_service.check_call_eligibility(
            session,
            customer_id=inp.customer_id,
            claim_id=inp.claim_id,
            at=datetime.now(UTC).replace(tzinfo=None),
        )


class GetStatusCriticalityInput(BaseModel):
    claim_id: str


@activity.defn(name="get_status_criticality")
async def get_status_criticality_activity(inp: GetStatusCriticalityInput) -> str:
    from src.claims import service as claims_service

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, inp.claim_id)
        if claim is None:
            return "NORMAL"
        return get_status_criticality(ClaimStage(claim.claim_stage))


ALL_CAMPAIGNS_ACTIVITIES = [check_call_eligibility, get_status_criticality_activity]

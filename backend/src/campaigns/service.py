"""check_call_eligibility() — composes reads from customers/, claims/, and telephony/, spec
§4/§0.6. `at: datetime` is a required parameter, never read from the clock or from
`workflow.now()` inside this module — campaigns/activities.py (Batch 13) is the only place
that decides what "now" means, per .claude/specs/phase-1-backend-implementation-plan.md's
corrections §3. This keeps campaigns/service.py a plain, framework-agnostic, easily
unit-tested module, same as every other service.py in this codebase.

"No active suppression" is hardcoded True for Phase 1 — see decision 0.4/0.6: there is no
CommunicationSuppression table yet (deferred to Phase 2/5).
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.campaigns.schemas import CallEligibility
from src.claims import service as claims_service
from src.telephony import service as telephony_service


async def check_call_eligibility(
    session: AsyncSession, *, customer_id: str, claim_id: str, at: datetime
) -> CallEligibility:
    claim = await claims_service.get_claim(session, claim_id)
    if claim is None:
        return CallEligibility(
            call_eligible=False,
            customer_id=customer_id,
            claim_id=claim_id,
            ineligible_reason="CLAIM_NOT_FOUND",
        )

    cli_config = await telephony_service.get_active_cli(session)
    cli_trunk_authorized = cli_config is not None and cli_config.trunk_authorized
    contact_window_allowed = await telephony_service.is_within_contact_window(session, at)

    ineligible_reason = None
    if not cli_trunk_authorized:
        ineligible_reason = "INVALID_OR_UNAUTHORIZED_CLI"
    elif not contact_window_allowed:
        ineligible_reason = "OUTSIDE_PERMITTED_CONTACT_WINDOW"

    return CallEligibility(
        call_eligible=cli_trunk_authorized and contact_window_allowed,
        customer_id=customer_id,
        claim_id=claim_id,
        cli=cli_config.cli if cli_config is not None else None,
        cli_trunk_authorized=cli_trunk_authorized,
        contact_window_allowed=contact_window_allowed,
        ineligible_reason=ineligible_reason,
    )

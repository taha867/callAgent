"""get_disclosable_status() — key selection + Level-2 financial-field redaction, task 6.
Not text generation: per .claude/specs/phase-1-backend-spec.md decision 0.8, this phase
only selects the already-populated `approved_customer_message_key` and redacts fields the
caller's verification_level doesn't clear — Phase 2 renders the key into actual speech.

Also get_claim() — the plain by-id lookup both claims/router.py (Batch 9) and
calls/activities.py (Batch 10) share, so neither duplicates the fetch-or-None.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.claims.constants import FINANCIAL_STAGES
from src.claims.models import ClaimDocument, ClaimStatusEvent, MotorClaim, RepairGarage
from src.claims.schemas import ClaimDocumentRead, ClaimStatusRead
from src.verification.constants import VerificationLevel


async def get_claim(session: AsyncSession, claim_id: str) -> MotorClaim | None:
    result = await session.execute(select(MotorClaim).where(MotorClaim.id == claim_id))
    return result.scalars().first()


async def get_claim_timeline(session: AsyncSession, claim_id: str) -> list[ClaimStatusEvent]:
    result = await session.execute(
        select(ClaimStatusEvent)
        .where(ClaimStatusEvent.claim_id == claim_id)
        .order_by(ClaimStatusEvent.event_timestamp)
    )
    return list(result.scalars().all())


async def get_claim_documents(session: AsyncSession, claim_id: str) -> list[ClaimDocument]:
    result = await session.execute(select(ClaimDocument).where(ClaimDocument.claim_id == claim_id))
    return list(result.scalars().all())


async def get_garage_for_claim(session: AsyncSession, claim: MotorClaim) -> RepairGarage | None:
    if claim.garage_id is None:
        return None
    result = await session.execute(select(RepairGarage).where(RepairGarage.id == claim.garage_id))
    return result.scalars().first()


def get_disclosable_status(
    claim: MotorClaim, verification_level: VerificationLevel
) -> ClaimStatusRead:
    """Redacts settlement_amount below Level 2 (spec §13 Journey E: "higher authentication
    may be required for financial detail") — no other spec §10.1 redaction is needed here
    because a caller below Level 1 never reaches this function at all (calls/activities.py's
    authentication stage gates the call before status delivery, spec §10.1's "not
    permitted" list)."""
    data = ClaimStatusRead(
        claim_id=claim.id,
        claim_stage=claim.claim_stage,
        current_owner=claim.current_owner,
        status_timestamp=claim.status_timestamp,
        next_expected_event=claim.next_expected_event,
        expected_by=claim.expected_by,
        customer_action_required=claim.customer_action_required,
        customer_action_code=claim.customer_action_code,
        delay_flag=claim.delay_flag,
        approved_customer_message_key=claim.approved_customer_message_key,
        language=claim.language,
        settlement_amount=claim.settlement_amount,
    )
    if verification_level != VerificationLevel.L2 and claim.claim_stage in FINANCIAL_STAGES:
        data = data.model_copy(update={"settlement_amount": None})
    return data


# --- Phase 2 read-only tool-response helpers (voice/tools.py's _READ_TOOLS, spec §21) ------
# Each is a narrow accessor onto data get_disclosable_status already reads — the LLM-facing
# tool contract is deliberately narrower than "get full status" per tool (spec §36 rule 3's
# no-hallucination rule: return None rather than inventing an answer when absent).


def get_next_step_message_key(claim: MotorClaim) -> str | None:
    """explain_next_step tool — same field get_disclosable_status already reads."""
    return claim.approved_customer_message_key


async def list_missing_documents(session: AsyncSession, claim_id: str) -> list[ClaimDocumentRead]:
    """list_missing_documents tool — documents not yet RECEIVED."""
    documents = await get_claim_documents(session, claim_id)
    return [ClaimDocumentRead.model_validate(doc) for doc in documents if doc.status != "RECEIVED"]


def get_authoritative_eta(claim: MotorClaim) -> datetime | None:
    """get_authoritative_eta tool — None when no authoritative ETA exists, never guessed."""
    return claim.expected_by

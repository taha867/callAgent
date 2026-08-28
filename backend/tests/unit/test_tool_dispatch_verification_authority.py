"""voice/tools.py::dispatch_tool_call — the mechanical enforcement of CLAUDE.md's single
most important rule (spec §36 rule 1): a caller's supplied `verification_level` argument is
never trusted. The authoritative value always comes from the workflow's own
`current_verification_level()` query, even when a tool-call argument claims otherwise —
this test forges a mismatched value and proves the dispatcher still ignores it.

Uses db_session_committed since _get_claim_status opens its own session via
get_session_factory(), same pattern as tests/unit/test_calls_activities.py.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from src.voice.tools import dispatch_tool_call


async def _seed_financial_claim(db, *, suffix: str) -> dict:
    from src.claims.constants import ClaimStage
    from src.claims.models import MotorClaim, MotorPolicy
    from src.customers.models import Customer

    customer_id = f"CUST-TOOLAUTH-{suffix}"
    db.add(Customer(id=customer_id, full_name="Test Customer", phone_e164=f"+9715{suffix}"))
    await db.flush()
    db.add(
        MotorPolicy(
            id=f"POL-TOOLAUTH-{suffix}",
            customer_id=customer_id,
            policy_number="P1",
            vehicle_plate="X",
            vehicle_make_model="Y",
        )
    )
    await db.flush()
    claim_id = f"CLM-TOOLAUTH-{suffix}"
    db.add(
        MotorClaim(
            id=claim_id,
            policy_id=f"POL-TOOLAUTH-{suffix}",
            customer_id=customer_id,
            claim_stage=ClaimStage.SETTLEMENT_APPROVED,  # a spec §13 Journey E financial stage
            language="en",
            settlement_amount=Decimal("5000.00"),
            status_timestamp=datetime(2026, 8, 27, 12, 0, 0),
        )
    )
    await db.commit()
    return {"customer_id": customer_id, "claim_id": claim_id}


async def test_forged_l2_argument_discloses_nothing_when_workflow_says_l0(db_session_committed):
    """L0 (unverified) blocks claim-specific disclosure entirely — spec §36 rules 1/2 — not
    just the financial-field-only redaction get_disclosable_status applies between L1/L2."""
    seeded = await _seed_financial_claim(db_session_committed, suffix="1")
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L0")

    result = await dispatch_tool_call(
        name="get_claim_status",
        # Forged: the LLM's tool-call argument claims L2, but the real session is L0.
        args={"claim_id": seeded["claim_id"], "verification_level": "L2"},
        call_id="CALL-TOOLAUTH-1",
        workflow_handle=workflow_handle,
    )

    assert result == {"found": False, "reason": "not_verified"}
    workflow_handle.query.assert_awaited_once()


async def test_forged_l2_argument_is_ignored_when_workflow_says_l1(db_session_committed):
    """At L1 (real), the tool still redacts the financial field per
    get_disclosable_status's own L2-only rule — the forged L2 argument changes nothing."""
    seeded = await _seed_financial_claim(db_session_committed, suffix="1B")
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L1")

    result = await dispatch_tool_call(
        name="get_claim_status",
        args={"claim_id": seeded["claim_id"], "verification_level": "L2"},
        call_id="CALL-TOOLAUTH-1B",
        workflow_handle=workflow_handle,
    )

    assert result["found"] is True
    assert result["settlement_amount"] is None  # redacted as if L1, not disclosed as L2


async def test_real_l2_from_workflow_discloses_the_amount(db_session_committed):
    seeded = await _seed_financial_claim(db_session_committed, suffix="2")
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L2")

    result = await dispatch_tool_call(
        name="get_claim_status",
        args={
            "claim_id": seeded["claim_id"],
            "verification_level": "L0",
        },  # understated, also ignored
        call_id="CALL-TOOLAUTH-2",
        workflow_handle=workflow_handle,
    )

    assert result["found"] is True
    assert result["settlement_amount"] == "5000.00"


async def test_other_claim_specific_read_tools_also_blocked_at_l0(db_session_committed):
    """explain_next_step / list_missing_documents / get_authoritative_eta share
    _require_verified — none of them are claim-status-specific tools by name, but all three
    disclose claim-specific facts and must be gated the same way as get_claim_status."""
    seeded = await _seed_financial_claim(db_session_committed, suffix="2B")
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L0")

    explain_result = await dispatch_tool_call(
        name="explain_next_step",
        args={"claim_id": seeded["claim_id"]},
        call_id="CALL-TOOLAUTH-2B",
        workflow_handle=workflow_handle,
    )
    assert explain_result == {"found": False, "reason": "not_verified"}

    docs_result = await dispatch_tool_call(
        name="list_missing_documents",
        args={"claim_id": seeded["claim_id"]},
        call_id="CALL-TOOLAUTH-2B",
        workflow_handle=workflow_handle,
    )
    assert docs_result == {"missing_documents": [], "reason": "not_verified"}

    eta_result = await dispatch_tool_call(
        name="get_authoritative_eta",
        args={"claim_id": seeded["claim_id"]},
        call_id="CALL-TOOLAUTH-2B",
        workflow_handle=workflow_handle,
    )
    assert eta_result == {"found": False, "reason": "not_verified"}


async def test_get_insurer_identity_is_never_gated_by_verification():
    """Not claim-specific — spec §7's purpose disclosure happens before authentication."""
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L0")

    result = await dispatch_tool_call(
        name="get_insurer_identity",
        args={},
        call_id="CALL-TOOLAUTH-3B",
        workflow_handle=workflow_handle,
    )
    assert result["insurer_name"]
    workflow_handle.query.assert_not_awaited()  # doesn't even need to check


async def test_unknown_claim_id_returns_not_found_never_invents_a_status(db_session_committed):
    workflow_handle = AsyncMock()
    workflow_handle.query = AsyncMock(return_value="L2")

    result = await dispatch_tool_call(
        name="get_claim_status",
        args={"claim_id": "CLM-DOES-NOT-EXIST", "verification_level": "L2"},
        call_id="CALL-TOOLAUTH-3",
        workflow_handle=workflow_handle,
    )

    assert result == {"found": False}

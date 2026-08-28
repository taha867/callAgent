"""The literal enforcement point of spec §2.2.2 rule 3 / §21 (AI Authority Matrix).

TOOL_REGISTRY has exactly 13 entries, 1:1 with spec §21's "Allowed" rows. The 8
"Not allowed"/"Never allowed" rows (change bank account, approve repair, override
authentication, ...) are deliberately ABSENT — there is no schema for the LLM to call,
which is the actual enforcement mechanism, not a comment saying "don't implement this."
NEVER_ALLOWED_CAPABILITIES names those 8 rows as data so a test can assert the registry
and the disallowed set are disjoint, turning "deliberately absent" into a mechanically
checked property.

Phase 2 wires the 13 stubs to real services (`.claude/specs/phase-2-backend-spec.md`
§0.3/§4.4). Module-level imports stay `pydantic` + `src.exceptions` + `temporalio.client`
only (the last is type declarations only — no connection/settings read at import time) —
still no config/DB side effects, since scripts/ci/check_tool_allowlist.py imports this
module directly. Every DB- or workflow-module-touching import happens lazily inside a
function body instead, the same convention calls/activities.py already uses for its own
occasional narrow imports (e.g. get_configured_auth_factor_type).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from temporalio.client import WorkflowHandle

from src.exceptions import UnknownToolError

Permission = Literal["allowed", "not_allowed_mvp", "never_allowed"]


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    args_schema: type[BaseModel]
    permission: Permission


# --- Args schemas — one per allowed capability (spec §21) -------------------------------


class GetInsurerIdentityArgs(BaseModel):
    pass


class RequestVerificationArgs(BaseModel):
    call_id: str
    target_level: Literal["L1", "L2"]


class GetClaimStatusArgs(BaseModel):
    claim_id: str
    verification_level: Literal["L0", "L1", "L2"]


class ExplainNextStepArgs(BaseModel):
    claim_id: str


class ListMissingDocumentsArgs(BaseModel):
    claim_id: str


class GetAuthoritativeEtaArgs(BaseModel):
    claim_id: str


class ScheduleCallbackArgs(BaseModel):
    customer_id: str
    claim_id: str | None = None
    callback_window_start: str
    callback_window_end: str
    reason: str


class RegisterInquiryArgs(BaseModel):
    call_id: str
    category: str
    summary: str


class CreateActionArgs(BaseModel):
    claim_id: str
    action_code: str
    summary: str


class CreateEscalationArgs(BaseModel):
    call_id: str
    reason: str


class RegisterComplaintArgs(BaseModel):
    claim_id: str
    complaint_category: str
    customer_statement_summary: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]


class SendSecureLinkArgs(BaseModel):
    customer_id: str
    link_type: str


class WarmTransferArgs(BaseModel):
    call_id: str
    reason: str


# --- The allow-list -----------------------------------------------------------------

TOOL_REGISTRY: dict[str, ToolSpec] = {
    "get_insurer_identity": ToolSpec(
        name="get_insurer_identity",
        description="Identify the insurer to the caller.",
        args_schema=GetInsurerIdentityArgs,
        permission="allowed",
    ),
    "request_verification": ToolSpec(
        name="request_verification",
        description="Verify the customer using the configured verification workflow.",
        args_schema=RequestVerificationArgs,
        permission="allowed",
    ),
    "get_claim_status": ToolSpec(
        name="get_claim_status",
        description="Read the approved claim status for a verified customer.",
        args_schema=GetClaimStatusArgs,
        permission="allowed",
    ),
    "explain_next_step": ToolSpec(
        name="explain_next_step",
        description="Explain the next approved step for a claim.",
        args_schema=ExplainNextStepArgs,
        permission="allowed",
    ),
    "list_missing_documents": ToolSpec(
        name="list_missing_documents",
        description="List missing documents for a claim.",
        args_schema=ListMissingDocumentsArgs,
        permission="allowed",
    ),
    "get_authoritative_eta": ToolSpec(
        name="get_authoritative_eta",
        description="Provide an authoritative ETA for a claim, if one exists.",
        args_schema=GetAuthoritativeEtaArgs,
        permission="allowed",
    ),
    "schedule_callback": ToolSpec(
        name="schedule_callback",
        description="Schedule a callback for the customer.",
        args_schema=ScheduleCallbackArgs,
        permission="allowed",
    ),
    "register_inquiry": ToolSpec(
        name="register_inquiry",
        description="Register a customer inquiry.",
        args_schema=RegisterInquiryArgs,
        permission="allowed",
    ),
    "create_action": ToolSpec(
        name="create_action",
        description="Create an operational task against a claim.",
        args_schema=CreateActionArgs,
        permission="allowed",
    ),
    "create_escalation": ToolSpec(
        name="create_escalation",
        description="Create a human escalation for the call.",
        args_schema=CreateEscalationArgs,
        permission="allowed",
    ),
    "register_complaint": ToolSpec(
        name="register_complaint",
        description="Register a formal complaint.",
        args_schema=RegisterComplaintArgs,
        permission="allowed",
    ),
    "send_secure_link": ToolSpec(
        name="send_secure_link",
        description="Send an approved secure link to the customer.",
        args_schema=SendSecureLinkArgs,
        permission="allowed",
    ),
    "warm_transfer": ToolSpec(
        name="warm_transfer",
        description="Warm-transfer the call to a human agent.",
        args_schema=WarmTransferArgs,
        permission="allowed",
    ),
}

# spec §21's 8 "Not allowed"/"Never allowed" rows, named as data (not as tool
# implementations) so their absence from TOOL_REGISTRY is a checked property, not just an
# omission. See tests/unit/test_tool_allowlist_mechanism.py.
NEVER_ALLOWED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "change_bank_account",
        "approve_repair",
        "change_settlement",
        "reverse_claim_rejection",
        "interpret_policy_coverage",
        "admit_liability",
        "promise_compensation",
        "override_authentication",
    }
)


def llm_tool(name: str | None = None):
    """Marks a function as an LLM-callable tool implementation. Registers nothing by
    itself in Phase 0 — scripts/ci/check_tool_allowlist.py's static AST scan looks for
    this decorator and cross-checks the (decorator-supplied or function) name against
    TOOL_REGISTRY."""

    def _decorator(fn):
        fn.__llm_tool_name__ = name or fn.__name__
        return fn

    return _decorator


# --- Phase 2: read tools — answered directly, no workflow signal (spec §0.3 shape (a)) ----
# Every DB-touching import is lazy (function-local), preserving this module's "no config/DB
# side effects at import time" property for scripts/ci/check_tool_allowlist.py.


async def _get_insurer_identity(
    args: GetInsurerIdentityArgs, *, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    # Static fact, no I/O — spec §21's simplest "Allowed" capability.
    return {"insurer_name": "Al Ain National Insurance"}


_NOT_VERIFIED_RESPONSE: dict[str, Any] = {"found": False, "reason": "not_verified"}


async def _require_verified(workflow_handle: WorkflowHandle) -> str | None:
    """spec §36 rules 1/2 ("no claim-specific information before required authentication")
    — every claim-specific read tool below calls this first. Returns the real
    verification_level string when it clears L0 (so a caller doesn't have to re-query), or
    None when the call isn't verified yet, meaning "disclose nothing." This is a *coarser*
    gate than claims/service.py::get_disclosable_status's own settlement_amount-only
    redaction (spec §13 Journey E) — that one governs which *fields* of an already-approved
    disclosure are withheld below L2; this one governs whether any claim-specific fact may
    be disclosed at all below L1."""
    from src.calls.workflows import CallSessionWorkflow

    verification_level = await workflow_handle.query(CallSessionWorkflow.current_verification_level)
    return None if verification_level == "L0" else verification_level


async def _get_claim_status(
    args: GetClaimStatusArgs, *, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    """spec §36 rule 1 — `args.verification_level` is parsed (so the tool call is
    well-typed) but NEVER read for this decision. The authoritative value always comes from
    the workflow itself, never from anything the LLM supplied."""
    from src.claims import service as claims_service
    from src.database import get_session_factory
    from src.verification.constants import VerificationLevel

    verification_level = await _require_verified(workflow_handle)
    if verification_level is None:
        return _NOT_VERIFIED_RESPONSE

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, args.claim_id)
        if claim is None:
            return {"found": False}
        status = claims_service.get_disclosable_status(claim, VerificationLevel(verification_level))
        return {"found": True, **status.model_dump(mode="json")}


async def _explain_next_step(
    args: ExplainNextStepArgs, *, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    from src.claims import service as claims_service
    from src.database import get_session_factory

    if await _require_verified(workflow_handle) is None:
        return _NOT_VERIFIED_RESPONSE

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, args.claim_id)
        if claim is None:
            return {"found": False}
        return {
            "found": True,
            "next_step_message_key": claims_service.get_next_step_message_key(claim),
        }


async def _list_missing_documents(
    args: ListMissingDocumentsArgs, *, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    from src.claims import service as claims_service
    from src.database import get_session_factory

    if await _require_verified(workflow_handle) is None:
        return {"missing_documents": [], "reason": "not_verified"}

    session_factory = get_session_factory()
    async with session_factory() as session:
        documents = await claims_service.list_missing_documents(session, args.claim_id)
        return {"missing_documents": [d.model_dump(mode="json") for d in documents]}


async def _get_authoritative_eta(
    args: GetAuthoritativeEtaArgs, *, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    from src.claims import service as claims_service
    from src.database import get_session_factory

    if await _require_verified(workflow_handle) is None:
        return _NOT_VERIFIED_RESPONSE

    session_factory = get_session_factory()
    async with session_factory() as session:
        claim = await claims_service.get_claim(session, args.claim_id)
        if claim is None:
            return {"found": False}
        eta = claims_service.get_authoritative_eta(claim)
        return {"found": True, "expected_by": eta.isoformat() if eta else None}


_READ_TOOLS: dict[str, Any] = {
    "get_insurer_identity": _get_insurer_identity,
    "get_claim_status": _get_claim_status,
    "explain_next_step": _explain_next_step,
    "list_missing_documents": _list_missing_documents,
    "get_authoritative_eta": _get_authoritative_eta,
}


# --- Phase 2: write tools — bridged onto CustomerIntentSignal, signalled into the running
# CallSessionWorkflow (spec §0.3 shape (b)) — the workflow, not this dispatcher, executes
# the matching activity and decides the resulting disposition. `create_escalation` and
# `warm_transfer` skip CustomerIntentSignal entirely and call the existing
# human_request_detected() signal directly, exactly like a customer saying "human please."


def _intent_request_verification(args: RequestVerificationArgs) -> dict[str, Any]:
    # target_level is parsed for schema completeness but not read: L1 already happens via
    # AUTH_ANSWER (extracted from customer speech), never a tool call; the only actionable
    # request this tool can make is the step-up to OTP/Level 2 — see
    # .claude/specs/phase-2-backend-spec.md §0.3's table.
    return {"intent": "REQUEST_OTP"}


def _intent_schedule_callback(args: ScheduleCallbackArgs) -> dict[str, Any]:
    return {
        "intent": "AI_SCHEDULE_CALLBACK",
        "callback_window_start": datetime.fromisoformat(args.callback_window_start),
        "callback_window_end": datetime.fromisoformat(args.callback_window_end),
        "summary": args.reason,
    }


def _intent_register_inquiry(args: RegisterInquiryArgs) -> dict[str, Any]:
    return {"intent": "ASK_QUESTION", "topic": args.category, "summary": args.summary}


def _intent_create_action(args: CreateActionArgs) -> dict[str, Any]:
    from src.actions.constants import ActionCode

    action_code = args.action_code if args.action_code in ActionCode.__members__ else None
    return {
        "intent": "AI_CREATE_ACTION",
        "topic": action_code or ActionCode.CLAIMS_TEAM_QUERY.value,
        "summary": args.summary,
    }


def _intent_register_complaint(args: RegisterComplaintArgs) -> dict[str, Any]:
    return {
        "intent": "COMPLAINT_REQUEST",
        "complaint_category": args.complaint_category,
        "severity": args.severity,
        "summary": args.customer_statement_summary,
    }


def _intent_send_secure_link(args: SendSecureLinkArgs) -> dict[str, Any]:
    return {"intent": "AI_SEND_SECURE_LINK", "topic": args.link_type}


_WRITE_TOOL_INTENTS: dict[str, Any] = {
    "request_verification": _intent_request_verification,
    "schedule_callback": _intent_schedule_callback,
    "register_inquiry": _intent_register_inquiry,
    "create_action": _intent_create_action,
    "register_complaint": _intent_register_complaint,
    "send_secure_link": _intent_send_secure_link,
}

# Tools that skip CustomerIntentSignal entirely — a direct human_request_detected() signal,
# same as the existing customer-said-"human"/REQUEST_HUMAN path.
_HUMAN_REQUEST_TOOLS: frozenset[str] = frozenset({"create_escalation", "warm_transfer"})


async def dispatch_tool_call(
    *, name: str, args: dict[str, Any], call_id: str, workflow_handle: WorkflowHandle
) -> dict[str, Any]:
    """The runtime allow-list gate, paired with the static gate in
    scripts/ci/check_tool_allowlist.py. Rejects any unregistered name before ever reaching
    an implementation. `call_id` is accepted for parity with every other call-scoped
    function in this codebase and future audit-logging use; the bridge itself only needs
    `workflow_handle` (spec §4.4)."""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise UnknownToolError(name)
    validated = spec.args_schema.model_validate(args)

    if name in _READ_TOOLS:
        return await _READ_TOOLS[name](validated, workflow_handle=workflow_handle)

    from src.calls.schemas import CustomerIntentSignal
    from src.calls.workflows import CallSessionWorkflow

    if name in _HUMAN_REQUEST_TOOLS:
        await workflow_handle.signal(CallSessionWorkflow.human_request_detected)
        return {"status": "signalled"}

    intent = CustomerIntentSignal(**_WRITE_TOOL_INTENTS[name](validated))
    await workflow_handle.signal(CallSessionWorkflow.customer_utterance, intent)
    return {"status": "signalled"}

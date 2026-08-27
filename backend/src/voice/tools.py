"""The literal enforcement point of spec §2.2.2 rule 3 / §21 (AI Authority Matrix).

TOOL_REGISTRY has exactly 13 entries, 1:1 with spec §21's "Allowed" rows. The 8
"Not allowed"/"Never allowed" rows (change bank account, approve repair, override
authentication, ...) are deliberately ABSENT — there is no schema for the LLM to call,
which is the actual enforcement mechanism, not a comment saying "don't implement this."
NEVER_ALLOWED_CAPABILITIES names those 8 rows as data so a test can assert the registry
and the disallowed set are disjoint, turning "deliberately absent" into a mechanically
checked property.

Tool implementations stay stubs in Phase 0 (`NotImplementedError`) — Phase 2 wires them to
real services. Imports only `pydantic` + `src.exceptions` — no config/DB side effects,
since scripts/ci/check_tool_allowlist.py imports this module directly.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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


async def dispatch_tool_call(*, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """The runtime allow-list gate, paired with the static gate in
    scripts/ci/check_tool_allowlist.py. Rejects any unregistered name before ever reaching
    an implementation — the implementations themselves are stubs in Phase 0; Phase 2 wires
    them to real services."""
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise UnknownToolError(name)
    spec.args_schema.model_validate(args)
    raise NotImplementedError(f"{name} is wired in Phase 2")

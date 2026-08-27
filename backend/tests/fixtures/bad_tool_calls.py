# ruff: noqa
# Deliberately "bad" fixture code for scripts/ci/check_tool_allowlist.py's meta-test —
# never imported, never collected by pytest (tests/fixtures/ is excluded via
# pyproject.toml's norecursedirs), never linted (excluded via ruff's extend-exclude).

SOME_VARIABLE = "get_claim_status"


def dispatch_tool_call(*, name, args):
    ...


def llm_tool(name=None):
    def _decorator(fn):
        return fn

    return _decorator


dispatch_tool_call(name="get_claim_status", args={})  # OK — registered
dispatch_tool_call(name="change_bank_account", args={})  # VIOLATION: UNREGISTERED_TOOL_CALL
dispatch_tool_call(name=SOME_VARIABLE, args={})  # UNRESOLVED_TOOL_NAME — not blocking by default


@llm_tool
def approve_repair(claim_id: str) -> dict: ...  # VIOLATION: UNREGISTERED_LLM_TOOL


@llm_tool(name="get_claim_status")
def get_claim_status_impl(claim_id: str) -> dict: ...  # OK — registered

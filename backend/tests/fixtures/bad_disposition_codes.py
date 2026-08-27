# ruff: noqa
# Deliberately "bad" fixture code for scripts/ci/check_disposition_action_codes.py's
# meta-test — never imported, never collected, never linted (see bad_tool_calls.py).


def record_outcome(*, action_code=None, disposition_code=None):
    ...


disposition_code = "SUCCESS_STATUS_DELIVERED"  # OK
disposition_code = "SUCESS_STATUS_DELIVERED"  # VIOLATION: UNKNOWN_DISPOSITION_CODE (typo)

record_outcome(action_code="CALLBACK_SCHEDULED")  # OK
record_outcome(action_code="CALLBACK_SCHEDULEDD")  # VIOLATION: UNKNOWN_ACTION_CODE (typo)

payload = {"disposition_code": "NOT_A_REAL_CODE"}  # VIOLATION: UNKNOWN_DISPOSITION_CODE

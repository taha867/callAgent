"""AdversarialScenarioId.BACKEND_TIMEOUT_POST_AUTH — "backend timeout after
authentication." Mechanistically the SAME branch as SYSTEM_DATA_UNAVAILABLE
(calls/workflows.py::_run_status_and_follow_up's `except Exception: backend_unavailable =
True` around the deliver_status activity) — this codebase has no separate simulated-timeout
hook distinct from "claim lookup failed," so a genuine timeout can't currently be induced
through the public signal-based test surface without either internal monkeypatching (out of
scope for a black-box scripted-conversation test) or hitting the exact same
FK-violation defect test_system_data_unavailable.py already found and logged (qa defect
2dd6d559-0e48-40c4-bb7b-e89988082ef8).

Kept as its own file — rather than silently folded into test_system_data_unavailable.py —
so this checklist item stays visibly present and traceable to the same root cause, per
.claude/specs/phase-4-backend-spec.md §0.3's discipline of never silently dropping a
checklist item.
"""

import pytest


@pytest.mark.skip(
    reason="Same underlying branch/defect as test_system_data_unavailable.py — see that "
    "file's docstring and qa defect 2dd6d559-0e48-40c4-bb7b-e89988082ef8. No distinct "
    "timeout-simulation hook exists yet to test this scenario independently."
)
async def test_backend_timeout_after_authentication_resolves_to_backend_system_failure():
    pass

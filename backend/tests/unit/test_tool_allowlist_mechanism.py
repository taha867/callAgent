import subprocess
import sys
from pathlib import Path

import pytest

from src.exceptions import UnknownToolError
from src.voice.tools import NEVER_ALLOWED_CAPABILITIES, TOOL_REGISTRY, dispatch_tool_call

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_FIXTURE = _BACKEND_DIR / "tests" / "fixtures" / "bad_tool_calls.py"


def test_registry_has_exactly_13_entries_all_allowed():
    assert len(TOOL_REGISTRY) == 13
    assert all(spec.permission == "allowed" for spec in TOOL_REGISTRY.values())


def test_registry_disjoint_from_never_allowed_capabilities():
    assert set(TOOL_REGISTRY).isdisjoint(NEVER_ALLOWED_CAPABILITIES)
    assert len(NEVER_ALLOWED_CAPABILITIES) == 8


async def test_dispatch_rejects_unregistered_name_before_reaching_workflow_handle():
    with pytest.raises(UnknownToolError):
        await dispatch_tool_call(
            name="change_bank_account", args={}, call_id="C1", workflow_handle=None
        )


async def test_dispatch_registered_name_passes_the_allowlist_gate():
    """The allow-list mechanism itself, not full tool behavior (that's
    tests/unit/test_tool_dispatch_verification_authority.py, Phase 2) — get_insurer_identity
    is the one read tool with zero I/O, so this stays a pure unit test."""
    result = await dispatch_tool_call(
        name="get_insurer_identity", args={}, call_id="C1", workflow_handle=None
    )
    assert result["insurer_name"]


def test_static_checker_clean_against_src():
    from scripts.ci.check_tool_allowlist import scan_paths

    violations = scan_paths([_BACKEND_DIR / "src"])
    blocking = [v for v in violations if v.code != "UNRESOLVED_TOOL_NAME"]
    assert blocking == []


def test_static_checker_catches_fixture_violations():
    from scripts.ci.check_tool_allowlist import scan_paths

    violations = scan_paths([_FIXTURE])
    codes = {v.code for v in violations}
    assert "UNREGISTERED_TOOL_CALL" in codes
    assert "UNREGISTERED_LLM_TOOL" in codes

    names = {v.message for v in violations if v.code == "UNREGISTERED_TOOL_CALL"}
    assert any("change_bank_account" in m for m in names)


def test_cli_exits_nonzero_on_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_tool_allowlist.py"),
            "--path",
            str(_FIXTURE),
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 1


def test_cli_exits_zero_against_src():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_tool_allowlist.py"),
            "--path",
            "src",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()

"""scripts/ci/check_transcript_redaction.py — mirrors tests/unit/test_prompt_structure.py's
own meta-test structure: the checker must be clean against real src/, and must catch the
deliberately-bad fixture. Spec §36 rule 17's mechanical enforcement — the one real call site
of record_transcript_turn in this codebase (calls/activities.py::persist_transcript_turn)
must always pass a `<result>.redacted_text` value, never raw text.
"""

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def test_static_checker_clean_against_src():
    from scripts.ci.check_transcript_redaction import scan_paths

    assert scan_paths([_BACKEND_DIR / "src"]) == []


def test_static_checker_catches_fixture_violation():
    from scripts.ci.check_transcript_redaction import scan_paths

    violations = scan_paths([_BACKEND_DIR / "tests" / "fixtures" / "bad_transcript_persistence.py"])
    assert len(violations) == 1
    assert violations[0].code == "UNREDACTED_TRANSCRIPT_WRITE"


def test_cli_exits_nonzero_on_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_transcript_redaction.py"),
            "--path",
            "tests/fixtures/bad_transcript_persistence.py",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 1


def test_cli_exits_zero_against_src():
    result = subprocess.run(
        [sys.executable, str(_BACKEND_DIR / "scripts" / "ci" / "check_transcript_redaction.py")],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()

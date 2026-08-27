import inspect
import re
import subprocess
import sys
from pathlib import Path

from src.voice.prompt import PromptContext, build_system_prompt

_RAW_TEXT_PATTERN = re.compile(
    r"(transcript|caller_text|caller_speech|user_input|user_message|utterance|raw_text)", re.I
)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def test_build_system_prompt_has_exactly_one_parameter():
    params = list(inspect.signature(build_system_prompt).parameters.values())
    assert len(params) == 1
    assert params[0].annotation is PromptContext


def test_no_parameter_is_annotated_str():
    for param in inspect.signature(build_system_prompt).parameters.values():
        assert param.annotation is not str


def test_no_prompt_context_field_matches_raw_text_pattern():
    for field_name in PromptContext.model_fields:
        assert not _RAW_TEXT_PATTERN.search(field_name), field_name


def test_static_checker_clean_against_src_voice():
    from scripts.ci.check_no_raw_prompt_concat import scan_paths

    assert scan_paths([_BACKEND_DIR / "src" / "voice"]) == []


def test_static_checker_catches_fixture_violation():
    from scripts.ci.check_no_raw_prompt_concat import scan_paths

    violations = scan_paths([_BACKEND_DIR / "tests" / "fixtures" / "bad_prompt_concat.py"])
    assert len(violations) == 1
    assert violations[0].code == "RAW_TEXT_IN_PROMPT_CONSTRUCTION"


def test_cli_exits_nonzero_on_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_DIR / "scripts" / "ci" / "check_no_raw_prompt_concat.py"),
            "--path",
            "tests/fixtures/bad_prompt_concat.py",
        ],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 1


def test_cli_exits_zero_against_src_voice():
    result = subprocess.run(
        [sys.executable, str(_BACKEND_DIR / "scripts" / "ci" / "check_no_raw_prompt_concat.py")],
        cwd=_BACKEND_DIR,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()

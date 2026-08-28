#!/usr/bin/env python3
"""CI gate: fails the build if any call to calls/service.py::record_transcript_turn under
src/ passes a `redacted_text=` argument that isn't shaped like the output of
privacy/service.py::redact() (a `<something>.redacted_text` attribute access — the one
field RedactionResult exposes for exactly this purpose). Spec §36 rule 17 — raw STT/TTS
output must never reach call_transcript directly.

Same static-analysis-by-shape discipline as check_no_raw_prompt_concat.py: this is a
pragmatic pattern check, not full dataflow analysis, mirroring that script's own scope and
limits. Kept as its own script so a failure here is independently attributable in CI.
"""

from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    col: int
    code: str
    message: str


def _call_target_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_safe_redacted_text_shape(node: ast.expr) -> bool:
    """The only accepted shape: `<expr>.redacted_text` — RedactionResult's own field."""
    return isinstance(node, ast.Attribute) and node.attr == "redacted_text"


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_target_name(node) != "record_transcript_turn":
            continue
        redacted_arg = next((kw.value for kw in node.keywords if kw.arg == "redacted_text"), None)
        if redacted_arg is None:
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    node.col_offset,
                    "MISSING_REDACTED_TEXT_KWARG",
                    "record_transcript_turn() called without an explicit redacted_text= "
                    "keyword argument — cannot verify it went through redact()",
                )
            )
            continue
        if not _is_safe_redacted_text_shape(redacted_arg):
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    node.col_offset,
                    "UNREDACTED_TRANSCRIPT_WRITE",
                    "record_transcript_turn()'s redacted_text= argument is not a "
                    "`<result>.redacted_text` attribute access — it must come from "
                    "privacy/service.py::redact()'s RedactionResult, never raw text",
                )
            )
    return violations


def scan_paths(paths: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for f in files:
            violations.extend(_scan_file(f))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", dest="paths", default=None)
    args = parser.parse_args(argv)

    default = [_BACKEND_DIR / "src"]
    paths = [Path(p) for p in args.paths] if args.paths else default
    resolved = [p if p.is_absolute() else _BACKEND_DIR / p for p in paths]

    violations = scan_paths(resolved)
    in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    for v in violations:
        rel = v.path.relative_to(_BACKEND_DIR) if v.path.is_relative_to(_BACKEND_DIR) else v.path
        print(f"{rel}:{v.lineno}:{v.col}: {v.code} {v.message}")
        if in_github_actions:
            print(f"::error file={rel},line={v.lineno}::{v.code} {v.message}")

    print(f"checked {len(resolved)} path(s) / {len(violations)} violations")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())

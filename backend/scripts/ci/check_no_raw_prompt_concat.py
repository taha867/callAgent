#!/usr/bin/env python3
"""CI gate: fails the build if a `*system_prompt*`/`*developer_prompt*`-named function
under src/voice/ builds a string from an identifier that looks like raw caller speech
(transcript, caller_text, user_input, utterance, ...). Spec §2.2.2 rule 2 — caller speech
must never be concatenated into system/developer prompts as trusted instructions.

Kept as its own script rather than folded into check_tool_allowlist.py so a failure here
is independently attributable in CI, the same reasoning the spec gives for keeping the
governance gates as separate steps.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_PROMPT_FUNC_PATTERN = re.compile(r"(system|developer)_prompt", re.I)
_TAINT_PATTERN = re.compile(
    r"(transcript|caller_text|caller_speech|user_input|user_message|utterance|raw_text|stt_)", re.I
)


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    col: int
    code: str
    message: str


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _tainted_identifiers(node: ast.AST) -> list[str]:
    """Collects identifiers feeding string construction within `node`'s subtree."""
    found: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            for value in sub.values:
                if isinstance(value, ast.FormattedValue):
                    for inner in ast.walk(value.value):
                        name = (
                            _name_of(inner)
                            if isinstance(inner, (ast.Name, ast.Attribute))
                            else None
                        )
                        if name:
                            found.append(name)
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Add):
            for operand in (sub.left, sub.right):
                name = _name_of(operand) if isinstance(operand, (ast.Name, ast.Attribute)) else None
                if name:
                    found.append(name)
        elif (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr in ("format", "join")
        ):
            for arg in list(sub.args) + [kw.value for kw in sub.keywords]:
                name = _name_of(arg) if isinstance(arg, (ast.Name, ast.Attribute)) else None
                if name:
                    found.append(name)
    return found


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and _PROMPT_FUNC_PATTERN.search(node.name):
            for identifier in _tainted_identifiers(node):
                if _TAINT_PATTERN.search(identifier):
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            node.col_offset,
                            "RAW_TEXT_IN_PROMPT_CONSTRUCTION",
                            f"{node.name}() builds a prompt string from {identifier!r}, "
                            "which looks like raw caller text",
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

    default = [_BACKEND_DIR / "src" / "voice"]
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

#!/usr/bin/env python3
"""CI gate: fails the build if a tool call or @llm_tool-decorated function anywhere in the
codebase uses a name outside src.voice.tools.TOOL_REGISTRY.

Library entry point (`scan_paths`) is used both by this CLI and by
tests/unit/test_tool_allowlist_mechanism.py, so the test and CI exercise the identical
code path.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from src.voice.tools import TOOL_REGISTRY  # noqa: E402

_ALLOWED_NAMES = set(TOOL_REGISTRY)

# Non-blocking: a dynamic dispatch name (a variable/enum member rather than a string
# literal) can't be resolved statically. Failing on it by default would be too brittle
# once Phase 2 writes real dispatch code — reported, not blocking, unless --strict-dynamic.
_NON_BLOCKING_CODES = {"UNRESOLVED_TOOL_NAME"}


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    col: int
    code: str
    message: str


def _suggest(name: str) -> str | None:
    matches = difflib.get_close_matches(name, _ALLOWED_NAMES, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _is_dispatch_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "dispatch_tool_call"
    if isinstance(func, ast.Attribute):
        return func.attr == "dispatch_tool_call"
    return False


def _extract_name_arg(node: ast.Call) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == "name":
            return kw.value
    if node.args:
        return node.args[0]
    return None


def _decorator_tool_name(decorator: ast.expr, func_name: str) -> str | None:
    """Returns the registered name for an `llm_tool` decorator in any of its 3 forms, or
    None if this decorator isn't `llm_tool` at all."""
    target = decorator
    call_args: list[ast.expr] = []
    call_keywords: list[ast.keyword] = []
    if isinstance(decorator, ast.Call):
        target = decorator.func
        call_args = decorator.args
        call_keywords = decorator.keywords

    is_llm_tool = (isinstance(target, ast.Name) and target.id == "llm_tool") or (
        isinstance(target, ast.Attribute) and target.attr == "llm_tool"
    )
    if not is_llm_tool:
        return None

    for kw in call_keywords:
        if (
            kw.arg == "name"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    if call_args and isinstance(call_args[0], ast.Constant) and isinstance(call_args[0].value, str):
        return call_args[0].value
    return func_name


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return violations

    is_tools_module = path.name == "tools.py" and path.parent.name == "voice"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_dispatch_call(node):
            name_arg = _extract_name_arg(node)
            if name_arg is None:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        node.col_offset,
                        "MALFORMED_DISPATCH_CALL",
                        "dispatch_tool_call() has no resolvable `name` argument",
                    )
                )
            elif isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                tool_name = name_arg.value
                if tool_name not in _ALLOWED_NAMES:
                    suggestion = _suggest(tool_name)
                    hint = f" (did you mean {suggestion!r}?)" if suggestion else ""
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            node.col_offset,
                            "UNREGISTERED_TOOL_CALL",
                            f"unregistered tool call: {tool_name!r}{hint}",
                        )
                    )
            else:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        node.col_offset,
                        "UNRESOLVED_TOOL_NAME",
                        "tool name is not a string literal — could not statically verify",
                    )
                )

        if not is_tools_module and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                registered_name = _decorator_tool_name(decorator, node.name)
                if registered_name is None:
                    continue
                if registered_name not in _ALLOWED_NAMES:
                    suggestion = _suggest(registered_name)
                    hint = f" (did you mean {suggestion!r}?)" if suggestion else ""
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            node.col_offset,
                            "UNREGISTERED_LLM_TOOL",
                            f"unregistered @llm_tool function: {registered_name!r}{hint}",
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
    parser.add_argument("--strict-dynamic", action="store_true")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in (args.paths or ["src"])]
    resolved = [p if p.is_absolute() else _BACKEND_DIR / p for p in paths]

    violations = scan_paths(resolved)
    blocking_codes = set() if args.strict_dynamic else _NON_BLOCKING_CODES
    blocking = [v for v in violations if v.code not in blocking_codes]

    checked_files = sum(1 for p in resolved for _ in ([p] if p.is_file() else p.rglob("*.py")))
    in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    for v in violations:
        rel = v.path.relative_to(_BACKEND_DIR) if v.path.is_relative_to(_BACKEND_DIR) else v.path
        print(f"{rel}:{v.lineno}:{v.col}: {v.code} {v.message}")
        if in_github_actions and v.code not in blocking_codes:
            pass
        elif in_github_actions:
            print(f"::error file={rel},line={v.lineno}::{v.code} {v.message}")

    print(
        f"checked {checked_files} files / {len(violations)} violations ({len(blocking)} blocking)"
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

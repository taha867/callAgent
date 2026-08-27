#!/usr/bin/env python3
"""CI gate: fails the build if a hardcoded `disposition_code`/`action_code` string literal
anywhere in the codebase isn't a member of DispositionCode/ActionCode. Catches a typo
before it ever reaches a test — the primary payload is the "did you mean ...?" suggestion.
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

from src.actions.constants import ActionCode  # noqa: E402
from src.calls.constants import DispositionCode  # noqa: E402

_TARGETS: dict[str, tuple[set[str], str]] = {
    "disposition_code": ({m.value for m in DispositionCode}, "UNKNOWN_DISPOSITION_CODE"),
    "action_code": ({m.value for m in ActionCode}, "UNKNOWN_ACTION_CODE"),
}

_DEFAULT_EXCLUDE = {"src/calls/constants.py", "src/actions/constants.py"}


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    col: int
    code: str
    message: str


def _suggest(value: str, valid: set[str]) -> str | None:
    matches = difflib.get_close_matches(value, valid, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _check_literal(
    target: str, value: str, node: ast.AST, path: Path, violations: list[Violation]
) -> None:
    valid, code = _TARGETS[target]
    if value in valid:
        return
    suggestion = _suggest(value, valid)
    hint = f" (did you mean {suggestion!r}?)" if suggestion else ""
    violations.append(
        Violation(
            path,
            node.lineno,
            node.col_offset,
            code,
            f"{target}={value!r} is not a known code{hint}",
        )
    )


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        # Assign / AnnAssign: `disposition_code = "X"` / `disposition_code: str = "X"`
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = _name_of(target)
                if name in _TARGETS:
                    _check_literal(name, node.value.value, node, path, violations)

        # Call keyword: `record_outcome(action_code="X")`
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg in _TARGETS
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    _check_literal(kw.arg, kw.value.value, kw.value, path, violations)

        # Dict entries: {"disposition_code": "X"}
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in _TARGETS
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    _check_literal(key.value, value.value, value, path, violations)

        # Compare: `if disposition_code == "X"` / `disposition_code != "X"`
        if isinstance(node, ast.Compare) and isinstance(node.left, (ast.Name, ast.Attribute)):
            name = _name_of(node.left)
            if name in _TARGETS:
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                        _check_literal(name, comparator.value, comparator, path, violations)

    return violations


def scan_paths(paths: list[Path], *, exclude: set[str] | None = None) -> list[Violation]:
    exclude = exclude if exclude is not None else _DEFAULT_EXCLUDE
    violations: list[Violation] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for f in files:
            try:
                rel = str(f.relative_to(_BACKEND_DIR))
            except ValueError:
                rel = str(f)
            if rel in exclude:
                continue
            violations.extend(_scan_file(f))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", dest="paths", default=None)
    parser.add_argument("--exclude", action="append", dest="exclude", default=None)
    args = parser.parse_args(argv)

    paths = [Path(p) for p in (args.paths or ["src"])]
    resolved = [p if p.is_absolute() else _BACKEND_DIR / p for p in paths]
    exclude = set(args.exclude) if args.exclude else _DEFAULT_EXCLUDE

    violations = scan_paths(resolved, exclude=exclude)
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

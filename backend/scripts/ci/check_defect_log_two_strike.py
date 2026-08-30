#!/usr/bin/env python3
"""CI gate: fails if any DefectLogEntry has occurrence_count >= 2 and status != COMPILED —
the mechanical enforcement of phases/phase-4-demo-hardening.md's two-strike rule
(.claude/specs/phase-4-backend-spec.md §6.2).

Unlike the other 4 gate scripts under this directory, this one does NOT run against
.github/workflows/backend-ci.yml's fresh per-PR ephemeral Postgres — that database has no
defect history (it's created and migrated from scratch on every job run). This script is
wired into its own workflow_dispatch job (.github/workflows/phase4-governance-check.yml),
pointed at the persistent hardening/staging DATABASE_URL via a repo/environment secret, run
deliberately before signing off Phase 4 — not on every push.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.qa import service as qa_service  # noqa: E402


async def main() -> int:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    async with session_factory() as db:
        entries = await qa_service.list_all_defects(db)

    blockers = [e for e in entries if qa_service.compilation_required(e)]
    for e in blockers:
        msg = f"UNCOMPILED (seen {e.occurrence_count}x): {e.title} [{e.id}]"
        print(msg)
        if in_github_actions:
            print(f"::error::{msg}")

    print(f"checked {len(entries)} defect(s) / {len(blockers)} pending compilation")
    await engine.dispose()
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

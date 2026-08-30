"""Temporal worker process. Registers the real Phase 1 workflows/activities — Batch 11
deletes the Phase 0 `_phase0_worker_boot_probe` placeholder (CallSessionWorkflow alone
satisfies temporalio's Worker.__init__ "at least one activity, Nexus service, or workflow"
constraint for real now). Runs as a separate deployable process from main.py's HTTP server;
both import the same src/ domain code.
"""

import asyncio
import logging
import logging.config
from pathlib import Path

from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.workflows import CallSessionWorkflow
from src.campaigns.activities import ALL_CAMPAIGNS_ACTIVITIES
from src.campaigns.workflows import RetrySchedulerWorkflow
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.config import settings
from src.temporal_client import get_temporal_client
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

# Explicit model import so every activity-reachable FK target is registered in SQLAlchemy's
# mapper registry for this process. src.campaigns.models (CallJob/OutboundCampaign) is never
# otherwise imported anywhere in this file's import graph — campaigns/activities.py and
# campaigns/workflows.py only touch src.campaigns.service/schemas/constants, never .models
# directly (service.py itself is the only real consumer, and workflows.py deliberately stays
# sandbox-safe/model-free per CLAUDE.md §2.6). Without this, the FIRST ORM flush of a
# CallAttempt row (call_attempt.call_job_id -> call_job.id) in this process raises
# sqlalchemy.exc.NoReferencedTableError — confirmed live: it silently wedged
# call-session-CUST-DEMO-009 into an infinite create_call_attempt retry loop for 16+ hours,
# permanently holding that customer's distributed voice lock (spec §4.1) and blocking every
# subsequent /calls attempt for it with WorkflowAlreadyStartedError. migrations/env.py
# already carries the identical "import every domain's models module" discipline for this
# exact reason; worker.py needs the same for campaigns specifically since it's the one
# domain whose models module isn't already pulled in transitively by this file's imports.
import src.campaigns.models  # noqa: F401

logger = logging.getLogger("worker")


def _configure_logging() -> None:
    logging_ini = Path(__file__).resolve().parent / "logging.ini"
    if logging_ini.exists():
        logging.config.fileConfig(logging_ini, disable_existing_loggers=False)


async def main() -> None:
    # Shared with voice_server.py (Phase 2) — a single connection helper so every Temporal
    # client in this codebase uses the same pydantic_data_converter, not a second
    # independent Client.connect() that would silently diverge from it.
    client = await get_temporal_client()
    logger.info(
        "connected to Temporal at %s (namespace=%s)",
        settings.TEMPORAL_HOST,
        settings.TEMPORAL_NAMESPACE,
    )

    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[CallSessionWorkflow, RetrySchedulerWorkflow, ComplaintSlaMonitorWorkflow],
        activities=[*ALL_CALLS_ACTIVITIES, *ALL_CAMPAIGNS_ACTIVITIES, *ALL_COMPLAINTS_ACTIVITIES],
        workflow_runner=SANDBOXED_WORKFLOW_RUNNER,
    )
    logger.info("worker starting on task queue %s", settings.TEMPORAL_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    _configure_logging()
    asyncio.run(main())

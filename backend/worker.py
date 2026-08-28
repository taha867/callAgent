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

from temporalio.client import Client
from temporalio.worker import Worker

from src.calls.activities import ALL_CALLS_ACTIVITIES
from src.calls.workflows import CallSessionWorkflow
from src.campaigns.activities import ALL_CAMPAIGNS_ACTIVITIES
from src.campaigns.workflows import RetrySchedulerWorkflow
from src.complaints.activities import ALL_COMPLAINTS_ACTIVITIES
from src.complaints.workflows import ComplaintSlaMonitorWorkflow
from src.config import settings
from src.workflow_runner import SANDBOXED_WORKFLOW_RUNNER

logger = logging.getLogger("worker")


def _configure_logging() -> None:
    logging_ini = Path(__file__).resolve().parent / "logging.ini"
    if logging_ini.exists():
        logging.config.fileConfig(logging_ini, disable_existing_loggers=False)


async def main() -> None:
    client = await Client.connect(settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE)
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

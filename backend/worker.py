"""Temporal worker process. Registers ZERO domain workflows/activities — Phase 0's only
job here is to prove the process boots and connects to Temporal OSS; Phase 1 is what gives
it real work (CallSessionWorkflow and friends). Runs as a separate deployable process from
main.py's HTTP server; both import the same src/ domain code.

Deviation from the literal design doc, discovered while implementing: temporalio's
`Worker.__init__` hard-rejects zero activities/workflows/Nexus services
("ValueError: At least one activity, Nexus service, or workflow must be specified") — a
`Worker` object cannot be constructed with nothing registered. `_phase0_worker_boot_probe`
below is a single no-op placeholder activity that exists ONLY to satisfy that SDK
constraint; it registers no domain logic and is deleted the moment Phase 1 adds
CallSessionWorkflow (which alone satisfies the constraint for real).
"""

import asyncio
import logging
import logging.config
from pathlib import Path

from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from src.config import settings

logger = logging.getLogger("worker")


@activity.defn(name="_phase0_worker_boot_probe")
async def _phase0_worker_boot_probe() -> None:
    """Placeholder only — see module docstring. Not part of any domain's public surface
    and never invoked by a workflow; delete this the moment Phase 1 registers real work."""


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
        workflows=[],  # Phase 1 adds CallSessionWorkflow here
        activities=[_phase0_worker_boot_probe],  # Phase 1 replaces this with real activities
    )
    logger.info("worker starting on task queue %s", settings.TEMPORAL_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    _configure_logging()
    asyncio.run(main())

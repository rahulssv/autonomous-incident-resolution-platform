from __future__ import annotations

import asyncio
import signal

from temporalio.worker import Worker

from airp.core.config import get_settings
from airp.core.logging import configure_logging, get_logger
from airp.workflows.activities import (
    agent_graph_run,
    incident_create_github_issue,
    incident_create_remediation_pr,
    incident_record_workflow_event,
    incident_send_slack_notification,
    incident_update_status,
)
from airp.workflows.client import get_temporal_client
from airp.workflows.incident import IncidentWorkflow

logger = get_logger(__name__)


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    client = await get_temporal_client(settings)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[IncidentWorkflow],
        activities=[
            incident_update_status,
            incident_record_workflow_event,
            agent_graph_run,
            incident_create_github_issue,
            incident_send_slack_notification,
            incident_create_remediation_pr,
        ],
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info(
        "temporal_worker_started",
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
    )
    worker_task = asyncio.create_task(worker.run())
    await stop_event.wait()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        logger.info("temporal_worker_stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

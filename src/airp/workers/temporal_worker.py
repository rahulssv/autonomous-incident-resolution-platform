from __future__ import annotations

import asyncio
import signal
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import UnsandboxedWorkflowRunner, Worker

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
from airp.workflows.incident import LIGHT_ACTIVITY_TASK_QUEUE, IncidentWorkflow

logger = get_logger(__name__)


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    client = await get_temporal_client(settings)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[IncidentWorkflow],
        workflow_runner=UnsandboxedWorkflowRunner(),
        activities=[
            incident_update_status,
            incident_record_workflow_event,
            agent_graph_run,
            incident_create_github_issue,
            incident_send_slack_notification,
            incident_create_remediation_pr,
        ],
        activity_executor=ThreadPoolExecutor(
            max_workers=settings.temporal_worker_activity_executor_threads,
            thread_name_prefix="airp-activity",
        ),
        max_concurrent_workflow_tasks=settings.temporal_worker_max_concurrent_workflow_tasks,
        max_concurrent_activities=settings.temporal_worker_max_concurrent_activities,
        max_concurrent_workflow_task_polls=settings.temporal_worker_max_workflow_task_polls,
        max_concurrent_activity_task_polls=settings.temporal_worker_max_activity_task_polls,
        max_activities_per_second=settings.temporal_worker_max_activities_per_second,
    )
    light_worker = Worker(
        client,
        task_queue=LIGHT_ACTIVITY_TASK_QUEUE,
        activities=[
            incident_update_status,
            incident_record_workflow_event,
            incident_create_github_issue,
            incident_send_slack_notification,
            incident_create_remediation_pr,
        ],
        max_concurrent_activities=4,
        max_concurrent_activity_task_polls=2,
        max_activities_per_second=4.0,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info(
        "temporal_worker_started",
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
        max_concurrent_workflow_tasks=settings.temporal_worker_max_concurrent_workflow_tasks,
        max_concurrent_activities=settings.temporal_worker_max_concurrent_activities,
        max_workflow_task_polls=settings.temporal_worker_max_workflow_task_polls,
        max_activity_task_polls=settings.temporal_worker_max_activity_task_polls,
        max_activities_per_second=settings.temporal_worker_max_activities_per_second,
        activity_executor_threads=settings.temporal_worker_activity_executor_threads,
        light_activity_task_queue=LIGHT_ACTIVITY_TASK_QUEUE,
    )
    worker_tasks = [
        asyncio.create_task(worker.run()),
        asyncio.create_task(light_worker.run()),
    ]
    await stop_event.wait()
    for worker_task in worker_tasks:
        worker_task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info("temporal_worker_stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

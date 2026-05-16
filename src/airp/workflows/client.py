from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from airp.core.config import Settings, get_settings
from airp.workflows.incident import IncidentWorkflow, IncidentWorkflowInput


@dataclass(frozen=True)
class WorkflowStartResult:
    workflow_id: str
    workflow_run_id: str | None


class IncidentWorkflowStarter(Protocol):
    async def start_incident_workflow(
        self,
        *,
        incident_id: str,
        severity: str,
        correlation_id: str | None,
    ) -> WorkflowStartResult:
        """Start or attach to the durable workflow for an incident."""


async def get_temporal_client(settings: Settings | None = None) -> Client:
    settings = settings or get_settings()
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        tls=settings.temporal_tls,
    )


class TemporalIncidentWorkflowStarter:
    def __init__(self, settings: Settings | None = None, client: Client | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    async def _get_client(self) -> Client:
        if self._client is None:
            self._client = await get_temporal_client(self.settings)
        return self._client

    async def start_incident_workflow(
        self,
        *,
        incident_id: str,
        severity: str,
        correlation_id: str | None,
    ) -> WorkflowStartResult:
        client = await self._get_client()
        workflow_id = f"airp-incident-{incident_id}"
        handle = await client.start_workflow(
            IncidentWorkflow.run,
            IncidentWorkflowInput(
                incident_id=incident_id,
                severity=severity,
                correlation_id=correlation_id,
            ),
            id=workflow_id,
            task_queue=self.settings.temporal_task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
        return WorkflowStartResult(
            workflow_id=handle.id,
            workflow_run_id=handle.first_execution_run_id or handle.run_id,
        )

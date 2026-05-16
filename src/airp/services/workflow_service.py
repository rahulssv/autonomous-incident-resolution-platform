from __future__ import annotations

from temporalio.client import WorkflowHandle

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError
from airp.schemas.incidents import IncidentEventCreate, WorkflowSignalRequest
from airp.services.incident_service import IncidentService
from airp.workflows.client import get_temporal_client


class IncidentWorkflowSignalService:
    def __init__(self, incident_service: IncidentService, settings: Settings | None = None) -> None:
        self.incident_service = incident_service
        self.settings = settings or get_settings()

    async def signal_workflow(
        self,
        incident_id: str,
        payload: WorkflowSignalRequest,
        *,
        actor: str,
    ):
        incident = await self.incident_service.get_incident(incident_id)
        if not incident.workflow_id:
            raise AppError(
                "Incident does not have an attached workflow",
                status_code=409,
                code="incident_workflow_missing",
            )

        client = await get_temporal_client(self.settings)
        handle: WorkflowHandle = client.get_workflow_handle(
            incident.workflow_id,
            run_id=incident.workflow_run_id,
        )
        signal_payload = {**payload.payload, "actor": actor}
        await handle.signal(payload.signal, args=[payload.reason, signal_payload])

        return await self.incident_service.add_event(
            incident_id,
            IncidentEventCreate(
                event_type="workflow.signal_requested",
                producer="api",
                payload={
                    "actor": actor,
                    "signal": payload.signal,
                    "reason": payload.reason,
                    "payload": payload.payload,
                },
            ),
        )

import pytest

from airp.core.config import Settings
from airp.schemas.incidents import WorkflowSignalRequest
from airp.services.workflow_service import IncidentWorkflowSignalService
from airp.workflows.client import TemporalIncidentWorkflowStarter
from airp.workflows.incident import (
    AGENT_GRAPH_ACTIVITY_TIMEOUT,
    AGENT_GRAPH_RETRY_POLICY,
    IncidentWorkflowInput,
)

pytestmark = pytest.mark.asyncio


class FakeHandle:
    id = "airp-incident-inc-123"
    first_execution_run_id = "run-123"
    run_id = "fallback-run"


class FakeTemporalClient:
    def __init__(self) -> None:
        self.started = []

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append((workflow, arg, kwargs))
        return FakeHandle()


class FakeIncident:
    workflow_id = "airp-incident-inc-123"
    workflow_run_id = "run-123"


class FakeIncidentService:
    def __init__(self) -> None:
        self.events = []

    async def get_incident(self, incident_id: str) -> FakeIncident:
        assert incident_id == "inc-123"
        return FakeIncident()

    async def add_event(self, incident_id, payload):
        self.events.append((incident_id, payload))
        return payload


async def test_temporal_starter_uses_stable_incident_workflow_id() -> None:
    client = FakeTemporalClient()
    starter = TemporalIncidentWorkflowStarter(
        Settings(temporal_task_queue="test-task-queue"),
        client=client,
    )

    result = await starter.start_incident_workflow(
        incident_id="inc-123",
        severity="critical",
        correlation_id="corr-1",
    )

    _, arg, kwargs = client.started[0]
    assert isinstance(arg, IncidentWorkflowInput)
    assert kwargs["id"] == "airp-incident-inc-123"
    assert kwargs["task_queue"] == "test-task-queue"
    assert kwargs["task_timeout"].total_seconds() == 60
    assert result.workflow_id == "airp-incident-inc-123"
    assert result.workflow_run_id == "run-123"


async def test_agent_graph_activity_has_dedicated_retry_settings() -> None:
    assert AGENT_GRAPH_ACTIVITY_TIMEOUT.total_seconds() == 480
    assert AGENT_GRAPH_RETRY_POLICY.maximum_attempts == 3


async def test_retry_failed_activity_signal_records_contract_without_temporal_call() -> None:
    incident_service = FakeIncidentService()
    signal_service = IncidentWorkflowSignalService(incident_service, Settings())

    event = await signal_service.signal_workflow(
        "inc-123",
        WorkflowSignalRequest(
            signal="retry_failed_activity",
            reason="retry operator requested",
            payload={"failed_activity": "agent_graph_run"},
        ),
        actor="sre@example.com",
    )

    assert event.event_type == "workflow.retry_failed_activity_requested"
    assert event.payload["temporal_signal_sent"] is False
    assert event.payload["status"] == "not_implemented"
    assert incident_service.events[0][0] == "inc-123"

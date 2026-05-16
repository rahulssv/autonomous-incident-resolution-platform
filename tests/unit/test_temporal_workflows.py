import pytest

from airp.core.config import Settings
from airp.workflows.client import TemporalIncidentWorkflowStarter
from airp.workflows.incident import IncidentWorkflowInput

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
    assert result.workflow_id == "airp-incident-inc-123"
    assert result.workflow_run_id == "run-123"

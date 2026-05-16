from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from airp.db.models.base import uuid_str
from airp.db.models.incident import Incident, IncidentEvent
from airp.messaging.dedupe import InMemoryDedupeStore
from airp.schemas.incidents import IncidentCreate
from airp.services.alert_ingestion_service import AlertIngestionService
from airp.services.incident_service import IncidentService
from airp.workflows.client import WorkflowStartResult


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, Incident) and item.id is None:
                item.id = uuid_str()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, item) -> None:
        _ = item

    async def scalar(self, stmt):
        _ = stmt
        return None


class FakeIncidentService:
    def __init__(self) -> None:
        self.existing = None
        self.created = False
        self.events = []
        self.attached_workflow = None

    async def get_incident_by_idempotency_key(self, idempotency_key: str):
        _ = idempotency_key
        return self.existing

    async def create_incident_once(self, payload: IncidentCreate, *, actor: str):
        _ = payload, actor
        self.created = True
        self.existing = SimpleNamespace(
            id="inc-1",
            severity=payload.severity.value,
            correlation_id=payload.correlation_id,
        )
        return self.existing, True

    async def add_event(self, incident_id: str, payload):
        self.events.append((incident_id, payload))

    async def attach_workflow(self, incident_id: str, **kwargs):
        self.attached_workflow = (incident_id, kwargs)


class FakeWorkflowStarter:
    def __init__(self) -> None:
        self.started = []

    async def start_incident_workflow(
        self,
        *,
        incident_id: str,
        severity: str,
        correlation_id: str | None,
    ) -> WorkflowStartResult:
        self.started.append((incident_id, severity, correlation_id))
        return WorkflowStartResult(
            workflow_id=f"airp-incident-{incident_id}",
            workflow_run_id="run-1",
        )


def sample_alertmanager_payload() -> dict:
    return {
        "receiver": "airp",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighLatency",
                    "service": "checkout-api",
                    "severity": "critical",
                    "namespace": "shopfast",
                    "environment": "prod",
                },
                "annotations": {
                    "summary": "Checkout latency spike",
                    "description": "p95 latency is above SLO",
                },
                "startsAt": "2026-05-16T00:00:00Z",
                "fingerprint": "abc123",
            }
        ],
    }


@pytest.mark.asyncio
async def test_incident_service_reuses_existing_idempotency_key() -> None:
    session = FakeSession()
    service = IncidentService(session)
    payload = IncidentCreate(
        title="Checkout latency spike",
        severity="critical",
        idempotency_key="alert:checkout:latency",
    )

    first, first_created = await service.create_incident_once(payload, actor="test")
    service.get_incident_by_idempotency_key = AsyncMock(return_value=first)
    second, second_created = await service.create_incident_once(payload, actor="test")

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert [type(item) for item in session.added] == [Incident, IncidentEvent]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_alert_ingestion_uses_service_idempotency_after_redis_replay() -> None:
    payload = sample_alertmanager_payload()
    incidents = FakeIncidentService()
    service = AlertIngestionService(FakeSession(), InMemoryDedupeStore())
    service.incidents = incidents

    first = await service.ingest_alertmanager_payload(payload)
    replay_after_redis_ttl = AlertIngestionService(
        FakeSession(),
        InMemoryDedupeStore(),
    )
    replay_after_redis_ttl.incidents = incidents
    replay = await replay_after_redis_ttl.ingest_alertmanager_payload(payload)

    assert first.created_incident_ids == ["inc-1"]
    assert replay.created_incident_ids == []
    assert replay.duplicate_keys == ["prod:shopfast:checkout-api:HighLatency:critical:abc123"]
    assert len(incidents.events) == 1
    assert incidents.events[0][1].event_type == "alert.validated"


@pytest.mark.asyncio
async def test_alert_ingestion_starts_workflow_for_new_incident() -> None:
    payload = sample_alertmanager_payload()
    incidents = FakeIncidentService()
    workflow_starter = FakeWorkflowStarter()
    service = AlertIngestionService(
        FakeSession(),
        InMemoryDedupeStore(),
        workflow_starter=workflow_starter,
    )
    service.incidents = incidents

    result = await service.ingest_alertmanager_payload(payload)

    assert result.created_incident_ids == ["inc-1"]
    assert workflow_starter.started == [
        ("inc-1", "critical", "prod:shopfast:checkout-api:HighLatency:critical:abc123")
    ]
    assert incidents.attached_workflow == (
        "inc-1",
        {
            "workflow_id": "airp-incident-inc-1",
            "workflow_run_id": "run-1",
            "actor": "monitoring-agent",
        },
    )

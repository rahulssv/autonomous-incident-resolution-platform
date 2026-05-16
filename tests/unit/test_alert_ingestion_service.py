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
        self.payloads = []
        self.events = []
        self.attached_workflow = None

    async def get_incident_by_idempotency_key(self, idempotency_key: str):
        _ = idempotency_key
        return self.existing

    async def create_incident_once(self, payload: IncidentCreate, *, actor: str):
        _ = payload, actor
        self.created = True
        self.payloads.append(payload)
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


def sample_azure_monitor_payload() -> dict:
    return {
        "schemaId": "azureMonitorCommonAlertSchema",
        "data": {
            "essentials": {
                "alertRule": "CheckoutPodRestarting",
                "severity": "Sev1",
                "monitorCondition": "Fired",
                "firedDateTime": "2026-05-16T00:00:00Z",
                "description": "checkout-api pod is restarting",
                "originAlertId": "azure-alert-123",
            },
            "alertContext": {
                "condition": {
                    "allOf": [
                        {
                            "dimensions": [
                                {"name": "namespace", "value": "shopfast"},
                                {"name": "pod", "value": "checkout-api-7d9c-abcde"},
                                {"name": "deployment", "value": "checkout-api"},
                            ]
                        }
                    ]
                }
            },
        },
    }


def sample_azure_event_records_payload() -> dict:
    return {
        "records": [
            {
                "time": "2026-05-16T00:00:00Z",
                "category": "KubernetesEvent",
                "resourceId": (
                    "/subscriptions/sub/resourceGroups/rg/providers/"
                    "Microsoft.ContainerService/managedClusters/airp-aks"
                ),
                "properties": {
                    "reason": "BackOff",
                    "type": "Warning",
                    "message": "Back-off restarting failed container checkout-api",
                    "involvedObject": {
                        "kind": "Pod",
                        "name": "checkout-api-7d9c-abcde",
                        "namespace": "shopfast",
                    },
                },
            }
        ]
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
async def test_alert_ingestion_accepts_azure_monitor_common_alert_schema() -> None:
    incidents = FakeIncidentService()
    workflow_starter = FakeWorkflowStarter()
    service = AlertIngestionService(
        FakeSession(),
        InMemoryDedupeStore(),
        workflow_starter=workflow_starter,
    )
    service.incidents = incidents

    result = await service.ingest_alertmanager_payload(sample_azure_monitor_payload())

    assert result.created_incident_ids == ["inc-1"]
    assert workflow_starter.started == [
        (
            "inc-1",
            "critical",
            "prod:shopfast:checkout-api:CheckoutPodRestarting:critical:azure-alert-123",
        )
    ]
    event = incidents.events[0][1]
    assert event.event_type == "alert.validated"
    assert event.payload["service"] == "checkout-api"
    assert event.payload["labels"]["azure_schema"] == "azureMonitorCommonAlertSchema"


@pytest.mark.asyncio
async def test_alert_ingestion_accepts_azure_event_hub_records() -> None:
    incidents = FakeIncidentService()
    service = AlertIngestionService(FakeSession(), InMemoryDedupeStore())
    service.incidents = incidents

    result = await service.ingest_alertmanager_payload(sample_azure_event_records_payload())

    assert result.created_incident_ids == ["inc-1"]
    event = incidents.events[0][1]
    assert event.payload["alert_name"] == "BackOff"
    assert event.payload["service"] == "checkout-api"
    assert event.payload["labels"]["azure_event_type"] == "KubernetesEvent"


@pytest.mark.asyncio
async def test_alert_ingestion_groups_repeated_azure_kubernetes_events() -> None:
    payload_one = sample_azure_event_records_payload()
    payload_two = sample_azure_event_records_payload()
    payload_one["records"][0]["id"] = "event-1"
    payload_two["records"][0]["id"] = "event-2"
    incidents = FakeIncidentService()
    service = AlertIngestionService(FakeSession(), InMemoryDedupeStore())
    service.incidents = incidents

    first = await service.ingest_alertmanager_payload(payload_one)
    second = await service.ingest_alertmanager_payload(payload_two)

    assert first.created_incident_ids == ["inc-1"]
    assert second.created_incident_ids == []
    assert second.duplicate_keys == [
        (
            "prod:shopfast:checkout-api:BackOff:warning:"
            "azure-event:shopfast:checkout-api:BackOff:checkout-api-7d9c-abcde"
        )
    ]


@pytest.mark.asyncio
async def test_alert_ingestion_groups_azure_image_pull_events_without_workload() -> None:
    payload_one = {
        "records": [
            {
                "id": "event-1",
                "time": "2026-05-16T00:00:00Z",
                "properties": {
                    "reason": "Failed",
                    "type": "Warning",
                    "namespace": "shopfast",
                    "message": (
                        'Failed to pull image "docker.io/ramnathnayak/s3-pricing:latest2": '
                        "not found"
                    ),
                },
            }
        ]
    }
    payload_two = {
        "records": [
            {
                "id": "event-2",
                "time": "2026-05-16T00:01:00Z",
                "properties": {
                    "reason": "Failed",
                    "type": "Warning",
                    "namespace": "shopfast",
                    "message": (
                        'Failed to pull image "docker.io/ramnathnayak/s3-pricing:latest2": '
                        "not found"
                    ),
                },
            }
        ]
    }
    incidents = FakeIncidentService()
    service = AlertIngestionService(FakeSession(), InMemoryDedupeStore())
    service.incidents = incidents

    first = await service.ingest_alertmanager_payload(payload_one)
    second = await service.ingest_alertmanager_payload(payload_two)

    assert first.created_incident_ids == ["inc-1"]
    assert second.created_incident_ids == []
    assert second.duplicate_keys == [incidents.payloads[0].idempotency_key]
    assert incidents.payloads[0].metadata["service"] == "s3-pricing"
    assert incidents.payloads[0].image_tag == "docker.io/ramnathnayak/s3-pricing:latest2"
    assert len(incidents.payloads[0].idempotency_key) <= 160


@pytest.mark.asyncio
async def test_alert_ingestion_ignores_generic_azure_records_without_signal() -> None:
    incidents = FakeIncidentService()
    service = AlertIngestionService(FakeSession(), InMemoryDedupeStore())
    service.incidents = incidents

    result = await service.ingest_alertmanager_payload(
        {"records": [{"resourceId": "/subscriptions/sub/resourceGroups/rg/providers/x/s4-payment"}]}
    )

    assert result.normalized_count == 0
    assert result.created_incident_ids == []
    assert incidents.events == []


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

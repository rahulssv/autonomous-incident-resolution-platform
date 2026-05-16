from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from airp.domain.enums import IncidentSeverity


def utc_now() -> datetime:
    return datetime.now(UTC)


def uuid_str() -> str:
    return str(uuid4())


class EventEnvelope(BaseModel):
    schema_version: str = "1.0"
    event_id: str = Field(default_factory=uuid_str)
    incident_id: str | None = None
    correlation_id: str = Field(default_factory=uuid_str)
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    service: str | None = None
    namespace: str | None = None
    environment: str = "prod"
    severity: IncidentSeverity = IncidentSeverity.WARNING
    producer: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RawAlertEvent(EventEnvelope):
    event_type: Literal["airp.alert.raw"] = "airp.alert.raw"
    producer: str = "alertmanager"


class ValidatedIncidentEvent(EventEnvelope):
    event_type: Literal["airp.incident.validated"] = "airp.incident.validated"
    producer: str = "monitoring-agent"


class DeadLetterEvent(EventEnvelope):
    event_type: Literal["airp.deadletter"] = "airp.deadletter"
    producer: str = "airp-worker"
    error: str
    failed_event: dict[str, Any] = Field(default_factory=dict)

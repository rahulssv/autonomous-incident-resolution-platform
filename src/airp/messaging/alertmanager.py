from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from airp.domain.enums import IncidentSeverity
from airp.schemas.incidents import IncidentCreate


class NormalizedAlert(BaseModel):
    alert_name: str
    status: str = "firing"
    service: str
    severity: IncidentSeverity = IncidentSeverity.WARNING
    environment: str = "prod"
    namespace: str | None = None
    pod_name: str | None = None
    deployment: str | None = None
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = None
    fingerprint: str | None = None
    generator_url: str | None = None
    summary: str | None = None
    description: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        fingerprint = self.fingerprint or "no-fingerprint"
        namespace = self.namespace or "default"
        return (
            f"{self.environment}:{namespace}:{self.service}:"
            f"{self.alert_name}:{self.severity.value}:{fingerprint}"
        )

    def to_incident_create(self) -> IncidentCreate:
        title = self.summary or f"{self.alert_name} on {self.service}"
        description = self.description or f"Alertmanager alert {self.alert_name} is {self.status}."
        return IncidentCreate(
            title=title,
            description=description,
            idempotency_key=self.dedupe_key,
            severity=self.severity,
            environment=self.environment,
            owner=self.labels.get("owner") or self.labels.get("team"),
            correlation_id=self.dedupe_key,
            namespace=self.namespace,
            pod_name=self.pod_name,
            metadata={
                "source": "alertmanager",
                "alert_name": self.alert_name,
                "status": self.status,
                "service": self.service,
                "dedupe_key": self.dedupe_key,
                "deployment": self.deployment,
                "starts_at": self.starts_at.isoformat(),
                "ends_at": self.ends_at.isoformat() if self.ends_at else None,
                "generator_url": self.generator_url,
                "fingerprint": self.fingerprint,
                "labels": self.labels,
                "annotations": self.annotations,
            },
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _severity(value: str | None) -> IncidentSeverity:
    normalized = (value or "").lower()
    if normalized in {"critical", "page", "p1", "sev1"}:
        return IncidentSeverity.CRITICAL
    if normalized in {"info", "none"}:
        return IncidentSeverity.INFO
    return IncidentSeverity.WARNING


def _first_present(values: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value:
            return str(value)
    return None


def normalize_alertmanager_payload(payload: dict[str, Any]) -> list[NormalizedAlert]:
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        raise ValueError("Alertmanager payload must contain a non-empty alerts list")

    normalized_alerts: list[NormalizedAlert] = []
    for raw_alert in alerts:
        if not isinstance(raw_alert, dict):
            raise ValueError("Alertmanager alert entries must be objects")

        labels = dict(raw_alert.get("labels") or {})
        annotations = dict(raw_alert.get("annotations") or {})
        alert_name = _first_present(labels, "alertname", "alert_name") or "UnknownAlert"
        service = _first_present(
            labels,
            "service",
            "app",
            "app_kubernetes_io_name",
            "deployment",
            "job",
            "pod",
        )
        if not service:
            raise ValueError(f"Alert {alert_name} is missing a service/app label")

        starts_at = _parse_datetime(raw_alert.get("startsAt")) or datetime.now(UTC)
        normalized_alerts.append(
            NormalizedAlert(
                alert_name=alert_name,
                status=str(raw_alert.get("status") or payload.get("status") or "firing"),
                service=service,
                severity=_severity(_first_present(labels, "severity", "priority")),
                environment=_first_present(labels, "environment", "env", "cluster") or "prod",
                namespace=_first_present(labels, "namespace", "kubernetes_namespace"),
                pod_name=_first_present(labels, "pod", "pod_name", "kubernetes_pod_name"),
                deployment=_first_present(labels, "deployment", "deployment_name"),
                starts_at=starts_at,
                ends_at=_parse_datetime(raw_alert.get("endsAt")),
                fingerprint=raw_alert.get("fingerprint"),
                generator_url=raw_alert.get("generatorURL"),
                summary=annotations.get("summary"),
                description=annotations.get("description"),
                labels=labels,
                annotations=annotations,
                raw=raw_alert,
            )
        )

    return normalized_alerts

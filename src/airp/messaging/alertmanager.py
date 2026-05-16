from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from airp.domain.enums import IncidentSeverity
from airp.schemas.incidents import IncidentCreate

_QUOTED_IMAGE_RE = re.compile(
    r'(?:image|reference)\s+"(?P<image>[^"]+)"',
    flags=re.IGNORECASE,
)
_CONTAINER_IMAGE_RE = re.compile(
    r"\b(?P<image>(?:[a-zA-Z0-9.-]+(?::\d+)?/)?"
    r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+"
    r"(?::[a-zA-Z0-9._-]+)?(?:@[A-Za-z0-9_:+.-]+)?)\b"
)


class NormalizedAlert(BaseModel):
    alert_name: str
    status: str = "firing"
    service: str
    severity: IncidentSeverity = IncidentSeverity.WARNING
    environment: str = "prod"
    namespace: str | None = None
    pod_name: str | None = None
    deployment: str | None = None
    image_tag: str | None = None
    image_digest: str | None = None
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = None
    fingerprint: str | None = None
    generator_url: str | None = None
    summary: str | None = None
    description: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str = "alertmanager"

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
        description = self.description or f"{self.source} alert {self.alert_name} is {self.status}."
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
            image_tag=self.image_tag,
            image_digest=self.image_digest,
            metadata={
                "source": self.source,
                "alert_name": self.alert_name,
                "status": self.status,
                "service": self.service,
                "image_tag": self.image_tag,
                "image_digest": self.image_digest,
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
    normalized = (value or "").lower().replace(" ", "")
    if normalized in {"critical", "page", "p1", "sev0", "sev1", "error", "err"}:
        return IncidentSeverity.CRITICAL
    if normalized in {"info", "none", "sev4", "verbose", "normal"}:
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
    if "alerts" not in payload:
        return _normalize_non_alertmanager_payload(payload)
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


def _normalize_non_alertmanager_payload(payload: dict[str, Any]) -> list[NormalizedAlert]:
    if _is_azure_monitor_common_alert(payload):
        return [_normalize_azure_monitor_common_alert(payload)]

    records = payload.get("records")
    if isinstance(records, list):
        return [
            alert
            for record in records
            if isinstance(record, dict)
            for alert in _normalize_azure_event_record(record)
        ]

    if _is_event_grid_event(payload):
        return _normalize_azure_event_record(payload)

    normalized = _normalize_azure_event_record(payload)
    if normalized:
        return normalized

    raise ValueError(
        "Alert payload must contain Alertmanager alerts, Azure Monitor common alert "
        "data, or Azure event records"
    )


def _is_azure_monitor_common_alert(payload: dict[str, Any]) -> bool:
    return payload.get("schemaId") == "azureMonitorCommonAlertSchema" and isinstance(
        payload.get("data"), dict
    )


def _normalize_azure_monitor_common_alert(payload: dict[str, Any]) -> NormalizedAlert:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    essentials = data.get("essentials") if isinstance(data.get("essentials"), dict) else {}
    alert_context = data.get("alertContext") if isinstance(data.get("alertContext"), dict) else {}
    dimensions = _azure_monitor_dimensions(alert_context)

    alert_name = _first_present(essentials, "alertRule", "alertRuleName") or "AzureMonitorAlert"
    status = str(_first_present(essentials, "monitorCondition", "status") or "Fired")
    namespace = _first_present(dimensions, "namespace", "kubernetes_namespace", "Namespace")
    pod_name = _first_present(dimensions, "pod", "pod_name", "PodName", "kubernetes_pod_name")
    deployment = _first_present(dimensions, "deployment", "deployment_name", "Deployment")
    service = (
        _first_present(dimensions, "service", "app", "container", "ContainerName")
        or deployment
        or _service_from_workload_name(pod_name)
        or _resource_name_from_id(_first_alert_target(essentials))
        or alert_name
    )
    fired_at = _parse_datetime(
        _first_present(essentials, "firedDateTime", "startDateTime", "lastModifiedDateTime")
    )
    summary = str(_first_present(essentials, "description", "alertRule") or alert_name)
    description = _azure_description(summary, alert_context)
    fingerprint = _first_present(essentials, "originAlertId", "alertId") or _stable_hash(payload)

    return NormalizedAlert(
        alert_name=alert_name,
        status=_status_from_azure_condition(status),
        service=service,
        severity=_severity(_first_present(essentials, "severity")),
        environment=_first_present(dimensions, "environment", "env", "cluster") or "prod",
        namespace=namespace,
        pod_name=pod_name,
        deployment=deployment,
        starts_at=fired_at or datetime.now(UTC),
        fingerprint=fingerprint,
        generator_url=_first_present(essentials, "alertRuleUrl"),
        summary=summary,
        description=description,
        labels={**dimensions, "azure_schema": "azureMonitorCommonAlertSchema"},
        annotations={"summary": summary, "description": description},
        raw=payload,
        source="azure-monitor",
    )


def _normalize_azure_event_record(record: dict[str, Any]) -> list[NormalizedAlert]:
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
    if not properties and isinstance(data.get("properties"), dict):
        properties = data["properties"]
    body = {**record, **data, **properties}
    involved = _first_dict(body, "involvedObject", "involved_object", "object")
    dimensions = _flatten_dict(body.get("dimensions"))

    event_type = _first_present(record, "eventType", "type", "category", "operationName")
    reason = _first_present(body, "reason", "Reason", "eventReason", "name")
    event_kind = _first_present(body, "kind", "objectKind")
    involved_kind = _first_present(involved, "kind") if involved else None
    severity_text = _first_present(body, "severity", "level", "type")
    message = _first_present(body, "message", "Message", "description", "summary")
    image_tag = _container_image_from_event(body, message)
    image_service = _repo_name_from_container_image(image_tag)
    if not any((event_type, reason, event_kind, involved_kind, severity_text, message)):
        return []
    namespace = (
        _first_present(body, "namespace", "kubernetes_namespace", "Namespace")
        or _first_present(dimensions, "namespace", "Namespace")
        or (_first_present(involved, "namespace") if involved else None)
    )
    pod_name = (
        _first_present(body, "pod", "pod_name", "kubernetes_pod_name", "PodName")
        or _first_present(dimensions, "pod", "PodName")
        or (
            _first_present(involved, "name")
            if involved_kind and involved_kind.lower() == "pod"
            else None
        )
    )
    deployment = (
        _first_present(body, "deployment", "deployment_name", "Deployment")
        or _first_present(dimensions, "deployment", "Deployment")
        or (
            _first_present(involved, "name")
            if involved_kind and involved_kind.lower() == "deployment"
            else None
        )
    )
    service = (
        _first_present(body, "service", "app", "appName", "container", "containerName")
        or _first_present(dimensions, "service", "app", "container")
        or deployment
        or _service_from_workload_name(pod_name)
        or image_service
        or _resource_name_from_id(_first_present(record, "resourceId", "resourceUri", "subject"))
        or "azure-event"
    )
    if _is_non_actionable_azure_event(severity_text, reason or event_type):
        return []

    occurred_at = _parse_datetime(
        _first_present(record, "time", "eventTime", "timestamp", "TimeGenerated")
        or _first_present(body, "lastTimestamp", "firstTimestamp", "eventTime")
    )
    alert_name = reason or event_type or "AzureEvent"
    description = message or f"Azure event {alert_name} was received from Event Hubs."
    fingerprint = _azure_event_fingerprint(
        alert_name=alert_name,
        service=service,
        namespace=namespace,
        pod_name=pod_name,
        deployment=deployment,
        image_tag=image_tag,
        message=description,
    ) or _first_present(record, "id", "correlationId", "operationId") or _stable_hash(record)
    status = _status_from_azure_condition(
        _first_present(body, "status", "monitorCondition", "type")
    )

    return [
        NormalizedAlert(
            alert_name=alert_name,
            status=status,
            service=service,
            severity=_severity(severity_text or reason),
            environment=_first_present(body, "environment", "env", "clusterName") or "prod",
            namespace=namespace,
            pod_name=pod_name,
            deployment=deployment,
            image_tag=image_tag,
            starts_at=occurred_at or datetime.now(UTC),
            fingerprint=fingerprint,
            generator_url=_first_present(record, "resourceId", "resourceUri", "subject"),
            summary=f"{alert_name} on {service}",
            description=description,
            labels={
                "azure_event_type": event_type,
                "reason": reason,
                "kind": event_kind or involved_kind,
                "image": image_tag,
                **{key: value for key, value in dimensions.items() if isinstance(value, str)},
            },
            annotations={"summary": f"{alert_name} on {service}", "description": description},
            raw=record,
            source="azure-event-hubs",
        )
    ]


def _is_event_grid_event(payload: dict[str, Any]) -> bool:
    return bool(payload.get("eventType") and payload.get("eventTime") and payload.get("data"))


def _azure_monitor_dimensions(alert_context: dict[str, Any]) -> dict[str, str]:
    dimensions: dict[str, str] = {}
    condition = (
        alert_context.get("condition")
        if isinstance(alert_context.get("condition"), dict)
        else {}
    )
    all_of = condition.get("allOf") if isinstance(condition.get("allOf"), list) else []
    for item in all_of:
        if not isinstance(item, dict):
            continue
        dimensions.update(_flatten_dict(item.get("dimensions")))
    dimensions.update(_flatten_dict(alert_context.get("dimensions")))
    return dimensions


def _flatten_dict(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items() if item not in (None, "")}
    if isinstance(value, list):
        flattened: dict[str, str] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            name = _first_present(item, "name", "Name")
            item_value = _first_present(item, "value", "Value")
            if name and item_value:
                flattened[name] = item_value
        return flattened
    return {}


def _first_dict(values: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, dict):
            return value
    return None


def _first_alert_target(essentials: dict[str, Any]) -> str | None:
    targets = essentials.get("alertTargetIDs")
    if isinstance(targets, list) and targets:
        return str(targets[0])
    return _first_present(essentials, "targetResource", "targetResourceName")


def _resource_name_from_id(value: str | None) -> str | None:
    if not value:
        return None
    parts = [part for part in value.rstrip("/").split("/") if part]
    return parts[-1] if parts else None


def _service_from_workload_name(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 3 and len(parts[-1]) >= 4 and len(parts[-2]) >= 4:
        return "-".join(parts[:-2])
    if len(parts) >= 2 and len(parts[-1]) >= 5:
        return "-".join(parts[:-1])
    return value


def _container_image_from_event(body: dict[str, Any], message: str | None) -> str | None:
    explicit = _first_present(
        body,
        "image",
        "imageName",
        "containerImage",
        "container_image",
        "image_tag",
    )
    if explicit:
        return explicit.strip().strip('"')
    if not message:
        return None
    quoted = _QUOTED_IMAGE_RE.search(message)
    if quoted:
        return quoted.group("image").strip()
    match = _CONTAINER_IMAGE_RE.search(message)
    if match:
        return match.group("image").strip()
    return None


def _repo_name_from_container_image(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.split("@", 1)[0].strip("/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[1]
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0]
    return normalized or None


def _azure_event_fingerprint(
    *,
    alert_name: str,
    service: str,
    namespace: str | None,
    pod_name: str | None,
    deployment: str | None,
    image_tag: str | None,
    message: str | None,
) -> str | None:
    workload = deployment or pod_name
    if not workload and image_tag:
        workload = f"image:{_stable_hash(image_tag)[:16]}"
    if not workload and message:
        workload = f"message:{_stable_hash(message)[:16]}"
    if not workload:
        return None
    return ":".join(
        [
            "azure-event",
            namespace or "default",
            service,
            alert_name,
            workload,
        ]
    )


def _status_from_azure_condition(value: str | None) -> str:
    normalized = (value or "").lower()
    if normalized in {"resolved", "succeeded", "normal"}:
        return "resolved"
    return "firing"


def _is_non_actionable_azure_event(severity: str | None, reason: str | None) -> bool:
    normalized_severity = (severity or "").lower()
    normalized_reason = (reason or "").lower()
    if normalized_severity in {"normal", "information", "informational", "info"}:
        return True
    return normalized_reason in {"pulled", "created", "scheduled", "started", "successfulcreate"}


def _azure_description(summary: str, alert_context: dict[str, Any]) -> str:
    context = json.dumps(alert_context, sort_keys=True, default=str)
    if context == "{}":
        return summary
    return f"{summary}\n\nAzure alert context: {context[:2000]}"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

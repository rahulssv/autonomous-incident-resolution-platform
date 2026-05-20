import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.config import Settings, get_settings
from airp.db.models.catalog import ServiceCatalog
from airp.messaging.alertmanager import NormalizedAlert, normalize_alertmanager_payload
from airp.messaging.dedupe import DedupeStore
from airp.schemas.incidents import IncidentEventCreate
from airp.services.incident_service import IncidentService
from airp.workflows.client import IncidentWorkflowStarter

logger = logging.getLogger(__name__)

# Generic K8s/Azure event placeholders that should NOT be treated as a real
# microservice name. When an alert arrives with one of these in `service`, we
# try to recover a real service name from the pod/deployment labels before
# letting the alert through.
_GENERIC_SERVICE_PLACEHOLDERS = frozenset(
    {
        "",
        "azure-event",
        "kube-event",
        "kubernetes",
        "k8s",
        "service",
        "container",
        "unknown",
    }
)

# Standard K8s pod-name pattern: <deployment>-<replicaset-hash>-<pod-hash>.
# The two trailing hash segments are 5-10 chars of lowercase alphanumeric.
_POD_NAME_HASH_SUFFIX = re.compile(r"^(?P<deployment>.+?)-[a-z0-9]{5,10}-[a-z0-9]{5,10}$")
# Simpler form used by StatefulSets etc: <name>-<ordinal>.
_POD_NAME_ORDINAL_SUFFIX = re.compile(r"^(?P<name>.+?)-\d+$")


@dataclass
class AlertIngestionResult:
    created_incident_ids: list[str] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)
    normalized_count: int = 0
    remapped_count: int = 0


class AlertIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        dedupe_store: DedupeStore,
        settings: Settings | None = None,
        workflow_starter: IncidentWorkflowStarter | None = None,
    ) -> None:
        self.session = session
        self.dedupe_store = dedupe_store
        self.settings = settings or get_settings()
        self.workflow_starter = workflow_starter
        self.incidents = IncidentService(session)

    async def ingest_alertmanager_payload(
        self,
        payload: dict[str, Any],
        *,
        actor: str = "monitoring-agent",
    ) -> AlertIngestionResult:
        alerts = normalize_alertmanager_payload(payload)
        result = AlertIngestionResult(normalized_count=len(alerts))

        for alert in alerts:
            remapped = self._remap_generic_service(alert)
            if remapped is not alert:
                result.remapped_count += 1
                logger.info(
                    "alert_service_remapped from=%s to=%s pod=%s deployment=%s",
                    alert.service,
                    remapped.service,
                    alert.pod_name,
                    alert.deployment,
                )
                alert = remapped
            created = await self._ingest_normalized_alert(alert, actor=actor)
            if created is None:
                result.duplicate_keys.append(alert.dedupe_key)
            else:
                result.created_incident_ids.append(created)

        return result

    @staticmethod
    def _remap_generic_service(alert: NormalizedAlert) -> NormalizedAlert:
        """If the alert's `service` is a generic placeholder, derive the real
        microservice name from the pod/deployment labels and return a new
        NormalizedAlert with the corrected service. Otherwise return the
        original alert unchanged.

        Order of precedence:
            1. deployment label (most authoritative)
            2. pod name minus the K8s hash suffix
            3. namespace (last resort — usually too coarse, kept as identifier)
        """
        service = (alert.service or "").strip().lower()
        if service not in _GENERIC_SERVICE_PLACEHOLDERS:
            return alert

        candidate: str | None = None

        if alert.deployment and alert.deployment.strip().lower() not in _GENERIC_SERVICE_PLACEHOLDERS:
            candidate = alert.deployment.strip()

        if candidate is None and alert.pod_name:
            pod = alert.pod_name.strip()
            m = _POD_NAME_HASH_SUFFIX.match(pod)
            if m:
                candidate = m.group("deployment")
            else:
                m = _POD_NAME_ORDINAL_SUFFIX.match(pod)
                if m:
                    candidate = m.group("name")

        if not candidate or candidate.strip().lower() in _GENERIC_SERVICE_PLACEHOLDERS:
            # No good replacement found — leave the alert as-is so it still
            # produces an incident, just without a real repo binding.
            return alert

        return alert.model_copy(update={"service": candidate})

    async def _ingest_normalized_alert(self, alert: NormalizedAlert, *, actor: str) -> str | None:
        existing = await self.incidents.get_incident_by_idempotency_key(alert.dedupe_key)
        if existing is not None:
            return None

        claimed = await self.dedupe_store.claim(
            alert.dedupe_key,
            ttl_seconds=self.settings.alert_dedupe_ttl_seconds,
        )
        if not claimed:
            return None

        incident_payload = alert.to_incident_create()
        service_id = await self._resolve_service_id(alert)
        if service_id:
            incident_payload = incident_payload.model_copy(update={"service_id": service_id})

        incident, created = await self.incidents.create_incident_once(
            incident_payload,
            actor=actor,
        )
        if not created:
            return None

        await self.incidents.add_event(
            incident.id,
            IncidentEventCreate(
                event_type="alert.validated",
                producer="monitoring-agent",
                payload={
                    "dedupe_key": alert.dedupe_key,
                    "alert_name": alert.alert_name,
                    "service": alert.service,
                    "severity": alert.severity.value,
                    "fingerprint": alert.fingerprint,
                    "labels": alert.labels,
                    "annotations": alert.annotations,
                },
            ),
        )
        await self._start_workflow(
            incident.id,
            severity=incident.severity,
            correlation_id=incident.correlation_id,
            actor=actor,
        )
        return incident.id

    async def _resolve_service_id(self, alert: NormalizedAlert) -> str | None:
        criteria = []
        if alert.namespace:
            criteria.append(
                and_(
                    ServiceCatalog.name == alert.service,
                    ServiceCatalog.namespace == alert.namespace,
                    ServiceCatalog.environment == alert.environment,
                )
            )
        if alert.deployment and alert.namespace:
            criteria.append(
                and_(
                    ServiceCatalog.deployment == alert.deployment,
                    ServiceCatalog.namespace == alert.namespace,
                    ServiceCatalog.environment == alert.environment,
                )
            )
        criteria.append(
            and_(
                ServiceCatalog.name == alert.service,
                ServiceCatalog.environment == alert.environment,
            )
        )

        for criterion in criteria:
            service_id = await self.session.scalar(
                select(ServiceCatalog.id).where(criterion).limit(1)
            )
            if service_id:
                return service_id
        return None

    async def _start_workflow(
        self,
        incident_id: str,
        *,
        severity: str,
        correlation_id: str | None,
        actor: str,
    ) -> None:
        if self.workflow_starter is None:
            return

        try:
            start = await self.workflow_starter.start_incident_workflow(
                incident_id=incident_id,
                severity=severity,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            await self.incidents.add_event(
                incident_id,
                IncidentEventCreate(
                    event_type="workflow.start_failed",
                    producer="monitoring-agent",
                    payload={"error": str(exc)},
                ),
            )
            return

        await self.incidents.attach_workflow(
            incident_id,
            workflow_id=start.workflow_id,
            workflow_run_id=start.workflow_run_id,
            actor=actor,
        )

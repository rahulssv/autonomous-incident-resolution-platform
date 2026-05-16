from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.config import Settings, get_settings
from airp.messaging.alertmanager import NormalizedAlert, normalize_alertmanager_payload
from airp.messaging.dedupe import DedupeStore
from airp.schemas.incidents import IncidentEventCreate
from airp.services.incident_service import IncidentService


@dataclass
class AlertIngestionResult:
    created_incident_ids: list[str] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)
    normalized_count: int = 0


class AlertIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        dedupe_store: DedupeStore,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.dedupe_store = dedupe_store
        self.settings = settings or get_settings()
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
            created = await self._ingest_normalized_alert(alert, actor=actor)
            if created is None:
                result.duplicate_keys.append(alert.dedupe_key)
            else:
                result.created_incident_ids.append(created)

        return result

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

        incident, created = await self.incidents.create_incident_once(
            alert.to_incident_create(),
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
        return incident.id

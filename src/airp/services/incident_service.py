from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.errors import NotFoundError
from airp.db.models.incident import EvidenceItem, Incident, IncidentEvent, RemediationPlan
from airp.domain.enums import IncidentStatus
from airp.schemas.incidents import (
    EvidenceItemCreate,
    IncidentCreate,
    IncidentEventCreate,
    IncidentSignal,
    RemediationPlanCreate,
)


def _payload_with_extra(payload: dict[str, Any]) -> dict[str, Any]:
    if "metadata" in payload:
        payload["extra"] = payload.pop("metadata")
    return payload


class IncidentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_incident(self, payload: IncidentCreate, *, actor: str) -> Incident:
        values = _payload_with_extra(payload.model_dump(mode="json"))
        values["severity"] = payload.severity.value
        incident = Incident(**values)
        self.session.add(incident)
        await self.session.flush()
        self.session.add(
            IncidentEvent(
                incident_id=incident.id,
                event_type="incident.created",
                producer="api",
                payload={"actor": actor, "title": incident.title},
            )
        )
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def list_incidents(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        service_id: str | None = None,
        environment: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Incident]:
        stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Incident.status == status)
        if severity:
            stmt = stmt.where(Incident.severity == severity)
        if service_id:
            stmt = stmt.where(Incident.service_id == service_id)
        if environment:
            stmt = stmt.where(Incident.environment == environment)
        return list((await self.session.scalars(stmt)).all())

    async def get_incident(self, incident_id: str) -> Incident:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundError("incident", incident_id)
        return incident

    async def get_events(self, incident_id: str) -> list[IncidentEvent]:
        await self.get_incident(incident_id)
        stmt = (
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_event(self, incident_id: str, payload: IncidentEventCreate) -> IncidentEvent:
        await self.get_incident(incident_id)
        event = IncidentEvent(
            incident_id=incident_id,
            event_type=payload.event_type,
            producer=payload.producer,
            payload=payload.payload,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def signal_incident(
        self, incident_id: str, payload: IncidentSignal, *, actor: str
    ) -> Incident:
        incident = await self.get_incident(incident_id)
        incident.status = payload.status.value
        if payload.status in {IncidentStatus.CLOSED, IncidentStatus.ESCALATED}:
            incident.closed_at = datetime.now(UTC)
        event = IncidentEvent(
            incident_id=incident.id,
            event_type="incident.signaled",
            producer="api",
            payload={
                "actor": actor,
                "status": payload.status.value,
                "reason": payload.reason,
                "payload": payload.payload,
            },
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def add_evidence(self, incident_id: str, payload: EvidenceItemCreate) -> EvidenceItem:
        await self.get_incident(incident_id)
        evidence = EvidenceItem(incident_id=incident_id, **payload.model_dump(mode="json"))
        self.session.add(evidence)
        await self.session.commit()
        await self.session.refresh(evidence)
        return evidence

    async def create_remediation_plan(
        self,
        incident_id: str,
        payload: RemediationPlanCreate,
    ) -> RemediationPlan:
        await self.get_incident(incident_id)
        values = _payload_with_extra(payload.model_dump(mode="json"))
        values["risk_level"] = payload.risk_level.value
        plan = RemediationPlan(incident_id=incident_id, **values)
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

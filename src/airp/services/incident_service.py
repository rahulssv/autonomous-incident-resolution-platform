import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.errors import NotFoundError
from airp.db.models.incident import (
    EvidenceItem,
    Incident,
    IncidentEvent,
    ModelCall,
    RCAHypothesis,
    RemediationPlan,
    ToolCall,
)
from airp.domain.enums import IncidentStatus
from airp.schemas.incidents import (
    EvidenceItemCreate,
    IncidentCreate,
    IncidentEventCreate,
    IncidentSignal,
    ModelCallCreate,
    RCAHypothesisCreate,
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
        incident, _ = await self.create_incident_once(payload, actor=actor)
        return incident

    async def create_incident_once(
        self, payload: IncidentCreate, *, actor: str
    ) -> tuple[Incident, bool]:
        if payload.idempotency_key:
            existing = await self.get_incident_by_idempotency_key(payload.idempotency_key)
            if existing is not None:
                return existing, False

        values = _payload_with_extra(payload.model_dump(mode="json"))
        values["severity"] = payload.severity.value
        incident = Incident(**values)
        self.session.add(incident)
        try:
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
        except IntegrityError:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.get_incident_by_idempotency_key(payload.idempotency_key)
                if existing is not None:
                    return existing, False
            raise
        await self.session.refresh(incident)
        return incident, True

    async def get_incident_by_idempotency_key(self, idempotency_key: str) -> Incident | None:
        stmt = select(Incident).where(Incident.idempotency_key == idempotency_key)
        return await self.session.scalar(stmt)

    async def attach_workflow(
        self,
        incident_id: str,
        *,
        workflow_id: str,
        workflow_run_id: str | None,
        actor: str,
    ) -> Incident:
        incident = await self.get_incident(incident_id)
        if incident.workflow_id == workflow_id and incident.workflow_run_id == workflow_run_id:
            return incident

        incident.workflow_id = workflow_id
        incident.workflow_run_id = workflow_run_id
        self.session.add(
            IncidentEvent(
                incident_id=incident.id,
                event_type="workflow.started",
                producer="temporal",
                payload={
                    "actor": actor,
                    "workflow_id": workflow_id,
                    "workflow_run_id": workflow_run_id,
                },
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

    async def list_evidence(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[EvidenceItem]:
        await self.get_incident(incident_id)
        stmt = (
            select(EvidenceItem)
            .where(EvidenceItem.incident_id == incident_id)
            .order_by(EvidenceItem.created_at)
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_tool_call(
        self,
        incident_id: str,
        *,
        tool_server: str,
        tool_name: str,
        parameters: dict[str, Any],
        result: dict[str, Any] | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> ToolCall:
        await self.get_incident(incident_id)
        tool_call = ToolCall(
            incident_id=incident_id,
            tool_server=tool_server,
            tool_name=tool_name,
            parameters_hash=_stable_hash(parameters),
            result_hash=_stable_hash(result) if result is not None else None,
            latency_ms=latency_ms,
            error=error,
        )
        self.session.add(tool_call)
        await self.session.commit()
        await self.session.refresh(tool_call)
        return tool_call

    async def list_tool_calls(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[ToolCall]:
        await self.get_incident(incident_id)
        stmt = (
            select(ToolCall)
            .where(ToolCall.incident_id == incident_id)
            .order_by(ToolCall.created_at)
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_rca_hypothesis(
        self, incident_id: str, payload: RCAHypothesisCreate
    ) -> RCAHypothesis:
        await self.get_incident(incident_id)
        hypothesis = RCAHypothesis(
            incident_id=incident_id,
            **payload.model_dump(mode="json"),
        )
        self.session.add(hypothesis)
        await self.session.commit()
        await self.session.refresh(hypothesis)
        return hypothesis

    async def list_rca_hypotheses(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[RCAHypothesis]:
        await self.get_incident(incident_id)
        stmt = (
            select(RCAHypothesis)
            .where(RCAHypothesis.incident_id == incident_id)
            .order_by(RCAHypothesis.rank, RCAHypothesis.created_at)
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_model_call(self, incident_id: str, payload: ModelCallCreate) -> ModelCall:
        await self.get_incident(incident_id)
        model_call = ModelCall(
            incident_id=incident_id,
            **payload.model_dump(mode="json"),
        )
        self.session.add(model_call)
        await self.session.commit()
        await self.session.refresh(model_call)
        return model_call

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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

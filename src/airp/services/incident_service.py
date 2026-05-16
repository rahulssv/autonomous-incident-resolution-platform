import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.errors import NotFoundError
from airp.db.models.incident import (
    DocumentationReport,
    EvidenceItem,
    GitHubArtifact,
    Incident,
    IncidentEmbedding,
    IncidentEvent,
    ModelCall,
    RCAHypothesis,
    RemediationPlan,
    SlackMessage,
    ToolCall,
)
from airp.domain.enums import IncidentStatus
from airp.schemas.incidents import (
    DocumentationReportCreate,
    EvidenceItemCreate,
    IncidentCreate,
    IncidentEmbeddingCreate,
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

    async def count_incidents(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        service_id: str | None = None,
        environment: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Incident)
        if status:
            stmt = stmt.where(Incident.status == status)
        if severity:
            stmt = stmt.where(Incident.severity == severity)
        if service_id:
            stmt = stmt.where(Incident.service_id == service_id)
        if environment:
            stmt = stmt.where(Incident.environment == environment)
        return int(await self.session.scalar(stmt) or 0)

    async def get_incident(self, incident_id: str) -> Incident:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundError("incident", incident_id)
        return incident

    async def get_events(
        self, incident_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[IncidentEvent]:
        await self.get_incident(incident_id)
        stmt = (
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.created_at)
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())

    async def count_events(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(IncidentEvent, incident_id)

    async def get_latest_workflow_event(self, incident_id: str) -> IncidentEvent | None:
        await self.get_incident(incident_id)
        stmt = (
            select(IncidentEvent)
            .where(
                IncidentEvent.incident_id == incident_id,
                or_(
                    IncidentEvent.event_type.like("workflow.%"),
                    IncidentEvent.producer == "temporal-workflow",
                ),
            )
            .order_by(IncidentEvent.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

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

    async def count_evidence(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(EvidenceItem, incident_id)

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

    async def count_tool_calls(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(ToolCall, incident_id)

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

    async def count_rca_hypotheses(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(RCAHypothesis, incident_id)

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

    async def list_model_calls(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[ModelCall]:
        await self.get_incident(incident_id)
        stmt = (
            select(ModelCall)
            .where(ModelCall.incident_id == incident_id)
            .order_by(ModelCall.created_at)
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_model_calls(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(ModelCall, incident_id)

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

    async def list_remediation_plans(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[RemediationPlan]:
        await self.get_incident(incident_id)
        stmt = (
            select(RemediationPlan)
            .where(RemediationPlan.incident_id == incident_id)
            .order_by(RemediationPlan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_remediation_plans(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(RemediationPlan, incident_id)

    async def create_documentation_report(
        self,
        incident_id: str,
        payload: DocumentationReportCreate,
    ) -> DocumentationReport:
        await self.get_incident(incident_id)
        values = _payload_with_extra(payload.model_dump(mode="json"))
        report = DocumentationReport(incident_id=incident_id, **values)
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def list_documentation_reports(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[DocumentationReport]:
        await self.get_incident(incident_id)
        stmt = (
            select(DocumentationReport)
            .where(DocumentationReport.incident_id == incident_id)
            .order_by(DocumentationReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_documentation_reports(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(DocumentationReport, incident_id)

    async def get_documentation_report(
        self, incident_id: str, report_id: str
    ) -> DocumentationReport:
        await self.get_incident(incident_id)
        report = await self.session.get(DocumentationReport, report_id)
        if report is None or report.incident_id != incident_id:
            raise NotFoundError("documentation_report", report_id)
        return report

    async def list_github_artifacts(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[GitHubArtifact]:
        await self.get_incident(incident_id)
        stmt = (
            select(GitHubArtifact)
            .where(GitHubArtifact.incident_id == incident_id)
            .order_by(GitHubArtifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_github_artifacts(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(GitHubArtifact, incident_id)

    async def record_github_issue(
        self,
        incident_id: str,
        *,
        repository_url: str,
        artifact_url: str,
        external_id: str | None,
        metadata: dict[str, Any],
    ) -> GitHubArtifact:
        incident = await self.get_incident(incident_id)
        incident.github_issue_url = artifact_url
        artifact = GitHubArtifact(
            incident_id=incident_id,
            artifact_type="issue",
            repository_url=repository_url,
            artifact_url=artifact_url,
            external_id=external_id,
            extra=metadata,
        )
        self.session.add(artifact)
        self.session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type="github.issue.created",
                producer="github-mcp",
                payload={
                    "repository_url": repository_url,
                    "artifact_url": artifact_url,
                    "external_id": external_id,
                    **metadata,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def list_slack_messages(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[SlackMessage]:
        await self.get_incident(incident_id)
        stmt = (
            select(SlackMessage)
            .where(SlackMessage.incident_id == incident_id)
            .order_by(SlackMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_slack_messages(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(SlackMessage, incident_id)

    async def record_slack_message(
        self,
        incident_id: str,
        *,
        channel: str,
        message_ts: str | None,
        thread_ts: str | None,
        message_url: str | None,
        payload: dict[str, Any],
    ) -> SlackMessage:
        incident = await self.get_incident(incident_id)
        if message_url:
            incident.slack_thread_url = message_url
        message = SlackMessage(
            incident_id=incident_id,
            channel=channel,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_url=message_url,
            payload=payload,
        )
        self.session.add(message)
        self.session.add(
            IncidentEvent(
                incident_id=incident_id,
                event_type="slack.notification.sent",
                producer="slack",
                payload={
                    "channel": channel,
                    "message_ts": message_ts,
                    "thread_ts": thread_ts,
                    "message_url": message_url,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def create_incident_embedding(
        self,
        incident_id: str,
        payload: IncidentEmbeddingCreate,
    ) -> IncidentEmbedding:
        await self.get_incident(incident_id)
        embedding = IncidentEmbedding(
            incident_id=incident_id,
            **payload.model_dump(mode="json"),
        )
        self.session.add(embedding)
        await self.session.commit()
        await self.session.refresh(embedding)
        return embedding

    async def list_incident_embeddings(
        self, incident_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[IncidentEmbedding]:
        await self.get_incident(incident_id)
        stmt = (
            select(IncidentEmbedding)
            .where(IncidentEmbedding.incident_id == incident_id)
            .order_by(IncidentEmbedding.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_incident_embeddings(self, incident_id: str) -> int:
        await self.get_incident(incident_id)
        return await self._count_for_incident(IncidentEmbedding, incident_id)

    async def _count_for_incident(self, model, incident_id: str) -> int:
        stmt = select(func.count()).select_from(model).where(model.incident_id == incident_id)
        return int(await self.session.scalar(stmt) or 0)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

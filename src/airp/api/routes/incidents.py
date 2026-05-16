import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.common import OperatorCommandRead, Page
from airp.schemas.incidents import (
    DocumentationReportRead,
    DocumentationRepublishRequest,
    EvidenceItemCreate,
    EvidenceItemRead,
    GitHubArtifactRead,
    IncidentAuditExportRead,
    IncidentCreate,
    IncidentEmbeddingRead,
    IncidentEventCreate,
    IncidentEventRead,
    IncidentRead,
    IncidentSignal,
    IncidentTimeline,
    IncidentWorkflowStateRead,
    ModelCallRead,
    RCAHypothesisRead,
    RemediationPlanCreate,
    RemediationPlanRead,
    SlackMessageRead,
    ToolCallRead,
    WorkflowSignalRequest,
)
from airp.services.incident_service import IncidentService
from airp.services.workflow_service import IncidentWorkflowSignalService

router = APIRouter()

INCIDENT_ARTIFACT_PAGE_RESPONSES = {
    200: {
        "description": "Paginated incident artifact list.",
        "content": {
            "application/json": {
                "example": {
                    "items": [],
                    "total": 0,
                    "limit": 100,
                    "offset": 0,
                }
            }
        },
    }
}

WORKFLOW_STATE_RESPONSES = {
    200: {
        "description": "Current persisted incident workflow state.",
        "content": {
            "application/json": {
                "example": {
                    "incident_id": "inc_123",
                    "incident_status": "validated",
                    "workflow_id": "airp-incident-inc_123",
                    "workflow_run_id": "run_123",
                    "has_workflow": True,
                    "latest_workflow_event": None,
                }
            }
        },
    }
}

AUDIT_EXPORT_RESPONSES = {
    200: {
        "description": "JSON audit export for an incident.",
        "content": {
            "application/json": {
                "example": {
                    "incident": {
                        "id": "inc_123",
                        "title": "Checkout latency spike",
                        "status": "validated",
                    },
                    "events": [],
                    "exported_at": "2026-05-16T00:00:00Z",
                    "format_version": "airp.incident_audit.v1",
                }
            }
        },
    }
}

DOCUMENTATION_REPUBLISH_RESPONSES = {
    202: {
        "description": "Documentation republish request recorded without external publishing.",
        "content": {
            "application/json": {
                "example": {
                    "operation_id": "doc-republish-123",
                    "operation": "documentation.republish",
                    "status": "disabled_by_policy",
                    "message": "Documentation publishing is disabled by policy.",
                    "external_execution_enabled": False,
                    "requested_at": "2026-05-16T00:00:00Z",
                    "payload": {"report_id": "report_123"},
                }
            }
        },
    }
}


@router.post("", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    session: DbSession,
    principal: CurrentPrincipal,
) -> IncidentRead:
    incident = await IncidentService(session).create_incident(
        payload,
        actor=principal.username or principal.subject,
    )
    return IncidentRead.model_validate(incident)


@router.get("", response_model=list[IncidentRead])
async def list_incidents(
    session: DbSession,
    _: CurrentPrincipal,
    incident_status: Annotated[str | None, Query(alias="status")] = None,
    severity: str | None = None,
    service_id: str | None = None,
    environment: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IncidentRead]:
    incidents = await IncidentService(session).list_incidents(
        status=incident_status,
        severity=severity,
        service_id=service_id,
        environment=environment,
        limit=limit,
        offset=offset,
    )
    return [IncidentRead.model_validate(incident) for incident in incidents]


@router.get("/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> IncidentRead:
    incident = await IncidentService(session).get_incident(incident_id)
    return IncidentRead.model_validate(incident)


@router.get("/{incident_id}/timeline", response_model=IncidentTimeline)
async def get_timeline(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> IncidentTimeline:
    service = IncidentService(session)
    incident = await service.get_incident(incident_id)
    events = await service.get_events(incident_id)
    return IncidentTimeline(
        incident=IncidentRead.model_validate(incident),
        events=[IncidentEventRead.model_validate(event) for event in events],
    )


@router.get(
    "/{incident_id}/workflow/state",
    response_model=IncidentWorkflowStateRead,
    responses=WORKFLOW_STATE_RESPONSES,
)
async def get_workflow_state(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> IncidentWorkflowStateRead:
    service = IncidentService(session)
    incident = await service.get_incident(incident_id)
    latest_workflow_event = await service.get_latest_workflow_event(incident_id)
    return IncidentWorkflowStateRead(
        incident_id=incident.id,
        incident_status=incident.status,
        workflow_id=incident.workflow_id,
        workflow_run_id=incident.workflow_run_id,
        has_workflow=bool(incident.workflow_id),
        latest_workflow_event=(
            IncidentEventRead.model_validate(latest_workflow_event)
            if latest_workflow_event is not None
            else None
        ),
    )


@router.get("/{incident_id}/audit", response_model=list[IncidentEventRead])
async def get_audit_events(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> list[IncidentEventRead]:
    events = await IncidentService(session).get_events(incident_id)
    return [IncidentEventRead.model_validate(event) for event in events]


@router.get(
    "/{incident_id}/audit/export",
    response_model=IncidentAuditExportRead,
    responses=AUDIT_EXPORT_RESPONSES,
)
async def export_audit_events(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> IncidentAuditExportRead:
    service = IncidentService(session)
    incident = await service.get_incident(incident_id)
    events = await service.get_events(incident_id)
    return IncidentAuditExportRead(
        incident=IncidentRead.model_validate(incident),
        events=[IncidentEventRead.model_validate(event) for event in events],
        exported_at=datetime.now(UTC),
    )


@router.post(
    "/{incident_id}/events", response_model=IncidentEventRead, status_code=status.HTTP_201_CREATED
)
async def add_incident_event(
    incident_id: str,
    payload: IncidentEventCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> IncidentEventRead:
    event = await IncidentService(session).add_event(incident_id, payload)
    return IncidentEventRead.model_validate(event)


@router.post("/{incident_id}/signals", response_model=IncidentRead)
async def signal_incident(
    incident_id: str,
    payload: IncidentSignal,
    session: DbSession,
    principal: CurrentPrincipal,
) -> IncidentRead:
    incident = await IncidentService(session).signal_incident(
        incident_id,
        payload,
        actor=principal.username or principal.subject,
    )
    return IncidentRead.model_validate(incident)


@router.post("/{incident_id}/workflow/signals", response_model=IncidentEventRead)
async def signal_incident_workflow(
    incident_id: str,
    payload: WorkflowSignalRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> IncidentEventRead:
    incident_service = IncidentService(session)
    event = await IncidentWorkflowSignalService(incident_service).signal_workflow(
        incident_id,
        payload,
        actor=principal.username or principal.subject,
    )
    return IncidentEventRead.model_validate(event)


@router.post(
    "/{incident_id}/evidence", response_model=EvidenceItemRead, status_code=status.HTTP_201_CREATED
)
async def add_evidence(
    incident_id: str,
    payload: EvidenceItemCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> EvidenceItemRead:
    evidence = await IncidentService(session).add_evidence(incident_id, payload)
    return EvidenceItemRead.model_validate(evidence)


@router.get(
    "/{incident_id}/evidence",
    response_model=Page[EvidenceItemRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_evidence(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EvidenceItemRead]:
    service = IncidentService(session)
    evidence_items = await service.list_evidence(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [EvidenceItemRead.model_validate(item) for item in evidence_items]
    total = await service.count_evidence(incident_id)
    return Page[EvidenceItemRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/tool-calls",
    response_model=Page[ToolCallRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_tool_calls(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ToolCallRead]:
    service = IncidentService(session)
    tool_calls = await service.list_tool_calls(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [ToolCallRead.model_validate(tool_call) for tool_call in tool_calls]
    total = await service.count_tool_calls(incident_id)
    return Page[ToolCallRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/hypotheses",
    response_model=Page[RCAHypothesisRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_rca_hypotheses(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RCAHypothesisRead]:
    service = IncidentService(session)
    hypotheses = await service.list_rca_hypotheses(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [RCAHypothesisRead.model_validate(hypothesis) for hypothesis in hypotheses]
    total = await service.count_rca_hypotheses(incident_id)
    return Page[RCAHypothesisRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/model-calls",
    response_model=Page[ModelCallRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_model_calls(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ModelCallRead]:
    service = IncidentService(session)
    model_calls = await service.list_model_calls(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [ModelCallRead.model_validate(model_call) for model_call in model_calls]
    total = await service.count_model_calls(incident_id)
    return Page[ModelCallRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/embeddings",
    response_model=Page[IncidentEmbeddingRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_incident_embeddings(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IncidentEmbeddingRead]:
    service = IncidentService(session)
    embeddings = await service.list_incident_embeddings(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [_embedding_read(embedding) for embedding in embeddings]
    total = await service.count_incident_embeddings(incident_id)
    return Page[IncidentEmbeddingRead](items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{incident_id}/remediation-plans",
    response_model=RemediationPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_remediation_plan(
    incident_id: str,
    payload: RemediationPlanCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> RemediationPlanRead:
    plan = await IncidentService(session).create_remediation_plan(incident_id, payload)
    return RemediationPlanRead.model_validate(plan)


@router.get(
    "/{incident_id}/remediation-plans",
    response_model=Page[RemediationPlanRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_remediation_plans(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RemediationPlanRead]:
    service = IncidentService(session)
    plans = await service.list_remediation_plans(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [RemediationPlanRead.model_validate(plan) for plan in plans]
    total = await service.count_remediation_plans(incident_id)
    return Page[RemediationPlanRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/documentation-reports",
    response_model=Page[DocumentationReportRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_documentation_reports(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DocumentationReportRead]:
    service = IncidentService(session)
    reports = await service.list_documentation_reports(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [DocumentationReportRead.model_validate(report) for report in reports]
    total = await service.count_documentation_reports(incident_id)
    return Page[DocumentationReportRead](items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{incident_id}/documentation-reports/{report_id}/republish",
    response_model=OperatorCommandRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses=DOCUMENTATION_REPUBLISH_RESPONSES,
)
async def request_documentation_republish(
    incident_id: str,
    report_id: str,
    payload: DocumentationRepublishRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> OperatorCommandRead:
    service = IncidentService(session)
    report = await service.get_documentation_report(incident_id, report_id)
    event = await service.add_event(
        incident_id,
        IncidentEventCreate(
            event_type="documentation.republish_requested",
            producer="api",
            payload={
                "actor": principal.username or principal.subject,
                "report_id": report.id,
                "target": payload.target,
                "reason": payload.reason,
                "force": payload.force,
                "metadata": payload.metadata,
                "external_execution_enabled": False,
                "status": "disabled_by_policy",
            },
        ),
    )
    return OperatorCommandRead(
        operation_id=f"documentation-republish-{uuid4()}",
        operation="documentation.republish",
        status="disabled_by_policy",
        message="Documentation publishing is disabled by policy.",
        external_execution_enabled=False,
        requested_at=datetime.now(UTC),
        payload={
            "incident_id": incident_id,
            "report_id": report.id,
            "event_id": event.id,
            "target": payload.target,
        },
    )


@router.get(
    "/{incident_id}/github-artifacts",
    response_model=Page[GitHubArtifactRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_github_artifacts(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[GitHubArtifactRead]:
    service = IncidentService(session)
    artifacts = await service.list_github_artifacts(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [GitHubArtifactRead.model_validate(artifact) for artifact in artifacts]
    total = await service.count_github_artifacts(incident_id)
    return Page[GitHubArtifactRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{incident_id}/slack-messages",
    response_model=Page[SlackMessageRead],
    responses=INCIDENT_ARTIFACT_PAGE_RESPONSES,
)
async def list_slack_messages(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SlackMessageRead]:
    service = IncidentService(session)
    messages = await service.list_slack_messages(
        incident_id,
        limit=limit,
        offset=offset,
    )
    items = [SlackMessageRead.model_validate(message) for message in messages]
    total = await service.count_slack_messages(incident_id)
    return Page[SlackMessageRead](items=items, total=total, limit=limit, offset=offset)


def _embedding_read(embedding) -> IncidentEmbeddingRead:
    vector = embedding.vector
    has_vector = isinstance(vector, list) and bool(vector)
    return IncidentEmbeddingRead(
        id=embedding.id,
        created_at=embedding.created_at,
        updated_at=embedding.updated_at,
        incident_id=embedding.incident_id,
        embedding_type=embedding.embedding_type,
        text=embedding.text,
        has_vector=has_vector,
        vector_dimension=len(vector) if isinstance(vector, list) else None,
        vector_hash=_stable_hash(vector) if isinstance(vector, list) else None,
    )


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

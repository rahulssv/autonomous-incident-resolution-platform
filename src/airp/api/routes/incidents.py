from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.incidents import (
    EvidenceItemCreate,
    EvidenceItemRead,
    IncidentCreate,
    IncidentEventCreate,
    IncidentEventRead,
    IncidentRead,
    IncidentSignal,
    IncidentTimeline,
    ModelCallRead,
    RCAHypothesisRead,
    RemediationPlanCreate,
    RemediationPlanRead,
    ToolCallRead,
    WorkflowSignalRequest,
)
from airp.services.incident_service import IncidentService
from airp.services.workflow_service import IncidentWorkflowSignalService

router = APIRouter()


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


@router.get("/{incident_id}/audit", response_model=list[IncidentEventRead])
async def get_audit_events(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> list[IncidentEventRead]:
    events = await IncidentService(session).get_events(incident_id)
    return [IncidentEventRead.model_validate(event) for event in events]


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


@router.get("/{incident_id}/evidence", response_model=list[EvidenceItemRead])
async def list_evidence(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvidenceItemRead]:
    evidence_items = await IncidentService(session).list_evidence(
        incident_id,
        limit=limit,
        offset=offset,
    )
    return [EvidenceItemRead.model_validate(item) for item in evidence_items]


@router.get("/{incident_id}/tool-calls", response_model=list[ToolCallRead])
async def list_tool_calls(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ToolCallRead]:
    tool_calls = await IncidentService(session).list_tool_calls(
        incident_id,
        limit=limit,
        offset=offset,
    )
    return [ToolCallRead.model_validate(tool_call) for tool_call in tool_calls]


@router.get("/{incident_id}/hypotheses", response_model=list[RCAHypothesisRead])
async def list_rca_hypotheses(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RCAHypothesisRead]:
    hypotheses = await IncidentService(session).list_rca_hypotheses(
        incident_id,
        limit=limit,
        offset=offset,
    )
    return [RCAHypothesisRead.model_validate(hypothesis) for hypothesis in hypotheses]


@router.get("/{incident_id}/model-calls", response_model=list[ModelCallRead])
async def list_model_calls(
    incident_id: str,
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ModelCallRead]:
    model_calls = await IncidentService(session).list_model_calls(
        incident_id,
        limit=limit,
        offset=offset,
    )
    return [ModelCallRead.model_validate(model_call) for model_call in model_calls]


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

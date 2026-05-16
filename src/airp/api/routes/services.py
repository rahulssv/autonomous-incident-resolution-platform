from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.catalog import DiscoveryRefreshRequest, ServiceCreate, ServiceRead
from airp.schemas.common import OperatorCommandRead
from airp.services.catalog_service import CatalogService

router = APIRouter()

DISCOVERY_REFRESH_RESPONSES = {
    202: {
        "description": "Discovery refresh request accepted as an audit-only command.",
        "content": {
            "application/json": {
                "example": {
                    "operation_id": "refresh_123",
                    "operation": "discovery.refresh",
                    "status": "pending_implementation",
                    "message": "Discovery refresh worker execution is not enabled yet.",
                    "external_execution_enabled": False,
                    "requested_at": "2026-05-16T00:00:00Z",
                    "payload": {"scope": "all"},
                }
            }
        },
    }
}


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> ServiceRead:
    service = await CatalogService(session).create_service(payload)
    return ServiceRead.model_validate(service)


@router.get("", response_model=list[ServiceRead])
async def list_services(
    session: DbSession,
    _: CurrentPrincipal,
    environment: str | None = None,
    namespace: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ServiceRead]:
    services = await CatalogService(session).list_services(
        environment=environment,
        namespace=namespace,
        limit=limit,
        offset=offset,
    )
    return [ServiceRead.model_validate(service) for service in services]


@router.post(
    "/refresh",
    response_model=OperatorCommandRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses=DISCOVERY_REFRESH_RESPONSES,
)
async def request_discovery_refresh(
    payload: DiscoveryRefreshRequest,
    _: DbSession,
    principal: CurrentPrincipal,
) -> OperatorCommandRead:
    return OperatorCommandRead(
        operation_id=f"discovery-refresh-{uuid4()}",
        operation="discovery.refresh",
        status="pending_implementation",
        message="Discovery refresh worker execution is not enabled yet.",
        external_execution_enabled=False,
        requested_at=datetime.now(UTC),
        payload={
            "actor": principal.username or principal.subject,
            "scope": payload.scope,
            "reason": payload.reason,
            "filters": payload.filters,
        },
    )


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(
    service_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> ServiceRead:
    service = await CatalogService(session).get_service(service_id)
    return ServiceRead.model_validate(service)

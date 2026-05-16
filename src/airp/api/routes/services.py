from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.catalog import ServiceCreate, ServiceRead
from airp.services.catalog_service import CatalogService

router = APIRouter()


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


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(
    service_id: str,
    session: DbSession,
    _: CurrentPrincipal,
) -> ServiceRead:
    service = await CatalogService(session).get_service(service_id)
    return ServiceRead.model_validate(service)

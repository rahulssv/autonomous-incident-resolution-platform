from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.catalog import RuntimeWorkloadCreate, RuntimeWorkloadRead
from airp.services.catalog_service import CatalogService

router = APIRouter()


@router.post("", response_model=RuntimeWorkloadRead, status_code=status.HTTP_201_CREATED)
async def upsert_workload(
    payload: RuntimeWorkloadCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> RuntimeWorkloadRead:
    workload = await CatalogService(session).upsert_workload(payload)
    return RuntimeWorkloadRead.model_validate(workload)


@router.get("", response_model=list[RuntimeWorkloadRead])
async def list_workloads(
    session: DbSession,
    _: CurrentPrincipal,
    namespace: str | None = None,
    service_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RuntimeWorkloadRead]:
    workloads = await CatalogService(session).list_workloads(
        namespace=namespace,
        service_id=service_id,
        limit=limit,
        offset=offset,
    )
    return [RuntimeWorkloadRead.model_validate(workload) for workload in workloads]

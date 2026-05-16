from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import AdminPrincipal, DbSession, ReadPrincipal
from airp.api.responses import PAGINATED_LIST_RESPONSES
from airp.schemas.catalog import RuntimeWorkloadCreate, RuntimeWorkloadRead
from airp.schemas.common import Page
from airp.services.catalog_service import CatalogService

router = APIRouter()


@router.post("", response_model=RuntimeWorkloadRead, status_code=status.HTTP_201_CREATED)
async def upsert_workload(
    payload: RuntimeWorkloadCreate,
    session: DbSession,
    _: AdminPrincipal,
) -> RuntimeWorkloadRead:
    workload = await CatalogService(session).upsert_workload(payload)
    return RuntimeWorkloadRead.model_validate(workload)


@router.get("", response_model=Page[RuntimeWorkloadRead], responses=PAGINATED_LIST_RESPONSES)
async def list_workloads(
    session: DbSession,
    _: ReadPrincipal,
    namespace: str | None = None,
    service_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RuntimeWorkloadRead]:
    service = CatalogService(session)
    workloads = await service.list_workloads(
        namespace=namespace,
        service_id=service_id,
        limit=limit,
        offset=offset,
    )
    items = [RuntimeWorkloadRead.model_validate(workload) for workload in workloads]
    total = await service.count_workloads(namespace=namespace, service_id=service_id)
    return Page[RuntimeWorkloadRead](items=items, total=total, limit=limit, offset=offset)

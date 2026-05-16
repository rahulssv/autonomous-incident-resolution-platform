from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import AdminPrincipal, DbSession, ReadPrincipal
from airp.api.responses import PAGINATED_LIST_RESPONSES
from airp.schemas.catalog import RepositoryCreate, RepositoryRead
from airp.schemas.common import Page
from airp.services.catalog_service import CatalogService

router = APIRouter()


@router.post("", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate,
    session: DbSession,
    _: AdminPrincipal,
) -> RepositoryRead:
    repository = await CatalogService(session).create_repository(payload)
    return RepositoryRead.model_validate(repository)


@router.get("", response_model=Page[RepositoryRead], responses=PAGINATED_LIST_RESPONSES)
async def list_repositories(
    session: DbSession,
    _: ReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RepositoryRead]:
    service = CatalogService(session)
    repositories = await service.list_repositories(limit=limit, offset=offset)
    items = [RepositoryRead.model_validate(repository) for repository in repositories]
    total = await service.count_repositories()
    return Page[RepositoryRead](items=items, total=total, limit=limit, offset=offset)

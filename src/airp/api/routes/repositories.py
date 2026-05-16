from typing import Annotated

from fastapi import APIRouter, Query, status

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.catalog import RepositoryCreate, RepositoryRead
from airp.services.catalog_service import CatalogService

router = APIRouter()


@router.post("", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate,
    session: DbSession,
    _: CurrentPrincipal,
) -> RepositoryRead:
    repository = await CatalogService(session).create_repository(payload)
    return RepositoryRead.model_validate(repository)


@router.get("", response_model=list[RepositoryRead])
async def list_repositories(
    session: DbSession,
    _: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RepositoryRead]:
    repositories = await CatalogService(session).list_repositories(limit=limit, offset=offset)
    return [RepositoryRead.model_validate(repository) for repository in repositories]

from typing import Annotated

from fastapi import APIRouter, Query

from airp.api.deps import DbSession, ReadPrincipal
from airp.api.responses import PAGINATED_LIST_RESPONSES
from airp.schemas.common import Page
from airp.schemas.incidents import SearchResult
from airp.services.search_service import SearchService

router = APIRouter()


@router.get(
    "/incidents",
    response_model=Page[SearchResult],
    responses=PAGINATED_LIST_RESPONSES,
)
async def search_incidents(
    session: DbSession,
    _: ReadPrincipal,
    q: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SearchResult]:
    service = SearchService(session)
    items = await service.search_incidents(q, limit=limit, offset=offset)
    total = await service.count_incident_search_results(q)
    return Page[SearchResult](items=items, total=total, limit=limit, offset=offset)

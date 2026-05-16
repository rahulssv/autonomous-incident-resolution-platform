from typing import Annotated

from fastapi import APIRouter, Query

from airp.api.deps import CurrentPrincipal, DbSession
from airp.schemas.incidents import SearchResult
from airp.services.search_service import SearchService

router = APIRouter()


@router.get("/incidents", response_model=list[SearchResult])
async def search_incidents(
    session: DbSession,
    _: CurrentPrincipal,
    q: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[SearchResult]:
    return await SearchService(session).search_incidents(q, limit=limit)

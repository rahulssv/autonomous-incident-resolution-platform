from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airp.db.models.incident import Incident
from airp.schemas.incidents import SearchResult


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search_incidents(
        self, query: str, *, limit: int = 25, offset: int = 0
    ) -> list[SearchResult]:
        pattern = f"%{query}%"
        stmt = (
            select(Incident)
            .where(or_(Incident.title.ilike(pattern), Incident.description.ilike(pattern)))
            .order_by(Incident.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        incidents = list((await self.session.scalars(stmt)).all())
        return [
            SearchResult(
                incident_id=incident.id,
                title=incident.title,
                severity=incident.severity,
                status=incident.status,
                score=None,
                summary=incident.description,
            )
            for incident in incidents
        ]

    async def count_incident_search_results(self, query: str) -> int:
        pattern = f"%{query}%"
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(or_(Incident.title.ilike(pattern), Incident.description.ilike(pattern)))
        )
        return int(await self.session.scalar(stmt) or 0)

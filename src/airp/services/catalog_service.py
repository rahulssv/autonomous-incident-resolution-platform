from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from airp.core.errors import ConflictError, NotFoundError
from airp.db.models.catalog import Repository, RuntimeWorkload, ServiceCatalog
from airp.schemas.catalog import RepositoryCreate, RuntimeWorkloadCreate, ServiceCreate


def _payload_with_extra(payload: dict[str, Any]) -> dict[str, Any]:
    if "metadata" in payload:
        payload["extra"] = payload.pop("metadata")
    return payload


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_services(
        self,
        *,
        environment: str | None = None,
        namespace: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ServiceCatalog]:
        stmt = select(ServiceCatalog).order_by(ServiceCatalog.name).limit(limit).offset(offset)
        if environment:
            stmt = stmt.where(ServiceCatalog.environment == environment)
        if namespace:
            stmt = stmt.where(ServiceCatalog.namespace == namespace)
        return list((await self.session.scalars(stmt)).all())

    async def create_service(self, payload: ServiceCreate) -> ServiceCatalog:
        values = _payload_with_extra(payload.model_dump(mode="json"))
        service = ServiceCatalog(**values)
        self.session.add(service)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Service already exists", {"name": payload.name}) from exc
        await self.session.refresh(service)
        return service

    async def get_service(self, service_id: str) -> ServiceCatalog:
        service = await self.session.get(ServiceCatalog, service_id)
        if service is None:
            raise NotFoundError("service", service_id)
        return service

    async def list_repositories(self, *, limit: int = 100, offset: int = 0) -> list[Repository]:
        stmt = select(Repository).order_by(Repository.name).limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())

    async def create_repository(self, payload: RepositoryCreate) -> Repository:
        values = _payload_with_extra(payload.model_dump(mode="json"))
        repository = Repository(**values)
        self.session.add(repository)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Repository already exists", {"url": str(payload.url)}) from exc
        await self.session.refresh(repository)
        return repository

    async def list_workloads(
        self,
        *,
        namespace: str | None = None,
        service_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RuntimeWorkload]:
        stmt = select(RuntimeWorkload).order_by(RuntimeWorkload.namespace, RuntimeWorkload.pod_name)
        if namespace:
            stmt = stmt.where(RuntimeWorkload.namespace == namespace)
        if service_id:
            stmt = stmt.where(RuntimeWorkload.service_id == service_id)
        stmt = stmt.limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())

    async def upsert_workload(self, payload: RuntimeWorkloadCreate) -> RuntimeWorkload:
        values = _payload_with_extra(payload.model_dump(mode="json"))
        stmt = select(RuntimeWorkload).where(
            RuntimeWorkload.namespace == payload.namespace,
            RuntimeWorkload.pod_name == payload.pod_name,
            RuntimeWorkload.container_name == payload.container_name,
        )
        workload = await self.session.scalar(stmt)
        if workload is None:
            workload = RuntimeWorkload(**values)
            self.session.add(workload)
        else:
            for key, value in values.items():
                setattr(workload, key, value)
        await self.session.commit()
        await self.session.refresh(workload)
        return workload

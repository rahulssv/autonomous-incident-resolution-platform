from fastapi import APIRouter

from airp.api.routes import (
    approvals,
    health,
    incidents,
    policy,
    repositories,
    search,
    services,
    workloads,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(policy.router, tags=["policy"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(approvals.router, tags=["approvals"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
api_router.include_router(workloads.router, prefix="/workloads", tags=["workloads"])
api_router.include_router(search.router, prefix="/search", tags=["search"])

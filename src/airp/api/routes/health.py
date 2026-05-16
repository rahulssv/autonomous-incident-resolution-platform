from typing import Annotated

from fastapi import APIRouter, Depends

from airp.core.config import Settings, get_settings
from airp.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        environment=settings.environment,
        auth_enabled=settings.auth_enabled,
    )

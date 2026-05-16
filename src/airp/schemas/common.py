from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIMessage(BaseModel):
    message: str


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class TimestampedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    auth_enabled: bool

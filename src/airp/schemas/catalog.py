from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from airp.schemas.common import TimestampedRead


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    owner: str | None = Field(default=None, max_length=160)
    environment: str = Field(default="prod", max_length=80)
    namespace: str | None = Field(default=None, max_length=160)
    deployment: str | None = Field(default=None, max_length=160)
    repository_url: HttpUrl | None = None
    docker_image: str | None = Field(default=None, max_length=512)
    slack_channel: str | None = Field(default=None, max_length=160)
    dashboard_url: HttpUrl | None = None
    slo_url: HttpUrl | None = None
    runbook_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceRead(TimestampedRead):
    name: str
    owner: str | None = None
    environment: str
    namespace: str | None = None
    deployment: str | None = None
    repository_url: str | None = None
    docker_image: str | None = None
    slack_channel: str | None = None
    dashboard_url: str | None = None
    slo_url: str | None = None
    runbook_url: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    url: HttpUrl
    default_branch: str = "main"
    owner_team: str | None = None
    docker_image: str | None = None
    ci_workflow: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepositoryRead(TimestampedRead):
    name: str
    url: str
    default_branch: str
    owner_team: str | None = None
    docker_image: str | None = None
    ci_workflow: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class RuntimeWorkloadCreate(BaseModel):
    service_id: str | None = None
    namespace: str
    deployment: str | None = None
    replica_set: str | None = None
    pod_name: str
    container_name: str | None = None
    image: str | None = None
    image_id: str | None = None
    node_name: str | None = None
    ready: bool = False
    restart_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeWorkloadRead(TimestampedRead):
    service_id: str | None = None
    namespace: str
    deployment: str | None = None
    replica_set: str | None = None
    pod_name: str
    container_name: str | None = None
    image: str | None = None
    image_id: str | None = None
    node_name: str | None = None
    ready: bool
    restart_count: int
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class ContainerImageRead(TimestampedRead):
    image_repository: str
    tag: str | None = None
    digest: str | None = None
    source_commit_sha: str | None = None
    build_timestamp: datetime | None = None
    sbom_url: str | None = None
    provenance_url: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )

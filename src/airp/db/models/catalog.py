from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airp.db.models.base import Base, IdMixin, TimestampMixin


class ServiceCatalog(IdMixin, TimestampMixin, Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    environment: Mapped[str] = mapped_column(String(80), default="prod", index=True)
    namespace: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    deployment: Mapped[str | None] = mapped_column(String(160), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    docker_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    slack_channel: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dashboard_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    slo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    runbook_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    workloads: Mapped[list["RuntimeWorkload"]] = relationship(back_populates="service")


class Repository(IdMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    name: Mapped[str] = mapped_column(String(240), index=True)
    url: Mapped[str] = mapped_column(String(512), unique=True)
    default_branch: Mapped[str] = mapped_column(String(160), default="main")
    owner_team: Mapped[str | None] = mapped_column(String(160), nullable=True)
    docker_image: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    ci_workflow: Mapped[str | None] = mapped_column(String(240), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ContainerImage(IdMixin, TimestampMixin, Base):
    __tablename__ = "container_images"
    __table_args__ = (
        UniqueConstraint("image_repository", "tag", "digest", name="uq_image_tag_digest"),
    )

    image_repository: Mapped[str] = mapped_column(String(512), index=True)
    tag: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    digest: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    source_commit_sha: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    build_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sbom_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    provenance_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class RuntimeWorkload(IdMixin, TimestampMixin, Base):
    __tablename__ = "runtime_workloads"

    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.id"), nullable=True, index=True
    )
    namespace: Mapped[str] = mapped_column(String(160), index=True)
    deployment: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    replica_set: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pod_name: Mapped[str] = mapped_column(String(240), index=True)
    container_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    node_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    restart_count: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    service: Mapped[ServiceCatalog | None] = relationship(back_populates="workloads")

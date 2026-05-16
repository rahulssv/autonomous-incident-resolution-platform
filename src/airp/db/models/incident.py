from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airp.db.models.base import Base, IdMixin, TimestampMixin, utc_now
from airp.domain.enums import IncidentSeverity, IncidentStatus, RemediationStatus, RiskLevel


class Incident(IdMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_incidents_idempotency_key"),)

    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(40), default=IncidentSeverity.WARNING.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(80), default=IncidentStatus.RECEIVED.value, index=True
    )
    environment: Mapped[str] = mapped_column(String(80), default="prod", index=True)
    owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    namespace: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    pod_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    image_tag: Mapped[str | None] = mapped_column(String(240), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(240), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    github_issue_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    slack_thread_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    events: Mapped[list["IncidentEvent"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at",
    )


class IncidentEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "incident_events"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    producer: Mapped[str] = mapped_column(String(160), default="api")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    incident: Mapped[Incident] = relationship(back_populates="events")


class EvidenceItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence_items"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(120), index=True)
    source: Mapped[str] = mapped_column(String(160), index=True)
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class RCAHypothesis(IdMixin, TimestampMixin, Base):
    __tablename__ = "rca_hypotheses"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=1)
    hypothesis: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    contradicting_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)


class RemediationPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "remediation_plans"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    plan_summary: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(40), default=RiskLevel.MEDIUM.value)
    status: Mapped[str] = mapped_column(
        String(80), default=RemediationStatus.PROPOSED.value, index=True
    )
    github_issue_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    github_pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    test_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class DocumentationReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "documentation_reports"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(80), default="draft", index=True)
    executive_summary: Mapped[str] = mapped_column(Text)
    root_cause_summary: Mapped[str] = mapped_column(Text)
    impact_summary: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[str] = mapped_column(Text)
    remediation_summary: Mapped[str] = mapped_column(Text)
    follow_up_tasks: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    publish_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    publishing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    published_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    requested_action: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(240))
    approver: Mapped[str | None] = mapped_column(String(240), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class GitHubArtifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "github_artifacts"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    repository_url: Mapped[str] = mapped_column(String(512))
    artifact_url: Mapped[str] = mapped_column(String(1024))
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class SlackMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "slack_messages"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    channel: Mapped[str] = mapped_column(String(160))
    message_ts: Mapped[str | None] = mapped_column(String(120), nullable=True)
    thread_ts: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelCall(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_calls"

    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_result: Mapped[dict] = mapped_column(JSON, default=dict)


class ToolCall(IdMixin, TimestampMixin, Base):
    __tablename__ = "tool_calls"

    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    tool_server: Mapped[str] = mapped_column(String(160), index=True)
    tool_name: Mapped[str] = mapped_column(String(160), index=True)
    parameters_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IncidentEmbedding(IdMixin, TimestampMixin, Base):
    __tablename__ = "incident_embeddings"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    embedding_type: Mapped[str] = mapped_column(String(120), index=True)
    text: Mapped[str] = mapped_column(Text)
    # Production migrations should convert this to pgvector.Vector once dimensions are finalized.
    vector: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

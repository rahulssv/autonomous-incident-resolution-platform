from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from airp.domain.enums import ApprovalDecision, IncidentSeverity, IncidentStatus, RiskLevel
from airp.schemas.common import TimestampedRead


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)
    service_id: str | None = None
    severity: IncidentSeverity = IncidentSeverity.WARNING
    environment: str = Field(default="prod", max_length=80)
    owner: str | None = None
    correlation_id: str | None = None
    namespace: str | None = None
    pod_name: str | None = None
    image_tag: str | None = None
    image_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentRead(TimestampedRead):
    idempotency_key: str | None = None
    service_id: str | None = None
    title: str
    description: str | None = None
    severity: str
    status: str
    environment: str
    owner: str | None = None
    correlation_id: str | None = None
    namespace: str | None = None
    pod_name: str | None = None
    image_tag: str | None = None
    image_digest: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    github_issue_url: str | None = None
    slack_thread_url: str | None = None
    started_at: datetime
    closed_at: datetime | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class IncidentEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    producer: str = Field(default="api", max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)


class IncidentEventRead(TimestampedRead):
    incident_id: str
    event_type: str
    producer: str
    payload: dict[str, Any]


class IncidentSignal(BaseModel):
    status: IncidentStatus
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowSignalRequest(BaseModel):
    signal: Literal["pause", "resume", "approve", "reject", "escalate", "close"]
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class IncidentTimeline(BaseModel):
    incident: IncidentRead
    events: list[IncidentEventRead]


class ApprovalCreate(BaseModel):
    requested_action: str = Field(min_length=1)
    requested_by: str = Field(min_length=1, max_length=240)
    payload_hash: str = Field(min_length=12, max_length=128)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionCreate(BaseModel):
    decision: ApprovalDecision
    approver: str = Field(min_length=1, max_length=240)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalRead(TimestampedRead):
    incident_id: str
    requested_action: str
    requested_by: str
    approver: str | None = None
    decision: str | None = None
    payload_hash: str
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class EvidenceItemCreate(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceItemRead(TimestampedRead):
    incident_id: str
    evidence_type: str
    source: str
    summary: str
    data: dict[str, Any]


class ToolCallRead(TimestampedRead):
    incident_id: str | None = None
    tool_server: str
    tool_name: str
    parameters_hash: str | None = None
    result_hash: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class RCAHypothesisCreate(BaseModel):
    rank: int = Field(ge=1)
    hypothesis: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: dict[str, Any] = Field(default_factory=dict)
    contradicting_evidence: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = Field(default=None, max_length=160)


class RCAHypothesisRead(TimestampedRead):
    incident_id: str
    rank: int
    hypothesis: str
    confidence: float
    supporting_evidence: dict[str, Any]
    contradicting_evidence: dict[str, Any]
    model_name: str | None = None


class ModelCallCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=160)
    prompt_template_version: str | None = Field(default=None, max_length=120)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    response_hash: str | None = Field(default=None, max_length=128)
    validation_result: dict[str, Any] = Field(default_factory=dict)


class ModelCallRead(TimestampedRead):
    incident_id: str | None = None
    model_name: str
    prompt_template_version: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    response_hash: str | None = None
    validation_result: dict[str, Any]


class RemediationPlanCreate(BaseModel):
    plan_summary: str = Field(min_length=1)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    github_issue_url: HttpUrl | None = None
    github_pr_url: HttpUrl | None = None
    test_plan: str | None = None
    rollback_plan: str | None = None
    approval_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemediationPlanRead(TimestampedRead):
    incident_id: str
    plan_summary: str
    risk_level: str
    status: str
    github_issue_url: str | None = None
    github_pr_url: str | None = None
    test_plan: str | None = None
    rollback_plan: str | None = None
    approval_required: bool
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class DocumentationReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    status: str = Field(default="draft", min_length=1, max_length=80)
    executive_summary: str = Field(min_length=1)
    root_cause_summary: str = Field(min_length=1)
    impact_summary: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    remediation_summary: str = Field(min_length=1)
    follow_up_tasks: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    publish_recommended: bool = False
    publishing_enabled: bool = False
    published_url: HttpUrl | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentationReportRead(TimestampedRead):
    incident_id: str
    title: str
    status: str
    executive_summary: str
    root_cause_summary: str
    impact_summary: str
    evidence_summary: str
    remediation_summary: str
    follow_up_tasks: list[str]
    source_refs: list[str]
    publish_recommended: bool
    publishing_enabled: bool
    published_url: str | None = None
    confidence: float
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )


class IncidentEmbeddingCreate(BaseModel):
    embedding_type: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    vector: list[float] | None = None


class IncidentEmbeddingRead(TimestampedRead):
    incident_id: str
    embedding_type: str
    text: str
    has_vector: bool
    vector_dimension: int | None = None
    vector_hash: str | None = None


class SearchResult(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    score: float | None = None
    summary: str | None = None

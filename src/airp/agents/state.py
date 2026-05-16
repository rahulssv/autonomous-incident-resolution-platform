from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    event_type: str
    agent: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MonitoringAssessment(BaseModel):
    valid_alert: bool
    severity: Literal["info", "warning", "critical"]
    affected_service: str | None = None
    noise_risk: Literal["low", "medium", "high"] = "low"
    recommended_next_agent: Literal["correlation", "rca", "escalate"] = "correlation"
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class EmbeddingRun(BaseModel):
    embedded_text_count: int
    vector_count: int
    skipped: bool = False
    reason: str | None = None


class CorrelationResult(BaseModel):
    service_name: str | None = None
    repository_url: str | None = None
    docker_image: str | None = None
    namespace: str | None = None
    pod_name: str | None = None
    workload_match: bool = False
    context_summary: str
    recommended_next_agent: Literal["rca", "escalate"] = "rca"
    confidence: float = Field(ge=0.0, le=1.0)


class RCAEvidenceBundle(BaseModel):
    incident_id: str
    evidence_sources: list[str] = Field(default_factory=list)
    monitoring_summary: str | None = None
    correlation_summary: str | None = None
    service_context: dict[str, Any] = Field(default_factory=dict)
    workload_context: dict[str, Any] = Field(default_factory=dict)
    kubernetes: dict[str, Any] = Field(default_factory=dict)
    github: dict[str, Any] = Field(default_factory=dict)
    dockerhub: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class RCAPlan(BaseModel):
    status: Literal["ready_for_evidence_collection", "needs_manual_triage"]
    summary: str
    evidence_bundle: RCAEvidenceBundle
    next_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class AgentGraphState(TypedDict, total=False):
    incident_id: str
    workflow_id: str | None
    title: str
    description: str | None
    severity: str
    status: str
    correlation_id: str | None
    service_context: dict[str, Any]
    workload_context: dict[str, Any]
    monitoring_assessment: dict[str, Any]
    correlation_result: dict[str, Any]
    rca_plan: dict[str, Any]
    rca_evidence_bundle: dict[str, Any]
    embedding_run: dict[str, Any]
    embedding_texts: list[str]
    embedding_vectors: list[list[float]]
    evidence_ids: list[str]
    tool_calls: list[dict[str, Any]]
    errors: list[str]
    next_action: str
    agent_events: list[dict[str, Any]]

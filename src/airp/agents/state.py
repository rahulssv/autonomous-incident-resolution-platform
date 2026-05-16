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


class AgentGraphState(TypedDict, total=False):
    incident_id: str
    workflow_id: str | None
    title: str
    description: str | None
    severity: str
    status: str
    correlation_id: str | None
    monitoring_assessment: dict[str, Any]
    embedding_run: dict[str, Any]
    embedding_texts: list[str]
    embedding_vectors: list[list[float]]
    evidence_ids: list[str]
    errors: list[str]
    next_action: str
    agent_events: list[dict[str, Any]]

from __future__ import annotations

import json
from typing import Any, Protocol

from airp.agents.state import AgentEvent, AgentGraphState, MonitoringAssessment
from airp.core.config import Settings, get_settings
from airp.domain.enums import IncidentSeverity


class StructuredChatClient(Protocol):
    def structured_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[MonitoringAssessment],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> MonitoringAssessment:
        """Return a validated structured response from the LLM gateway."""


class MonitoringAgent:
    name = "monitoring"

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: StructuredChatClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        assessment = await self.assess(state)
        event = AgentEvent(
            event_type="monitoring.assessed",
            agent=self.name,
            payload=assessment.model_dump(mode="json"),
        )
        return {
            "monitoring_assessment": assessment.model_dump(mode="json"),
            "next_action": assessment.recommended_next_agent,
            "agent_events": [event.model_dump(mode="json")],
        }

    async def assess(self, state: AgentGraphState) -> MonitoringAssessment:
        if self.llm_client is not None:
            try:
                return self.llm_client.structured_chat(
                    model=self.settings.llm_monitoring_model,
                    messages=self._messages(state),
                    response_model=MonitoringAssessment,
                    temperature=0.0,
                    request_id=state.get("correlation_id") or state.get("incident_id"),
                )
            except Exception as exc:  # noqa: BLE001 - monitoring must degrade gracefully
                return self._deterministic_assessment(
                    state,
                    reason=f"Structured monitoring assessment failed: {exc}",
                )
        return self._deterministic_assessment(state)

    def _messages(self, state: AgentGraphState) -> list[dict[str, Any]]:
        response_schema = {
            "valid_alert": "boolean",
            "severity": "one of: info, warning, critical",
            "affected_service": "string or null",
            "noise_risk": "one of: low, medium, high",
            "recommended_next_agent": "one of: correlation, rca, escalate",
            "summary": "string",
            "confidence": "number between 0 and 1",
        }
        return [
            {
                "role": "system",
                "content": (
                    "You are the AIRP Monitoring Agent. Validate incident alerts and return "
                    "only a single JSON object matching the required schema. Do not wrap the "
                    "JSON in prose or markdown. Do not invent evidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "required_response_schema": response_schema,
                        "incident_id": state.get("incident_id"),
                        "title": state.get("title"),
                        "description": state.get("description"),
                        "severity": state.get("severity"),
                        "status": state.get("status"),
                    },
                    separators=(",", ":"),
                ),
            },
        ]

    def _deterministic_assessment(
        self,
        state: AgentGraphState,
        *,
        reason: str | None = None,
    ) -> MonitoringAssessment:
        severity = self._severity(state.get("severity"))
        summary = f"Incident {state.get('incident_id')} accepted for {severity} processing."
        if reason:
            summary = f"{summary} {reason}"
        return MonitoringAssessment(
            valid_alert=True,
            severity=severity,
            affected_service=None,
            noise_risk="low",
            recommended_next_agent=(
                "rca" if severity == IncidentSeverity.CRITICAL.value else "correlation"
            ),
            summary=summary,
            confidence=0.65,
        )

    def _severity(self, value: str | None) -> str:
        if value in {item.value for item in IncidentSeverity}:
            return value
        return IncidentSeverity.WARNING.value

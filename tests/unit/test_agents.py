from __future__ import annotations

import pytest

from airp.agents.embedding import EmbeddingAgent
from airp.agents.monitoring import MonitoringAgent
from airp.agents.state import AgentGraphState, MonitoringAssessment
from airp.agents.supervisor import LangGraphSupervisor
from airp.core.config import Settings

pytestmark = pytest.mark.asyncio


class FakeMonitoringClient:
    def __init__(self) -> None:
        self.calls = []

    def structured_chat(self, **kwargs) -> MonitoringAssessment:
        self.calls.append(kwargs)
        return MonitoringAssessment(
            valid_alert=True,
            severity="critical",
            affected_service="checkout-api",
            noise_risk="low",
            recommended_next_agent="rca",
            summary="Checkout alert is valid and needs RCA.",
            confidence=0.91,
        )


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.inputs = []

    def embed(self, *, input_text: str | list[str], model: str | None = None) -> list[list[float]]:
        self.inputs.append((input_text, model))
        count = len(input_text) if isinstance(input_text, list) else 1
        return [[0.1, 0.2, 0.3] for _ in range(count)]


def sample_state() -> AgentGraphState:
    return {
        "incident_id": "inc-1",
        "workflow_id": "airp-incident-inc-1",
        "title": "Checkout latency spike",
        "description": "p95 latency is above SLO",
        "severity": "critical",
        "status": "validated",
        "correlation_id": "corr-1",
        "agent_events": [],
        "evidence_ids": [],
        "errors": [],
    }


async def test_monitoring_agent_validates_mocked_genaihub_output() -> None:
    client = FakeMonitoringClient()
    agent = MonitoringAgent(
        settings=Settings(llm_monitoring_model="gpt-4.1-nano"),
        llm_client=client,
    )

    update = await agent(sample_state())

    assert update["monitoring_assessment"]["valid_alert"] is True
    assert update["monitoring_assessment"]["recommended_next_agent"] == "rca"
    assert update["agent_events"][0]["event_type"] == "monitoring.assessed"
    assert client.calls[0]["model"] == "gpt-4.1-nano"


async def test_embedding_agent_redacts_text_before_embedding() -> None:
    client = FakeEmbeddingClient()
    agent = EmbeddingAgent(settings=Settings(llm_embedding_model="embeddings"), embedder=client)
    state = sample_state()
    state["description"] = "api_key=secret-value p95 latency is above SLO"

    update = await agent(state)

    input_text, model = client.inputs[0]
    assert model == "embeddings"
    assert "secret-value" not in " ".join(input_text)
    assert "[REDACTED]" in " ".join(input_text)
    assert update["embedding_run"]["vector_count"] == len(input_text)


async def test_langgraph_supervisor_routes_monitoring_then_embedding() -> None:
    supervisor = LangGraphSupervisor(
        monitoring_agent=MonitoringAgent(llm_client=FakeMonitoringClient()),
        embedding_agent=EmbeddingAgent(embedder=FakeEmbeddingClient()),
    )

    state = await supervisor.run(
        incident_id="inc-1",
        workflow_id="airp-incident-inc-1",
        title="Checkout latency spike",
        description="p95 latency is above SLO",
        severity="critical",
        status="validated",
        correlation_id="corr-1",
    )

    assert [event["event_type"] for event in state["agent_events"]] == [
        "monitoring.assessed",
        "embedding.generated",
    ]
    assert state["monitoring_assessment"]["affected_service"] == "checkout-api"
    assert state["embedding_run"]["vector_count"] >= 1

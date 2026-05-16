from __future__ import annotations

import pytest

from airp.agents.correlation import CorrelationAgent
from airp.agents.embedding import EmbeddingAgent
from airp.agents.evidence import RCAEvidenceCollector
from airp.agents.monitoring import MonitoringAgent
from airp.agents.rca import RCAAgent
from airp.agents.state import AgentGraphState, MonitoringAssessment
from airp.agents.supervisor import LangGraphSupervisor
from airp.core.config import Settings
from airp.integrations.dockerhub.client import DockerHubClient, DockerHubImageEvidence
from airp.integrations.github_mcp.client import (
    GitHubChangedFileEvidence,
    GitHubCommitEvidence,
    GitHubEvidenceBundle,
    GitHubMCPClient,
)
from airp.integrations.kubernetes_mcp.client import (
    KubernetesEventEvidence,
    KubernetesEvidenceBundle,
    KubernetesLogEvidence,
    KubernetesMCPClient,
    KubernetesPodEvidence,
)

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


async def test_correlation_agent_uses_service_and_workload_context() -> None:
    state = sample_state()
    state["monitoring_assessment"] = {
        "affected_service": "checkout-api",
        "summary": "valid alert",
    }
    state["service_context"] = {
        "name": "checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
        "docker_image": "docker.io/airpclient/checkout-api:v1",
        "namespace": "shopfast",
    }
    state["workload_context"] = {
        "namespace": "shopfast",
        "pod_name": "checkout-api-abc123",
        "image": "docker.io/airpclient/checkout-api:v1",
    }

    update = await CorrelationAgent()(state)

    assert update["correlation_result"]["service_name"] == "checkout-api"
    assert update["correlation_result"]["workload_match"] is True
    assert update["correlation_result"]["recommended_next_agent"] == "rca"
    assert update["agent_events"][0]["event_type"] == "correlation.completed"


async def test_rca_agent_builds_evidence_bundle_from_available_context() -> None:
    state = sample_state()
    state["monitoring_assessment"] = {"summary": "Checkout alert is valid."}
    state["correlation_result"] = {"context_summary": "service=checkout-api"}
    state["service_context"] = {"name": "checkout-api"}
    state["workload_context"] = {"pod_name": "checkout-api-abc123"}

    update = await RCAAgent()(state)

    assert update["rca_plan"]["status"] == "ready_for_evidence_collection"
    assert "service_catalog" in update["rca_evidence_bundle"]["evidence_sources"]
    assert "runtime_workload" in update["rca_evidence_bundle"]["evidence_sources"]
    assert update["agent_events"][0]["event_type"] == "rca.started"


async def test_rca_agent_collects_read_only_runtime_repository_and_image_evidence() -> None:
    state = sample_state()
    state["monitoring_assessment"] = {"summary": "Checkout alert is valid."}
    state["correlation_result"] = {
        "context_summary": "service=checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
        "docker_image": "docker.io/airpclient/checkout-api:v1",
    }
    state["service_context"] = {
        "name": "checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
        "docker_image": "docker.io/airpclient/checkout-api:v1",
        "namespace": "shopfast",
        "deployment": "checkout-api",
    }
    state["workload_context"] = {
        "namespace": "shopfast",
        "deployment": "checkout-api",
        "pod_name": "checkout-api-abc123",
        "container_name": "api",
        "image": "docker.io/airpclient/checkout-api:v1",
    }
    collector = RCAEvidenceCollector(
        kubernetes_client=KubernetesMCPClient(
            fixture=KubernetesEvidenceBundle(
                namespace="shopfast",
                pod_name="checkout-api-abc123",
                deployment="checkout-api",
                pods=[
                    KubernetesPodEvidence(
                        namespace="shopfast",
                        name="checkout-api-abc123",
                        restart_count=3,
                    )
                ],
                logs=[
                    KubernetesLogEvidence(
                        namespace="shopfast",
                        pod_name="checkout-api-abc123",
                        container="api",
                        lines=["token=secret-value", "timeout talking to payments"],
                    )
                ],
                events=[
                    KubernetesEventEvidence(
                        namespace="shopfast",
                        reason="BackOff",
                        message="Back-off restarting failed container",
                    )
                ],
            )
        ),
        github_client=GitHubMCPClient(
            fixture=GitHubEvidenceBundle(
                repository_url="https://github.com/AIRP-client/checkout-api",
                default_branch="main",
                commits=[
                    GitHubCommitEvidence(
                        sha="abc123",
                        message="Tighten checkout timeout",
                        changed_files=[
                            GitHubChangedFileEvidence(
                                path="src/checkout/client.py",
                                status="modified",
                            )
                        ],
                    )
                ],
            )
        ),
        dockerhub_client=DockerHubClient(
            fixture={
                "docker.io/airpclient/checkout-api:v1": DockerHubImageEvidence(
                    image="docker.io/airpclient/checkout-api:v1",
                    repository="airpclient/checkout-api",
                    tag="v1",
                    digest="sha256:abc",
                    source_commit_sha="abc123",
                )
            }
        ),
    )

    update = await RCAAgent(evidence_collector=collector)(state)

    bundle = update["rca_evidence_bundle"]
    assert "kubernetes" in bundle["evidence_sources"]
    assert "github" in bundle["evidence_sources"]
    assert "dockerhub" in bundle["evidence_sources"]
    assert bundle["kubernetes"]["pods"][0]["restart_count"] == 3
    assert "secret-value" not in bundle["kubernetes"]["logs"][0]["lines"][0]
    assert bundle["github"]["changed_files"][0]["path"] == "src/checkout/client.py"
    assert bundle["dockerhub"]["source_commit_sha"] == "abc123"
    assert {call["tool_server"] for call in update["tool_calls"]} == {
        "kubernetes_mcp",
        "github_mcp",
        "dockerhub",
    }


async def test_langgraph_supervisor_routes_monitoring_correlation_rca_then_embedding() -> None:
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
        service_context={
            "name": "checkout-api",
            "repository_url": "https://github.com/AIRP-client/checkout-api",
            "docker_image": "docker.io/airpclient/checkout-api:v1",
            "namespace": "shopfast",
        },
        workload_context={
            "namespace": "shopfast",
            "pod_name": "checkout-api-abc123",
            "image": "docker.io/airpclient/checkout-api:v1",
        },
    )

    assert [event["event_type"] for event in state["agent_events"]] == [
        "monitoring.assessed",
        "correlation.completed",
        "rca.started",
        "embedding.generated",
    ]
    assert state["monitoring_assessment"]["affected_service"] == "checkout-api"
    assert state["correlation_result"]["repository_url"] == "https://github.com/AIRP-client/checkout-api"
    assert state["rca_plan"]["status"] == "ready_for_evidence_collection"
    assert state["embedding_run"]["vector_count"] >= 1

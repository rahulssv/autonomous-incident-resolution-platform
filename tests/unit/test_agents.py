from __future__ import annotations

import pytest

from airp.agents.correlation import CorrelationAgent
from airp.agents.documentation import DocumentationAgent
from airp.agents.embedding import EmbeddingAgent
from airp.agents.evidence import RCAEvidenceCollector
from airp.agents.monitoring import MonitoringAgent
from airp.agents.rca import RCAAgent
from airp.agents.remediation import RemediationAgent
from airp.agents.state import (
    AgentGraphState,
    DocumentationReportDraft,
    MonitoringAssessment,
    RCAHypothesisOutput,
    RCAHypothesisSet,
    RemediationAgentOutput,
)
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


class FakeRCAClient:
    def __init__(self) -> None:
        self.calls = []

    def structured_chat(self, **kwargs) -> RCAHypothesisSet:
        self.calls.append(kwargs)
        return RCAHypothesisSet(
            summary="Recent checkout change likely increased latency.",
            hypotheses=[
                RCAHypothesisOutput(
                    rank=1,
                    hypothesis="A recent checkout timeout change is the likely cause.",
                    confidence=0.82,
                    supporting_evidence_refs=["correlation", "service_catalog"],
                    contradictions=[],
                    next_actions=["review_checkout_timeout_change"],
                )
            ],
            escalation_required=False,
        )


class FakeRemediationClient:
    def __init__(self) -> None:
        self.calls = []

    def structured_chat(self, **kwargs) -> RemediationAgentOutput:
        self.calls.append(kwargs)
        return RemediationAgentOutput(
            plan_summary="Tune checkout timeout handling behind approval.",
            risk_level="medium",
            risk_score=0.62,
            test_plan="Run checkout unit and integration tests.",
            rollback_plan="Revert timeout change or roll back to the last healthy image.",
            approval_required=True,
            blocked_path_findings=[],
            recommended_actions=["update_timeout_config", "run_checkout_tests"],
            evidence_refs=["github", "kubernetes"],
            external_writes_allowed=True,
            pr_creation_recommended=True,
            confidence=0.8,
        )


class FakeDocumentationClient:
    def __init__(self) -> None:
        self.calls = []

    def structured_chat(self, **kwargs) -> DocumentationReportDraft:
        self.calls.append(kwargs)
        return DocumentationReportDraft(
            title="RCA Draft: Checkout latency spike",
            executive_summary="Checkout latency rose after a recent timeout change.",
            root_cause_summary="Recent checkout timeout change likely increased latency.",
            impact_summary="Critical checkout service latency degraded.",
            evidence_summary="Used Kubernetes restart evidence and GitHub commit evidence.",
            remediation_summary="Prepare a minimal timeout fix after approval.",
            follow_up_tasks=["add_timeout_regression_test"],
            source_refs=["kubernetes", "github"],
            publish_recommended=True,
            publishing_enabled=True,
            confidence=0.82,
        )


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


async def test_embedding_agent_includes_remediation_and_documentation_summaries() -> None:
    client = FakeEmbeddingClient()
    agent = EmbeddingAgent(settings=Settings(llm_embedding_model="embeddings"), embedder=client)
    state = rca_ready_state()
    state["remediation_result"] = {
        "plan_summary": "Prepare a timeout fix after approval.",
        "test_plan": "Run checkout latency regression tests.",
        "rollback_plan": "Roll back to the last healthy Docker image.",
        "recommended_actions": ["review_timeout_change", "run_checkout_tests"],
    }
    state["documentation_report"] = {
        "executive_summary": "Checkout latency increased after a timeout change.",
        "root_cause_summary": "Timeout configuration likely caused the incident.",
        "evidence_summary": "GitHub and Kubernetes evidence were reviewed.",
        "remediation_summary": "Use an approval-gated timeout fix.",
        "follow_up_tasks": ["add_latency_test"],
    }

    update = await agent(state)

    input_text, _ = client.inputs[0]
    joined = " ".join(input_text)
    assert "Prepare a timeout fix after approval." in joined
    assert "Checkout latency increased after a timeout change." in joined
    assert "Documentation follow-ups: add_latency_test" in joined
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
    assert update["rca_hypothesis_result"]["escalation_required"] is True
    assert update["agent_events"][1]["event_type"] == "rca.hypotheses.generated"


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
    assert update["rca_hypotheses"][0]["supporting_evidence_refs"] == [
        "kubernetes",
        "github",
        "dockerhub",
    ]


async def test_rca_agent_generates_structured_hypotheses_with_mocked_genaihub() -> None:
    state = sample_state()
    state["monitoring_assessment"] = {"summary": "Checkout alert is valid."}
    state["correlation_result"] = {
        "context_summary": "service=checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
    }
    state["service_context"] = {"name": "checkout-api"}
    client = FakeRCAClient()

    update = await RCAAgent(
        settings=Settings(llm_rca_model="gpt-5.2-CIO"),
        llm_client=client,
    )(state)

    assert update["rca_hypotheses"][0]["confidence"] == 0.82
    assert update["rca_hypothesis_result"]["summary"].startswith("Recent checkout")
    assert update["model_calls"][0]["model_name"] == "gpt-5.2-CIO"
    assert update["model_calls"][0]["prompt_template_version"] == "rca-hypothesis-v1"
    assert client.calls[0]["response_model"] is RCAHypothesisSet


def rca_ready_state() -> AgentGraphState:
    state = sample_state()
    state["service_context"] = {
        "name": "checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
        "docker_image": "docker.io/airpclient/checkout-api:v1",
        "namespace": "shopfast",
    }
    state["correlation_result"] = {
        "service_name": "checkout-api",
        "repository_url": "https://github.com/AIRP-client/checkout-api",
        "docker_image": "docker.io/airpclient/checkout-api:v1",
        "context_summary": "service=checkout-api repository=checkout-api",
    }
    state["rca_evidence_bundle"] = {
        "incident_id": "inc-1",
        "evidence_sources": ["incident", "kubernetes", "github"],
        "kubernetes": {"logs": [{"lines": ["timeout talking to payments"]}]},
        "github": {"commits": [{"sha": "abc123", "message": "Tighten timeout"}]},
    }
    state["rca_hypothesis_result"] = {
        "summary": "Recent checkout timeout change likely increased latency.",
        "escalation_required": False,
    }
    state["rca_hypotheses"] = [
        {
            "rank": 1,
            "hypothesis": "A recent checkout timeout change is the likely cause.",
            "confidence": 0.78,
            "supporting_evidence_refs": ["kubernetes", "github"],
            "contradictions": [],
            "next_actions": ["review_timeout_change"],
        }
    ]
    return state


async def test_remediation_agent_builds_safe_deterministic_plan() -> None:
    agent = RemediationAgent(
        settings=Settings(remediation_pr_creation_enabled=False),
    )

    update = await agent(rca_ready_state())

    result = update["remediation_result"]
    assert result["approval_required"] is True
    assert result["external_writes_allowed"] is False
    assert result["pr_creation_recommended"] is True
    assert result["risk_level"] == "medium"
    assert "github" in result["evidence_refs"]
    assert result["blocked_path_findings"] == [
        "Remediation PR creation feature flag is disabled"
    ]
    assert update["agent_events"][0]["event_type"] == "remediation.planned"


async def test_remediation_agent_uses_mocked_genaihub_and_policy_grounding() -> None:
    client = FakeRemediationClient()
    agent = RemediationAgent(
        settings=Settings(
            llm_remediation_model="gpt-5.2-CIO",
            remediation_pr_creation_enabled=False,
        ),
        llm_client=client,
    )

    update = await agent(rca_ready_state())

    result = update["remediation_result"]
    assert result["external_writes_allowed"] is False
    assert result["approval_required"] is True
    assert result["risk_score"] == 0.62
    assert "Remediation PR creation feature flag is disabled" in result[
        "blocked_path_findings"
    ]
    assert update["model_calls"][0]["model_name"] == "gpt-5.2-CIO"
    assert update["model_calls"][0]["prompt_template_version"] == "remediation-plan-v1"
    assert client.calls[0]["response_model"] is RemediationAgentOutput


async def test_documentation_agent_builds_safe_deterministic_draft() -> None:
    state = rca_ready_state()
    state["remediation_result"] = {
        "plan_summary": "Prepare a minimal timeout fix after approval.",
        "recommended_actions": ["review_timeout_change"],
        "evidence_refs": ["kubernetes", "github"],
    }
    agent = DocumentationAgent(
        settings=Settings(documentation_publishing_enabled=False),
    )

    update = await agent(state)

    report = update["documentation_report"]
    assert report["publishing_enabled"] is False
    assert report["publish_recommended"] is True
    assert "A recent checkout timeout change" in report["root_cause_summary"]
    assert "github" in report["source_refs"]
    assert "Documentation publishing feature flag is disabled" in report[
        "follow_up_tasks"
    ]
    assert update["agent_events"][0]["event_type"] == "documentation.drafted"


async def test_documentation_agent_uses_mocked_genaihub_and_policy_grounding() -> None:
    client = FakeDocumentationClient()
    state = rca_ready_state()
    state["remediation_result"] = {
        "plan_summary": "Prepare a minimal timeout fix after approval.",
        "recommended_actions": ["review_timeout_change"],
        "evidence_refs": ["kubernetes", "github"],
    }
    agent = DocumentationAgent(
        settings=Settings(
            llm_documentation_model="gpt-4.1",
            documentation_publishing_enabled=False,
        ),
        llm_client=client,
    )

    update = await agent(state)

    report = update["documentation_report"]
    assert report["publishing_enabled"] is False
    assert "Documentation publishing feature flag is disabled" in report[
        "follow_up_tasks"
    ]
    assert update["model_calls"][0]["model_name"] == "gpt-4.1"
    assert update["model_calls"][0]["prompt_template_version"] == "documentation-report-v1"
    assert client.calls[0]["response_model"] is DocumentationReportDraft


async def test_langgraph_supervisor_routes_monitoring_correlation_rca_then_embedding() -> None:
    supervisor = LangGraphSupervisor(
        monitoring_agent=MonitoringAgent(llm_client=FakeMonitoringClient()),
        remediation_agent=RemediationAgent(settings=Settings()),
        documentation_agent=DocumentationAgent(settings=Settings()),
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
        "rca.hypotheses.generated",
        "remediation.planned",
        "documentation.drafted",
        "embedding.generated",
    ]
    assert state["monitoring_assessment"]["affected_service"] == "checkout-api"
    assert state["correlation_result"]["repository_url"] == "https://github.com/AIRP-client/checkout-api"
    assert state["rca_plan"]["status"] == "ready_for_evidence_collection"
    assert state["remediation_result"]["approval_required"] is True
    assert state["documentation_report"]["publishing_enabled"] is False
    assert state["embedding_run"]["vector_count"] >= 1

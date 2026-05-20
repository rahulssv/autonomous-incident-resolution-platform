from __future__ import annotations

from airp.agents.correlation import CorrelationAgent
from airp.agents.documentation import DocumentationAgent
from airp.agents.embedding import EmbeddingAgent
from airp.agents.evidence import RCAEvidenceCollector
from airp.agents.monitoring import MonitoringAgent
from airp.agents.rca import RCAAgent
from airp.agents.remediation import RemediationAgent
from airp.agents.supervisor import LangGraphSupervisor
from airp.core.config import Settings, get_settings
from airp.integrations.dockerhub.client import DockerHubClient
from airp.integrations.genaihub.client import AnthropicGatewayClient, GenAIHubClient
from airp.integrations.github_mcp.client import GitHubMCPClient
from airp.integrations.kubernetes_mcp.client import KubernetesMCPClient


def build_default_agent_supervisor(settings: Settings | None = None) -> LangGraphSupervisor:
    settings = settings or get_settings()
    genai_client = None
    if settings.anthropic_base_url and settings.anthropic_auth_token:
        genai_client = AnthropicGatewayClient(settings)
    elif settings.gateway_base_url and settings.gateway_api_key:
        genai_client = GenAIHubClient(settings)

    # The Anthropic-style gateway does not expose an OpenAI-compatible /v1/embeddings
    # route, so prefer the GenAI Hub gateway for embeddings when it is configured.
    embedding_client = genai_client
    if (
        isinstance(genai_client, AnthropicGatewayClient)
        and settings.gateway_base_url
        and settings.gateway_api_key
    ):
        embedding_client = GenAIHubClient(settings)

    evidence_collector = None
    if settings.agent_read_only_evidence_enabled:
        evidence_collector = RCAEvidenceCollector(
            kubernetes_client=KubernetesMCPClient(
                transport=settings.kubernetes_mcp_transport,
                endpoint_url=str(settings.kubernetes_mcp_url)
                if settings.kubernetes_mcp_url
                else None,
                timeout_seconds=settings.kubernetes_mcp_read_timeout_seconds,
            ),
            github_client=GitHubMCPClient(
                transport=settings.github_mcp_transport,
                endpoint_url=str(settings.github_mcp_url) if settings.github_mcp_url else None,
                timeout_seconds=settings.github_mcp_read_timeout_seconds,
            ),
            dockerhub_client=DockerHubClient(
                base_url=str(settings.dockerhub_base_url),
                timeout_seconds=settings.dockerhub_read_timeout_seconds,
            ),
            allowed_namespaces=settings.kubernetes_mcp_namespace_allowlist,
            allowed_repositories=settings.github_mcp_repository_allowlist,
            retry_attempts=settings.mcp_read_retry_attempts,
            retry_min_backoff_seconds=settings.mcp_read_retry_min_backoff_seconds,
            retry_max_backoff_seconds=settings.mcp_read_retry_max_backoff_seconds,
        )

    # Build a GitHub MCP client for the remediation agent so it can read the
    # suspect file and propose a real code-fix patch when appropriate.
    remediation_github_client = None
    if settings.github_mcp_transport != "disabled" and settings.github_mcp_url:
        remediation_github_client = GitHubMCPClient(
            transport=settings.github_mcp_transport,
            endpoint_url=str(settings.github_mcp_url),
            timeout_seconds=settings.github_mcp_read_timeout_seconds,
        )

    return LangGraphSupervisor(
        monitoring_agent=MonitoringAgent(settings=settings, llm_client=genai_client),
        correlation_agent=CorrelationAgent(),
        rca_agent=RCAAgent(
            settings=settings,
            evidence_collector=evidence_collector,
            llm_client=genai_client,
        ),
        remediation_agent=RemediationAgent(
            settings=settings,
            llm_client=genai_client,
            github_client=remediation_github_client,
        ),
        documentation_agent=DocumentationAgent(settings=settings, llm_client=genai_client),
        embedding_agent=EmbeddingAgent(settings=settings, embedder=embedding_client),
    )

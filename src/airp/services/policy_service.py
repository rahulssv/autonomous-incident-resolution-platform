from __future__ import annotations

from airp.core.config import Settings, get_settings
from airp.core.policy import ExternalActionPolicy, PolicyDecision
from airp.schemas.policy import (
    AllowlistPolicyRead,
    EffectivePolicyRead,
    ExternalActionPolicyRead,
    MCPReadPolicyRead,
    PolicyDecisionRead,
)


def build_effective_policy(settings: Settings | None = None) -> EffectivePolicyRead:
    settings = settings or get_settings()
    external_policy = ExternalActionPolicy(settings)
    return EffectivePolicyRead(
        environment=settings.environment,
        external_actions=ExternalActionPolicyRead(
            github_issue_creation=_decision_read(external_policy.github_issue_creation()),
            slack_notification=_decision_read(external_policy.slack_notification()),
            remediation_pr_creation=_decision_read(external_policy.remediation_pr_creation()),
            documentation_publishing=_decision_read(external_policy.documentation_publishing()),
        ),
        allowlists=AllowlistPolicyRead(
            github_repositories=settings.github_mcp_repository_allowlist,
            kubernetes_namespaces=settings.kubernetes_mcp_namespace_allowlist,
            client_github_org=settings.client_github_org,
        ),
        mcp_read_settings=MCPReadPolicyRead(
            read_only_evidence_enabled=settings.agent_read_only_evidence_enabled,
            kubernetes_transport=settings.kubernetes_mcp_transport,
            kubernetes_endpoint_configured=settings.kubernetes_mcp_url is not None,
            kubernetes_read_timeout_seconds=settings.kubernetes_mcp_read_timeout_seconds,
            github_transport=settings.github_mcp_transport,
            github_endpoint_configured=settings.github_mcp_url is not None,
            github_read_timeout_seconds=settings.github_mcp_read_timeout_seconds,
            dockerhub_base_url=str(settings.dockerhub_base_url),
            dockerhub_read_timeout_seconds=settings.dockerhub_read_timeout_seconds,
            retry_attempts=settings.mcp_read_retry_attempts,
            retry_min_backoff_seconds=settings.mcp_read_retry_min_backoff_seconds,
            retry_max_backoff_seconds=settings.mcp_read_retry_max_backoff_seconds,
        ),
        secrets_redacted=True,
    )


def _decision_read(decision: PolicyDecision) -> PolicyDecisionRead:
    return PolicyDecisionRead(allowed=decision.allowed, reason=decision.reason)

from pydantic import BaseModel


class PolicyDecisionRead(BaseModel):
    allowed: bool
    reason: str


class ExternalActionPolicyRead(BaseModel):
    github_issue_creation: PolicyDecisionRead
    slack_notification: PolicyDecisionRead
    remediation_pr_creation: PolicyDecisionRead
    documentation_publishing: PolicyDecisionRead


class AllowlistPolicyRead(BaseModel):
    github_repositories: list[str]
    kubernetes_namespaces: list[str]
    client_github_org: str


class MCPReadPolicyRead(BaseModel):
    read_only_evidence_enabled: bool
    kubernetes_transport: str
    kubernetes_endpoint_configured: bool
    kubernetes_read_timeout_seconds: float
    github_transport: str
    github_endpoint_configured: bool
    github_read_timeout_seconds: float
    dockerhub_base_url: str
    dockerhub_read_timeout_seconds: float
    retry_attempts: int
    retry_min_backoff_seconds: float
    retry_max_backoff_seconds: float


class EffectivePolicyRead(BaseModel):
    environment: str
    external_actions: ExternalActionPolicyRead
    allowlists: AllowlistPolicyRead
    mcp_read_settings: MCPReadPolicyRead
    secrets_redacted: bool = True

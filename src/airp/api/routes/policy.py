from typing import Annotated

from fastapi import APIRouter, Depends

from airp.api.deps import AdminPrincipal
from airp.core.config import Settings, get_settings
from airp.schemas.policy import EffectivePolicyRead
from airp.services.policy_service import build_effective_policy

router = APIRouter()

POLICY_RESPONSES = {
    200: {
        "description": "Effective runtime automation policy with secrets redacted.",
        "content": {
            "application/json": {
                "example": {
                    "environment": "development",
                    "external_actions": {
                        "github_issue_creation": {
                            "allowed": False,
                            "reason": "GitHub issue creation feature flag is disabled",
                        },
                        "slack_notification": {
                            "allowed": False,
                            "reason": "Slack notification feature flag is disabled",
                        },
                        "remediation_pr_creation": {
                            "allowed": False,
                            "reason": "Remediation PR creation feature flag is disabled",
                        },
                        "documentation_publishing": {
                            "allowed": False,
                            "reason": "Documentation publishing feature flag is disabled",
                        },
                    },
                    "allowlists": {
                        "github_repositories": ["AIRP-client/*"],
                        "kubernetes_namespaces": [],
                        "client_github_org": "AIRP-client",
                    },
                    "mcp_read_settings": {
                        "read_only_evidence_enabled": False,
                        "kubernetes_transport": "disabled",
                        "kubernetes_endpoint_configured": False,
                        "kubernetes_read_timeout_seconds": 20.0,
                        "github_transport": "disabled",
                        "github_endpoint_configured": False,
                        "github_read_timeout_seconds": 20.0,
                        "dockerhub_base_url": "https://hub.docker.com/v2",
                        "dockerhub_read_timeout_seconds": 20.0,
                        "retry_attempts": 2,
                        "retry_min_backoff_seconds": 0.1,
                        "retry_max_backoff_seconds": 1.0,
                    },
                    "secrets_redacted": True,
                }
            }
        },
    }
}


@router.get("/policy", response_model=EffectivePolicyRead, responses=POLICY_RESPONSES)
async def get_policy(
    _: AdminPrincipal,
    settings: Annotated[Settings, Depends(get_settings)],
) -> EffectivePolicyRead:
    return build_effective_policy(settings)

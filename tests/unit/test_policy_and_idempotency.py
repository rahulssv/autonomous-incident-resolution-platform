from __future__ import annotations

from backend.src.airp.core.config import Settings
from backend.src.airp.core.idempotency import artifact_idempotency_marker, build_idempotency_key
from backend.src.airp.core.policy import ExternalActionPolicy
from backend.src.airp.services.policy_service import build_effective_policy


def test_artifact_idempotency_key_is_stable_and_marker_safe() -> None:
    first = build_idempotency_key(
        scope="github",
        incident_id="inc-1",
        action="create_issue",
        target="https://github.com/AIRP-client/checkout-api",
        payload={"title": "Checkout latency"},
    )
    second = build_idempotency_key(
        scope="github",
        incident_id="inc-1",
        action="create_issue",
        target="https://github.com/AIRP-client/checkout-api",
        payload={"title": "Checkout latency"},
    )

    assert first == second
    assert first.startswith("airp:v1:github:create_issue:")
    assert artifact_idempotency_marker(first) == f"<!-- airp-idempotency-key:{first} -->"


def test_external_write_policies_default_disabled() -> None:
    policy = ExternalActionPolicy(Settings())

    assert policy.github_issue_creation().allowed is False
    assert policy.slack_notification().allowed is False
    assert policy.remediation_pr_creation().allowed is False


def test_external_write_policies_can_be_enabled_explicitly() -> None:
    policy = ExternalActionPolicy(
        Settings(
            github_issue_creation_enabled=True,
            slack_notifications_enabled=True,
            remediation_pr_creation_enabled=True,
        )
    )

    assert policy.github_issue_creation().allowed is True
    assert policy.slack_notification().allowed is True
    assert policy.remediation_pr_creation().allowed is True


def test_effective_policy_redacts_secrets_and_preserves_disabled_defaults() -> None:
    settings = Settings(
        gateway_base_url="https://gateway.example.test",
        gateway_api_key="super-secret-gateway-key",
        kafka_password="super-secret-event-hubs-key",
        kubernetes_mcp_url="https://kubernetes-mcp.example.test",
        github_mcp_url="https://github-mcp.example.test",
        kubernetes_mcp_namespace_allowlist=["shopfast"],
        github_mcp_repository_allowlist=["AIRP-client/*"],
    )

    policy = build_effective_policy(settings)
    payload = policy.model_dump_json()

    assert policy.secrets_redacted is True
    assert policy.external_actions.github_issue_creation.allowed is False
    assert policy.external_actions.slack_notification.allowed is False
    assert policy.external_actions.remediation_pr_creation.allowed is False
    assert policy.external_actions.documentation_publishing.allowed is False
    assert policy.mcp_read_settings.kubernetes_endpoint_configured is True
    assert policy.mcp_read_settings.github_endpoint_configured is True
    assert "super-secret" not in payload
    assert "gateway_api_key" not in payload
    assert "kafka_password" not in payload

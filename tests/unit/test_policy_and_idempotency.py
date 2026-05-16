from __future__ import annotations

from airp.core.config import Settings
from airp.core.idempotency import artifact_idempotency_marker, build_idempotency_key
from airp.core.policy import ExternalActionPolicy


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

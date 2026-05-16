from __future__ import annotations

import pytest

from airp.agents.evidence import RCAEvidenceCollector
from airp.api.routes.health import build_readiness_response, readiness
from airp.core.allowlists import (
    is_github_repository_allowed,
    is_namespace_allowed,
    normalize_github_repository,
)
from airp.core.config import Settings
from airp.core.readiness import ProbeResult
from airp.integrations.mcp_retry import read_with_retries
from airp.workflows.activities import _tool_call_event_type


def test_namespace_allowlist_supports_exact_and_wildcard_patterns() -> None:
    assert is_namespace_allowed("shopfast", ["shopfast"])
    assert is_namespace_allowed("shopfast-prod", ["shopfast-*"])
    assert not is_namespace_allowed("payments", ["shopfast", "catalog"])


def test_github_repository_allowlist_normalizes_urls_and_org_patterns() -> None:
    assert normalize_github_repository(
        "https://github.com/AIRP-client/checkout-api.git"
    ) == "AIRP-client/checkout-api"
    assert is_github_repository_allowed(
        "git@github.com:AIRP-client/checkout-api.git",
        ["AIRP-client/*"],
    )
    assert is_github_repository_allowed(
        "https://github.com/AIRP-client/checkout-api",
        ["https://github.com/orgs/AIRP-client"],
    )
    assert not is_github_repository_allowed(
        "https://github.com/OtherOrg/checkout-api",
        ["AIRP-client/*"],
    )


def test_settings_accept_blank_mcp_urls_from_helm_values() -> None:
    settings = Settings(kubernetes_mcp_url="", github_mcp_url="")

    assert settings.kubernetes_mcp_url is None
    assert settings.github_mcp_url is None


@pytest.mark.asyncio
async def test_read_with_retries_retries_transient_timeout() -> None:
    calls = 0
    sleeps: list[float] = []

    async def flaky_read() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("first call timed out")
        return "ok"

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    assert await read_with_retries(flaky_read, attempts=2, sleep=record_sleep) == "ok"
    assert calls == 2
    assert sleeps == [0.1]


@pytest.mark.asyncio
async def test_evidence_collector_blocks_disallowed_namespace() -> None:
    class KubernetesClient:
        async def collect_evidence(self, **_: object) -> object:
            raise AssertionError("disallowed namespace should not reach Kubernetes MCP")

    collector = RCAEvidenceCollector(
        kubernetes_client=KubernetesClient(),
        allowed_namespaces=["payments"],
    )

    evidence = await collector.collect(
        {
            "service_context": {"namespace": "shopfast"},
            "workload_context": {"namespace": "shopfast"},
        }
    )

    call = next(item for item in evidence.tool_calls if item.tool_server == "kubernetes_mcp")
    assert call.status == "forbidden"
    assert evidence.kubernetes == {}


@pytest.mark.asyncio
async def test_evidence_collector_blocks_disallowed_repository() -> None:
    class GitHubClient:
        async def collect_evidence(self, **_: object) -> object:
            raise AssertionError("disallowed repository should not reach GitHub MCP")

    collector = RCAEvidenceCollector(
        github_client=GitHubClient(),
        allowed_repositories=["AIRP-client/catalog-api"],
    )

    evidence = await collector.collect(
        {
            "correlation_result": {
                "repository_url": "https://github.com/AIRP-client/checkout-api"
            }
        }
    )

    call = next(item for item in evidence.tool_calls if item.tool_server == "github_mcp")
    assert call.status == "forbidden"
    assert evidence.github == {}


@pytest.mark.asyncio
async def test_evidence_collector_records_timeout_status() -> None:
    class KubernetesClient:
        async def collect_evidence(self, **_: object) -> object:
            raise TimeoutError("Kubernetes MCP read timed out")

    collector = RCAEvidenceCollector(
        kubernetes_client=KubernetesClient(),
        retry_attempts=1,
    )

    evidence = await collector.collect(
        {
            "service_context": {"namespace": "shopfast"},
            "workload_context": {"namespace": "shopfast"},
        }
    )

    call = next(item for item in evidence.tool_calls if item.tool_server == "kubernetes_mcp")
    assert call.status == "timeout"


def test_tool_call_event_type_tracks_visible_read_failures() -> None:
    assert (
        _tool_call_event_type({"status": "unavailable"})
        == "rca.evidence_collection.unavailable"
    )
    assert _tool_call_event_type({"status": "forbidden"}) == "rca.evidence_collection.forbidden"
    assert _tool_call_event_type({"status": "timeout"}) == "rca.evidence_collection.timeout"
    assert _tool_call_event_type({"status": "partial"}) == "rca.evidence_collection.partial"
    assert _tool_call_event_type({"status": "completed"}) is None


@pytest.mark.asyncio
async def test_readiness_reports_mcp_configuration_status() -> None:
    response = await readiness(
        Settings(
            agent_read_only_evidence_enabled=True,
            kubernetes_mcp_transport="mcp",
            kubernetes_mcp_url="https://kubernetes-mcp.example.test",
            kubernetes_mcp_namespace_allowlist=["shopfast"],
            github_mcp_transport="mcp",
            github_mcp_url="https://github-mcp.example.test",
            github_mcp_repository_allowlist=["AIRP-client/*"],
        )
    )

    assert response.status == "ready"
    assert response.dependencies["kubernetes_mcp"].status == "ready"
    assert response.dependencies["github_mcp"].status == "ready"
    assert response.dependencies["dockerhub"].status == "ready"


@pytest.mark.asyncio
async def test_active_readiness_degrades_when_required_probe_fails() -> None:
    async def unavailable_postgres() -> ProbeResult:
        return ProbeResult(False, "connection refused")

    response = await build_readiness_response(
        Settings(),
        active_checks=True,
        probes={"postgres": unavailable_postgres},
    )

    assert response.status == "degraded"
    assert response.dependencies["postgres"].status == "unavailable"
    assert response.dependencies["postgres"].details["reachability"] == "unreachable"
    assert "password" not in response.dependencies["postgres"].details


@pytest.mark.asyncio
async def test_active_readiness_marks_reachable_probe_ready() -> None:
    async def reachable_postgres() -> ProbeResult:
        return ProbeResult(True)

    response = await build_readiness_response(
        Settings(),
        active_checks=True,
        probes={"postgres": reachable_postgres},
    )

    assert response.dependencies["postgres"].status == "ready"
    assert response.dependencies["postgres"].details["check_mode"] == "active"
    assert response.dependencies["postgres"].details["reachability"] == "reachable"


@pytest.mark.asyncio
async def test_evidence_collector_records_partial_status() -> None:
    class PartialKubernetesClient:
        async def collect_evidence(self, **_: object) -> object:
            from airp.integrations.kubernetes_mcp.client import (
                KubernetesEvidenceBundle,
                KubernetesPodEvidence,
            )

            return KubernetesEvidenceBundle(
                namespace="shopfast",
                pods=[KubernetesPodEvidence(namespace="shopfast", name="checkout-api-abc123")],
                collection_errors=["get_pod_logs: HTTPStatusError"],
            )

    collector = RCAEvidenceCollector(
        kubernetes_client=PartialKubernetesClient(),
        retry_attempts=1,
    )

    evidence = await collector.collect(
        {
            "service_context": {"namespace": "shopfast"},
            "workload_context": {"namespace": "shopfast"},
        }
    )

    call = next(item for item in evidence.tool_calls if item.tool_server == "kubernetes_mcp")
    assert call.status == "partial"
    assert call.error == "get_pod_logs: HTTPStatusError"

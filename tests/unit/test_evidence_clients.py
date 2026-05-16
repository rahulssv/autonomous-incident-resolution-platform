from __future__ import annotations

import httpx
import pytest

from airp.integrations.dockerhub.client import (
    DockerHubClient,
    DockerHubImageEvidence,
    parse_image_reference,
)
from airp.integrations.github_mcp.client import (
    GitHubChangedFileEvidence,
    GitHubCommitEvidence,
    GitHubEvidenceBundle,
    GitHubMCPClient,
    GitHubPullRequestEvidence,
)
from airp.integrations.kubernetes_mcp.client import (
    KubernetesDeploymentEvidence,
    KubernetesEvidenceBundle,
    KubernetesLogEvidence,
    KubernetesMCPClient,
    KubernetesPodEvidence,
    KubernetesReplicaSetEvidence,
    KubernetesRolloutEvidence,
)


@pytest.mark.asyncio
async def test_kubernetes_mcp_fixture_collects_runtime_evidence() -> None:
    client = KubernetesMCPClient(
        fixture=KubernetesEvidenceBundle(
            namespace="shopfast",
            pod_name="checkout-api-abc123",
            deployment="checkout-api",
            pods=[
                KubernetesPodEvidence(
                    namespace="shopfast",
                    name="checkout-api-abc123",
                    ready=False,
                    restart_count=4,
                )
            ],
            logs=[
                KubernetesLogEvidence(
                    namespace="shopfast",
                    pod_name="checkout-api-abc123",
                    container="api",
                    lines=["line-1", "line-2"],
                )
            ],
            deployment_state=KubernetesDeploymentEvidence(
                namespace="shopfast",
                name="checkout-api",
                desired_replicas=2,
                ready_replicas=1,
            ),
            rollout_status=KubernetesRolloutEvidence(
                namespace="shopfast",
                deployment="checkout-api",
                status="degraded",
            ),
            replica_sets=[
                KubernetesReplicaSetEvidence(
                    namespace="shopfast",
                    name="checkout-api-7789",
                    deployment="checkout-api",
                    ready_replicas=1,
                )
            ],
        )
    )

    evidence = await client.collect_evidence(
        namespace="shopfast",
        pod_name="checkout-api-abc123",
        deployment="checkout-api",
        container="api",
    )

    assert evidence.pods[0].restart_count == 4
    assert evidence.logs[0].lines == ["line-1", "line-2"]
    assert evidence.deployment_state is not None
    assert evidence.rollout_status is not None
    assert evidence.replica_sets[0].name == "checkout-api-7789"


@pytest.mark.asyncio
async def test_github_mcp_fixture_collects_repository_evidence() -> None:
    client = GitHubMCPClient(
        fixture=GitHubEvidenceBundle(
            repository_url="https://github.com/AIRP-client/checkout-api",
            default_branch="main",
            commits=[
                GitHubCommitEvidence(
                    sha="abc123",
                    message="Change retry policy",
                    changed_files=[GitHubChangedFileEvidence(path="src/retry.py")],
                )
            ],
            merged_prs=[
                GitHubPullRequestEvidence(
                    number=42,
                    title="Deploy retry policy",
                    changed_files=[GitHubChangedFileEvidence(path="helm/values.yaml")],
                )
            ],
        )
    )

    evidence = await client.collect_evidence(
        repository_url="https://github.com/AIRP-client/checkout-api"
    )

    assert evidence.default_branch == "main"
    assert evidence.commits[0].sha == "abc123"
    assert {item.path for item in evidence.changed_files} == {
        "src/retry.py",
        "helm/values.yaml",
    }


@pytest.mark.asyncio
async def test_dockerhub_fixture_resolves_image_metadata() -> None:
    client = DockerHubClient(
        fixture={
            "airpclient/checkout-api:v1": DockerHubImageEvidence(
                image="docker.io/airpclient/checkout-api:v1",
                repository="airpclient/checkout-api",
                tag="v1",
                digest="sha256:abc",
            )
        }
    )

    evidence = await client.get_image_evidence("docker.io/airpclient/checkout-api:v1")

    assert evidence.repository == "airpclient/checkout-api"
    assert evidence.tag == "v1"
    assert evidence.digest == "sha256:abc"


@pytest.mark.asyncio
async def test_dockerhub_live_tag_lookup_uses_http_transport_and_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/repositories/airpclient/checkout-api/tags/v1"
        return httpx.Response(
            200,
            json={
                "name": "v1",
                "digest": "sha256:live",
                "last_updated": "2026-05-16T10:00:00Z",
                "images": [{"source_commit_sha": "abc123"}],
            },
        )

    client = DockerHubClient(
        base_url="https://hub.docker.com/v2",
        timeout_seconds=3.0,
        transport=httpx.MockTransport(handler),
    )

    evidence = await client.get_image_evidence("docker.io/airpclient/checkout-api:v1")

    assert evidence.repository == "airpclient/checkout-api"
    assert evidence.tag == "v1"
    assert evidence.digest == "sha256:live"
    assert evidence.source_commit_sha == "abc123"
    assert evidence.last_updated == "2026-05-16T10:00:00Z"


def test_parse_image_reference_handles_registry_tag_and_digest() -> None:
    reference = parse_image_reference(
        "docker.io/airpclient/checkout-api:v1@sha256:abc"
    )

    assert reference.repository == "airpclient/checkout-api"
    assert reference.tag == "v1"
    assert reference.digest == "sha256:abc"

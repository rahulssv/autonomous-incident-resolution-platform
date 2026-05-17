from __future__ import annotations

import json

import httpx
import pytest

from backend.src.airp.integrations.dockerhub.client import (
    DockerHubClient,
    DockerHubImageEvidence,
    parse_image_reference,
)
from backend.src.airp.integrations.github_mcp.client import (
    GitHubChangedFileEvidence,
    GitHubCommitEvidence,
    GitHubEvidenceBundle,
    GitHubMCPClient,
    GitHubPullRequestEvidence,
)
from backend.src.airp.integrations.kubernetes_mcp.client import (
    KubernetesDeploymentEvidence,
    KubernetesEvidenceBundle,
    KubernetesLogEvidence,
    KubernetesMCPClient,
    KubernetesPodEvidence,
    KubernetesReplicaSetEvidence,
    KubernetesRolloutEvidence,
)
from backend.src.airp.integrations.mcp_http import MCPToolResponseError


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


@pytest.mark.asyncio
async def test_kubernetes_mcp_http_transport_collects_live_evidence() -> None:
    seen_tools: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mcp/tools/call"
        body = json.loads(request.content.decode())
        tool = body["tool"]
        seen_tools.append(tool)
        arguments = body["arguments"]
        assert arguments["namespace"] == "shopfast"

        responses = {
            "kubernetes.list_pods": {
                "pods": [
                    {
                        "namespace": "shopfast",
                        "name": "checkout-api-abc123",
                        "restart_count": 2,
                        "raw": {"source_link": "https://k8s.example/pods/checkout-api-abc123"},
                    }
                ]
            },
            "kubernetes.get_pod": {
                "pod": {
                    "namespace": "shopfast",
                    "name": "checkout-api-abc123",
                    "restart_count": 2,
                }
            },
            "kubernetes.get_pod_logs": {"lines": ["old", "current"]},
            "kubernetes.list_events": {
                "events": [
                    {
                        "namespace": "shopfast",
                        "reason": "BackOff",
                        "message": "Back-off restarting container",
                    }
                ]
            },
            "kubernetes.get_deployment": {
                "deployment": {
                    "namespace": "shopfast",
                    "name": "checkout-api",
                    "ready_replicas": 1,
                }
            },
            "kubernetes.get_rollout_status": {
                "rollout_status": {
                    "namespace": "shopfast",
                    "deployment": "checkout-api",
                    "status": "degraded",
                }
            },
            "kubernetes.list_replicasets": {
                "replica_sets": [
                    {
                        "namespace": "shopfast",
                        "name": "checkout-api-7789",
                        "deployment": "checkout-api",
                    }
                ]
            },
        }
        return httpx.Response(200, json={"result": responses[tool]})

    client = KubernetesMCPClient(
        transport="mcp",
        endpoint_url="https://kubernetes-mcp.example/mcp",
        http_transport=httpx.MockTransport(handler),
    )

    pod = await client.get_pod("shopfast", "checkout-api-abc123")
    evidence = await client.collect_evidence(
        namespace="shopfast",
        pod_name="checkout-api-abc123",
        deployment="checkout-api",
        container="api",
    )

    assert pod is not None
    assert pod["name"] == "checkout-api-abc123"
    assert evidence.pods[0].restart_count == 2
    assert evidence.logs[0].lines == ["old", "current"]
    assert evidence.events[0].reason == "BackOff"
    assert evidence.deployment_state is not None
    assert evidence.rollout_status is not None
    assert evidence.replica_sets[0].name == "checkout-api-7789"
    assert evidence.source_links == ["https://k8s.example/pods/checkout-api-abc123"]
    assert seen_tools == [
        "kubernetes.get_pod",
        "kubernetes.list_pods",
        "kubernetes.get_pod_logs",
        "kubernetes.list_events",
        "kubernetes.get_deployment",
        "kubernetes.get_rollout_status",
        "kubernetes.list_replicasets",
    ]


@pytest.mark.asyncio
async def test_kubernetes_mcp_collects_partial_evidence_when_one_tool_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        tool = body["tool"]
        if tool == "kubernetes.get_pod_logs":
            return httpx.Response(500, json={"error": "logs temporarily unavailable"})
        responses = {
            "kubernetes.list_pods": {
                "pods": [{"namespace": "shopfast", "name": "checkout-api-abc123"}],
                "warnings": ["pod data may be delayed"],
            },
            "kubernetes.list_events": {"events": []},
        }
        return httpx.Response(200, json={"result": responses[tool]})

    client = KubernetesMCPClient(
        transport="mcp",
        endpoint_url="https://kubernetes-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    evidence = await client.collect_evidence(
        namespace="shopfast",
        pod_name="checkout-api-abc123",
    )

    assert evidence.pods[0].name == "checkout-api-abc123"
    assert evidence.logs == []
    assert "pod data may be delayed" in evidence.collection_errors
    assert "get_pod_logs: HTTPStatusError" in evidence.collection_errors


@pytest.mark.asyncio
async def test_github_mcp_http_transport_collects_live_repository_evidence() -> None:
    seen_tools: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        tool = body["tool"]
        seen_tools.append(tool)
        repository_url = body["arguments"].get("repository_url")
        if repository_url:
            assert repository_url == "https://github.com/AIRP-client/checkout-api"

        responses = {
            "github.get_repository": {
                "repository": {
                    "name": "checkout-api",
                    "owner": "AIRP-client",
                    "html_url": "https://github.com/AIRP-client/checkout-api",
                    "default_branch": "main",
                }
            },
            "github.lookup_commits": {
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "Change retry policy",
                        "raw": {"html_url": "https://github.com/AIRP-client/checkout-api/abc123"},
                    }
                ]
            },
            "github.lookup_commit": {"commit": {"sha": "abc123", "message": "Change retry policy"}},
            "github.lookup_merged_prs": {
                "merged_prs": [
                    {"number": 42, "title": "Deploy retry policy", "merge_commit_sha": "abc123"}
                ]
            },
            "github.lookup_changed_files": {
                "changed_files": [{"path": "src/retry.py", "status": "modified"}]
            },
            "github.lookup_releases": {"releases": [{"tag_name": "v1"}]},
            "github.lookup_prior_issues": {"issues": [{"number": 7, "title": "Prior timeout"}]},
            "github.lookup_branches": {"branches": [{"name": "main"}]},
        }
        return httpx.Response(200, json={"content": [{"type": "json", "json": responses[tool]}]})

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    evidence = await client.collect_evidence(
        repository_url="https://github.com/AIRP-client/checkout-api"
    )
    commit = await client.lookup_commit(
        "https://github.com/AIRP-client/checkout-api",
        "abc123",
    )
    branches = await client.lookup_branches("https://github.com/AIRP-client/checkout-api")

    assert evidence.default_branch == "main"
    assert evidence.commits[0].sha == "abc123"
    assert commit is not None
    assert commit["sha"] == "abc123"
    assert evidence.merged_prs[0].number == 42
    assert evidence.changed_files[0].path == "src/retry.py"
    assert evidence.releases[0].tag_name == "v1"
    assert evidence.prior_issues[0].number == 7
    assert evidence.source_links == ["https://github.com/AIRP-client/checkout-api/abc123"]
    assert branches == [{"name": "main"}]
    assert seen_tools == [
        "github.get_repository",
        "github.lookup_commits",
        "github.lookup_merged_prs",
        "github.lookup_changed_files",
        "github.lookup_releases",
        "github.lookup_prior_issues",
        "github.lookup_commit",
        "github.lookup_branches",
    ]


@pytest.mark.asyncio
async def test_github_mcp_creates_issue_through_mcp_tool() -> None:
    seen_arguments: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["tool"] == "github.create_issue"
        seen_arguments.update(body["arguments"])
        return httpx.Response(
            200,
            json={
                "result": {
                    "issue": {
                        "number": 123,
                        "title": body["arguments"]["title"],
                        "url": "https://github.com/AIRP-client/checkout-api/issues/123",
                        "labels": body["arguments"]["labels"],
                    }
                }
            },
        )

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    issue = await client.create_issue(
        "https://github.com/AIRP-client/checkout-api",
        "AIRP incident",
        "RCA body",
        labels=["airp", "incident"],
    )

    assert issue["number"] == 123
    assert issue["url"].endswith("/issues/123")
    assert seen_arguments["repository_url"] == "https://github.com/AIRP-client/checkout-api"
    assert seen_arguments["labels"] == ["airp", "incident"]


@pytest.mark.asyncio
async def test_github_mcp_creates_pull_request_through_mcp_tool() -> None:
    seen_arguments: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["tool"] == "github.create_pull_request"
        seen_arguments.update(body["arguments"])
        return httpx.Response(
            200,
            json={
                "result": {
                    "pull_request": {
                        "number": 456,
                        "title": body["arguments"]["title"],
                        "url": "https://github.com/AIRP-client/checkout-api/pull/456",
                        "head": body["arguments"]["branch"],
                        "base": body["arguments"]["base"],
                        "assignees": body["arguments"]["assignees"],
                    }
                }
            },
        )

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    pull_request = await client.create_pull_request(
        "https://github.com/AIRP-client/checkout-api",
        {
            "title": "AIRP remediation",
            "body": "RCA fix",
            "branch": "airp/remediation/inc-123",
            "base": "main",
            "files": [{"path": ".airp/remediations/inc-123.md", "content": "body"}],
            "assignees": ["rahulssv"],
        },
    )

    assert pull_request["number"] == 456
    assert pull_request["url"].endswith("/pull/456")
    assert seen_arguments["repository_url"] == "https://github.com/AIRP-client/checkout-api"
    assert seen_arguments["assignees"] == ["rahulssv"]


@pytest.mark.asyncio
async def test_github_mcp_looks_up_file_commits_through_mcp_tool() -> None:
    seen_arguments: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["tool"] == "github.lookup_file_commits"
        seen_arguments.update(body["arguments"])
        return httpx.Response(
            200,
            json={
                "result": {
                    "commits": [
                        {
                            "sha": "abc123",
                            "author": "rahulssv",
                            "raw": {"author_login": "rahulssv"},
                        }
                    ]
                }
            },
        )

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    commits = await client.lookup_file_commits(
        "https://github.com/AIRP-client/checkout-api",
        path="src/checkout/api.py",
        limit=1,
    )

    assert commits[0]["author"] == "rahulssv"
    assert seen_arguments["path"] == "src/checkout/api.py"
    assert seen_arguments["limit"] == 1


@pytest.mark.asyncio
async def test_github_mcp_finds_issue_by_idempotency_marker_in_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["tool"] == "github.lookup_prior_issues"
        return httpx.Response(
            200,
            json={
                "result": {
                    "issues": [
                        {
                            "number": 99,
                            "title": "AIRP incident",
                            "body": "created by AIRP-INCIDENT-ID-inc-123",
                            "url": "https://github.com/AIRP-client/checkout-api/issues/99",
                        }
                    ]
                }
            },
        )

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    issue = await client.lookup_issue_by_idempotency_marker(
        "https://github.com/AIRP-client/checkout-api",
        "AIRP-INCIDENT-ID-inc-123",
    )

    assert issue is not None
    assert issue["number"] == 99


@pytest.mark.asyncio
async def test_github_mcp_collects_partial_evidence_when_one_tool_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        tool = body["tool"]
        if tool == "github.lookup_changed_files":
            return httpx.Response(500, json={"error": "files temporarily unavailable"})
        responses = {
            "github.get_repository": {
                "repository": {
                    "name": "checkout-api",
                    "owner": "AIRP-client",
                    "default_branch": "main",
                }
            },
            "github.lookup_commits": {
                "commits": [{"sha": "abc123", "message": "Change retry policy"}],
                "warnings": ["commit list truncated"],
            },
            "github.lookup_merged_prs": {"merged_prs": []},
            "github.lookup_releases": {"releases": []},
            "github.lookup_prior_issues": {"issues": []},
        }
        return httpx.Response(200, json={"result": responses[tool]})

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    evidence = await client.collect_evidence(
        repository_url="https://github.com/AIRP-client/checkout-api"
    )

    assert evidence.default_branch == "main"
    assert evidence.commits[0].sha == "abc123"
    assert evidence.changed_files == []
    assert "commit list truncated" in evidence.collection_errors
    assert "lookup_changed_files: HTTPStatusError" in evidence.collection_errors


@pytest.mark.asyncio
async def test_mcp_http_transport_propagates_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = KubernetesMCPClient(
        transport="mcp",
        endpoint_url="https://kubernetes-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.ReadTimeout):
        await client.list_pods("shopfast")


@pytest.mark.parametrize("status_code", [429, 500])
@pytest.mark.asyncio
async def test_mcp_http_transport_raises_for_retryable_http_statuses(
    status_code: int,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "try later"})

    client = GitHubMCPClient(
        transport="mcp",
        endpoint_url="https://github-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.lookup_commits("https://github.com/AIRP-client/checkout-api")


@pytest.mark.asyncio
async def test_mcp_http_transport_rejects_malformed_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"unexpected": []}})

    client = KubernetesMCPClient(
        transport="mcp",
        endpoint_url="https://kubernetes-mcp.example",
        http_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MCPToolResponseError):
        await client.list_pods("shopfast")

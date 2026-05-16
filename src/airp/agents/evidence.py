from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from airp.core.allowlists import is_github_repository_allowed, is_namespace_allowed
from airp.integrations.genaihub.redaction import redact_payload
from airp.integrations.mcp_retry import is_timeout_error, read_with_retries

ToolCallStatus = Literal[
    "completed",
    "partial",
    "failed",
    "skipped",
    "unavailable",
    "forbidden",
    "timeout",
]


class PlannedToolCall(BaseModel):
    tool_server: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus
    latency_ms: int | None = None
    result_summary: str | None = None
    error: str | None = None


class CollectedRCAEvidence(BaseModel):
    kubernetes: dict[str, Any] = Field(default_factory=dict)
    github: dict[str, Any] = Field(default_factory=dict)
    dockerhub: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[PlannedToolCall] = Field(default_factory=list)


class RCAEvidenceCollector:
    """Read-only RCA evidence boundary for MCP and DockerHub adapters.

    This collector records every intended tool call and never performs repository
    mutations. It is safe to run with fixture-backed clients in tests and with
    future live read-only transports in production.
    """

    def __init__(
        self,
        *,
        kubernetes_client: Any | None = None,
        github_client: Any | None = None,
        dockerhub_client: Any | None = None,
        allowed_namespaces: Sequence[str] | None = None,
        allowed_repositories: Sequence[str] | None = None,
        retry_attempts: int = 2,
        retry_min_backoff_seconds: float = 0.1,
        retry_max_backoff_seconds: float = 1.0,
    ) -> None:
        self.kubernetes_client = kubernetes_client
        self.github_client = github_client
        self.dockerhub_client = dockerhub_client
        self.allowed_namespaces = tuple(allowed_namespaces or ())
        self.allowed_repositories = tuple(allowed_repositories or ())
        self.retry_attempts = retry_attempts
        self.retry_min_backoff_seconds = retry_min_backoff_seconds
        self.retry_max_backoff_seconds = retry_max_backoff_seconds

    async def collect(self, state: dict[str, Any]) -> CollectedRCAEvidence:
        evidence = CollectedRCAEvidence()
        service_context = state.get("service_context") or {}
        workload_context = state.get("workload_context") or {}
        correlation_result = state.get("correlation_result") or {}

        namespace = workload_context.get("namespace") or service_context.get("namespace")
        pod_name = workload_context.get("pod_name")
        deployment = workload_context.get("deployment") or service_context.get("deployment")
        container = workload_context.get("container_name")
        repository_url = (
            service_context.get("repository_url") or correlation_result.get("repository_url")
        )
        image = (
            workload_context.get("image")
            or service_context.get("docker_image")
            or correlation_result.get("docker_image")
        )

        await self._collect_kubernetes(
            evidence,
            namespace=namespace,
            pod_name=pod_name,
            deployment=deployment,
            container=container,
        )
        await self._collect_github(evidence, repository_url=repository_url)
        await self._collect_dockerhub(evidence, image=image)
        return evidence

    async def _collect_kubernetes(
        self,
        evidence: CollectedRCAEvidence,
        *,
        namespace: str | None,
        pod_name: str | None,
        deployment: str | None,
        container: str | None,
    ) -> None:
        parameters = {
            "namespace": namespace,
            "pod_name": pod_name,
            "deployment": deployment,
            "container": container,
        }
        if self.kubernetes_client is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="kubernetes_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="Kubernetes MCP client is not configured",
                )
            )
            return
        if namespace is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="kubernetes_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="namespace is unavailable",
                )
            )
            return
        if not is_namespace_allowed(namespace, self.allowed_namespaces):
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="kubernetes_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="forbidden",
                    error=(
                        f"namespace '{namespace}' is outside the configured Kubernetes "
                        "MCP allowlist"
                    ),
                )
            )
            return

        started = perf_counter()
        try:
            bundle = await read_with_retries(
                lambda: self.kubernetes_client.collect_evidence(
                    namespace=namespace,
                    pod_name=pod_name,
                    deployment=deployment,
                    container=container,
                ),
                attempts=self.retry_attempts,
                min_backoff_seconds=self.retry_min_backoff_seconds,
                max_backoff_seconds=self.retry_max_backoff_seconds,
            )
        except NotImplementedError as exc:
            evidence.tool_calls.append(
                self._tool_call(
                    "kubernetes_mcp",
                    "collect_evidence",
                    parameters,
                    "unavailable",
                    started,
                    error=str(exc),
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 - boundary must never crash RCA graph
            status: ToolCallStatus = "timeout" if is_timeout_error(exc) else "failed"
            evidence.tool_calls.append(
                self._tool_call(
                    "kubernetes_mcp",
                    "collect_evidence",
                    parameters,
                    status,
                    started,
                    error=str(exc),
                )
            )
            return

        data = redact_payload(bundle.model_dump(mode="json", exclude_none=True))
        evidence.kubernetes = data
        status = _collection_status(
            data,
            evidence_keys=(
                "pods",
                "logs",
                "events",
                "deployment_state",
                "rollout_status",
                "replica_sets",
            ),
        )
        errors = _collection_errors(data)
        evidence.tool_calls.append(
            self._tool_call(
                "kubernetes_mcp",
                "collect_evidence",
                parameters,
                status,
                started,
                result_summary=(
                    f"{len(data.get('pods', []))} pods, "
                    f"{len(data.get('logs', []))} log windows, "
                    f"{len(data.get('events', []))} events"
                ),
                error="; ".join(errors) if errors else None,
            )
        )

    async def _collect_github(
        self,
        evidence: CollectedRCAEvidence,
        *,
        repository_url: str | None,
    ) -> None:
        parameters = {"repository_url": repository_url}
        if self.github_client is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="github_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="GitHub MCP client is not configured",
                )
            )
            return
        if repository_url is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="github_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="repository_url is unavailable",
                )
            )
            return
        if not is_github_repository_allowed(repository_url, self.allowed_repositories):
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="github_mcp",
                    tool_name="collect_evidence",
                    parameters=parameters,
                    status="forbidden",
                    error=(
                        f"repository '{repository_url}' is outside the configured GitHub "
                        "MCP allowlist"
                    ),
                )
            )
            return

        started = perf_counter()
        try:
            bundle = await read_with_retries(
                lambda: self.github_client.collect_evidence(repository_url=repository_url),
                attempts=self.retry_attempts,
                min_backoff_seconds=self.retry_min_backoff_seconds,
                max_backoff_seconds=self.retry_max_backoff_seconds,
            )
        except NotImplementedError as exc:
            evidence.tool_calls.append(
                self._tool_call(
                    "github_mcp",
                    "collect_evidence",
                    parameters,
                    "unavailable",
                    started,
                    error=str(exc),
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 - boundary must never crash RCA graph
            status: ToolCallStatus = "timeout" if is_timeout_error(exc) else "failed"
            evidence.tool_calls.append(
                self._tool_call(
                    "github_mcp",
                    "collect_evidence",
                    parameters,
                    status,
                    started,
                    error=str(exc),
                )
            )
            return

        data = redact_payload(bundle.model_dump(mode="json", exclude_none=True))
        evidence.github = data
        status = _collection_status(
            data,
            evidence_keys=("commits", "merged_prs", "changed_files", "releases", "prior_issues"),
        )
        errors = _collection_errors(data)
        evidence.tool_calls.append(
            self._tool_call(
                "github_mcp",
                "collect_evidence",
                parameters,
                status,
                started,
                result_summary=(
                    f"{len(data.get('commits', []))} commits, "
                    f"{len(data.get('merged_prs', []))} merged PRs, "
                    f"{len(data.get('prior_issues', []))} prior issues"
                ),
                error="; ".join(errors) if errors else None,
            )
        )

    async def _collect_dockerhub(
        self,
        evidence: CollectedRCAEvidence,
        *,
        image: str | None,
    ) -> None:
        parameters = {"image": image}
        if self.dockerhub_client is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="dockerhub",
                    tool_name="get_image_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="DockerHub client is not configured",
                )
            )
            return
        if image is None:
            evidence.tool_calls.append(
                PlannedToolCall(
                    tool_server="dockerhub",
                    tool_name="get_image_evidence",
                    parameters=parameters,
                    status="skipped",
                    error="image is unavailable",
                )
            )
            return

        started = perf_counter()
        try:
            image_evidence = await read_with_retries(
                lambda: self.dockerhub_client.get_image_evidence(image),
                attempts=self.retry_attempts,
                min_backoff_seconds=self.retry_min_backoff_seconds,
                max_backoff_seconds=self.retry_max_backoff_seconds,
            )
        except NotImplementedError as exc:
            evidence.tool_calls.append(
                self._tool_call(
                    "dockerhub",
                    "get_image_evidence",
                    parameters,
                    "unavailable",
                    started,
                    error=str(exc),
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 - boundary must never crash RCA graph
            status: ToolCallStatus = "timeout" if is_timeout_error(exc) else "failed"
            evidence.tool_calls.append(
                self._tool_call(
                    "dockerhub",
                    "get_image_evidence",
                    parameters,
                    status,
                    started,
                    error=str(exc),
                )
            )
            return

        data = redact_payload(image_evidence.model_dump(mode="json", exclude_none=True))
        evidence.dockerhub = data
        evidence.tool_calls.append(
            self._tool_call(
                "dockerhub",
                "get_image_evidence",
                parameters,
                "completed",
                started,
                result_summary=(
                    f"{data.get('repository')}:{data.get('tag')}"
                    if data.get("tag")
                    else data.get("repository")
                ),
            )
        )

    def _tool_call(
        self,
        tool_server: str,
        tool_name: str,
        parameters: dict[str, Any],
        status: ToolCallStatus,
        started: float,
        *,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> PlannedToolCall:
        return PlannedToolCall(
            tool_server=tool_server,
            tool_name=tool_name,
            parameters=parameters,
            status=status,
            latency_ms=int((perf_counter() - started) * 1000),
            result_summary=result_summary,
            error=error,
        )


def _collection_errors(data: dict[str, Any]) -> list[str]:
    errors = data.get("collection_errors")
    if isinstance(errors, list):
        return [str(error) for error in errors if error]
    if isinstance(errors, str) and errors:
        return [errors]
    return []


def _collection_status(data: dict[str, Any], *, evidence_keys: tuple[str, ...]) -> ToolCallStatus:
    errors = _collection_errors(data)
    if not errors:
        return "completed"
    has_evidence = any(bool(data.get(key)) for key in evidence_keys)
    return "partial" if has_evidence else "failed"

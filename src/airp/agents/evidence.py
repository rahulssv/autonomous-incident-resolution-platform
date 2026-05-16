from __future__ import annotations

from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from airp.integrations.genaihub.redaction import redact_payload

ToolCallStatus = Literal["completed", "failed", "skipped", "unavailable"]


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
    ) -> None:
        self.kubernetes_client = kubernetes_client
        self.github_client = github_client
        self.dockerhub_client = dockerhub_client

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

        started = perf_counter()
        try:
            bundle = await self.kubernetes_client.collect_evidence(
                namespace=namespace,
                pod_name=pod_name,
                deployment=deployment,
                container=container,
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
            evidence.tool_calls.append(
                self._tool_call(
                    "kubernetes_mcp",
                    "collect_evidence",
                    parameters,
                    "failed",
                    started,
                    error=str(exc),
                )
            )
            return

        data = redact_payload(bundle.model_dump(mode="json", exclude_none=True))
        evidence.kubernetes = data
        evidence.tool_calls.append(
            self._tool_call(
                "kubernetes_mcp",
                "collect_evidence",
                parameters,
                "completed",
                started,
                result_summary=(
                    f"{len(data.get('pods', []))} pods, "
                    f"{len(data.get('logs', []))} log windows, "
                    f"{len(data.get('events', []))} events"
                ),
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

        started = perf_counter()
        try:
            bundle = await self.github_client.collect_evidence(repository_url=repository_url)
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
            evidence.tool_calls.append(
                self._tool_call(
                    "github_mcp",
                    "collect_evidence",
                    parameters,
                    "failed",
                    started,
                    error=str(exc),
                )
            )
            return

        data = redact_payload(bundle.model_dump(mode="json", exclude_none=True))
        evidence.github = data
        evidence.tool_calls.append(
            self._tool_call(
                "github_mcp",
                "collect_evidence",
                parameters,
                "completed",
                started,
                result_summary=(
                    f"{len(data.get('commits', []))} commits, "
                    f"{len(data.get('merged_prs', []))} merged PRs, "
                    f"{len(data.get('prior_issues', []))} prior issues"
                ),
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
            image_evidence = await self.dockerhub_client.get_image_evidence(image)
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
            evidence.tool_calls.append(
                self._tool_call(
                    "dockerhub",
                    "get_image_evidence",
                    parameters,
                    "failed",
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

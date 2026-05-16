from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from airp.integrations.mcp_http import call_mcp_tool, item_list, optional_dict


class KubernetesPodEvidence(BaseModel):
    namespace: str
    name: str
    phase: str | None = None
    ready: bool | None = None
    restart_count: int | None = None
    node_name: str | None = None
    pod_ip: str | None = None
    containers: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesLogEvidence(BaseModel):
    namespace: str
    pod_name: str
    container: str | None = None
    lines: list[str] = Field(default_factory=list)
    truncated: bool = False
    time_range: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesEventEvidence(BaseModel):
    namespace: str
    reason: str
    message: str
    type: str | None = None
    involved_object: str | None = None
    timestamp: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesDeploymentEvidence(BaseModel):
    namespace: str
    name: str
    desired_replicas: int | None = None
    ready_replicas: int | None = None
    updated_replicas: int | None = None
    available_replicas: int | None = None
    images: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesRolloutEvidence(BaseModel):
    namespace: str
    deployment: str
    status: str
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesReplicaSetEvidence(BaseModel):
    namespace: str
    name: str
    deployment: str | None = None
    desired_replicas: int | None = None
    ready_replicas: int | None = None
    images: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class KubernetesEvidenceBundle(BaseModel):
    namespace: str | None = None
    pod_name: str | None = None
    deployment: str | None = None
    pods: list[KubernetesPodEvidence] = Field(default_factory=list)
    logs: list[KubernetesLogEvidence] = Field(default_factory=list)
    events: list[KubernetesEventEvidence] = Field(default_factory=list)
    deployment_state: KubernetesDeploymentEvidence | None = None
    rollout_status: KubernetesRolloutEvidence | None = None
    replica_sets: list[KubernetesReplicaSetEvidence] = Field(default_factory=list)
    collection_errors: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)


class KubernetesMCPClient:
    """Thin boundary for future AKS read-only MCP transport implementation."""

    def __init__(
        self,
        fixture: KubernetesEvidenceBundle | dict[str, Any] | None = None,
        *,
        transport: Literal["disabled", "mcp"] = "disabled",
        endpoint_url: str | None = None,
        timeout_seconds: float = 20.0,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.fixture = (
            KubernetesEvidenceBundle.model_validate(fixture) if fixture is not None else None
        )
        self.transport = transport
        self.endpoint_url = endpoint_url.rstrip("/") if endpoint_url else None
        self.timeout_seconds = timeout_seconds
        self.http_transport = http_transport

    async def list_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return [
                pod.model_dump(mode="json")
                for pod in self.fixture.pods
                if namespace is None or pod.namespace == namespace
            ]
        payload = await self._call_tool(
            "kubernetes.list_pods",
            {"namespace": namespace},
        )
        return item_list(payload, "pods", "items")

    async def get_pod(self, namespace: str, pod_name: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            for pod in self.fixture.pods:
                if pod.namespace == namespace and pod.name == pod_name:
                    return pod.model_dump(mode="json")
            return None
        payload = await self._call_tool(
            "kubernetes.get_pod",
            {"namespace": namespace, "pod_name": pod_name},
        )
        return optional_dict(payload, "pod", "item")

    async def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        container: str | None = None,
        *,
        limit_lines: int = 200,
        since_seconds: int | None = None,
        time_range: str | None = None,
    ) -> str:
        if self.fixture is not None:
            for log in self.fixture.logs:
                same_container = container is None or log.container == container
                if log.namespace == namespace and log.pod_name == pod_name and same_container:
                    return "\n".join(log.lines[-limit_lines:])
            return ""
        payload = await self._call_tool(
            "kubernetes.get_pod_logs",
            {
                "namespace": namespace,
                "pod_name": pod_name,
                "container": container,
                "limit_lines": limit_lines,
                "since_seconds": since_seconds,
                "time_range": time_range,
            },
        )
        return _log_text(payload, limit_lines)

    async def list_events(self, namespace: str) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return [
                event.model_dump(mode="json")
                for event in self.fixture.events
                if event.namespace == namespace
            ]
        payload = await self._call_tool(
            "kubernetes.list_events",
            {"namespace": namespace},
        )
        return item_list(payload, "events", "items")

    async def get_events(self, namespace: str) -> list[dict[str, Any]]:
        return await self.list_events(namespace)

    async def get_deployment(self, namespace: str, deployment: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            item = self.fixture.deployment_state
            if item and item.namespace == namespace and item.name == deployment:
                return item.model_dump(mode="json")
            return None
        payload = await self._call_tool(
            "kubernetes.get_deployment",
            {"namespace": namespace, "deployment": deployment},
        )
        return optional_dict(payload, "deployment", "item")

    async def get_rollout_status(
        self, namespace: str, deployment: str
    ) -> dict[str, Any] | None:
        if self.fixture is not None:
            item = self.fixture.rollout_status
            if item and item.namespace == namespace and item.deployment == deployment:
                return item.model_dump(mode="json")
            return None
        payload = await self._call_tool(
            "kubernetes.get_rollout_status",
            {"namespace": namespace, "deployment": deployment},
        )
        return optional_dict(payload, "rollout_status", "item")

    async def list_replicasets(
        self, namespace: str, deployment: str | None = None
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return [
                replica_set.model_dump(mode="json")
                for replica_set in self.fixture.replica_sets
                if replica_set.namespace == namespace
                and (deployment is None or replica_set.deployment == deployment)
            ]
        payload = await self._call_tool(
            "kubernetes.list_replicasets",
            {"namespace": namespace, "deployment": deployment},
        )
        return item_list(payload, "replica_sets", "items")

    async def collect_evidence(
        self,
        *,
        namespace: str | None,
        pod_name: str | None = None,
        deployment: str | None = None,
        container: str | None = None,
    ) -> KubernetesEvidenceBundle:
        if self.fixture is not None:
            return self._fixture_view(
                namespace=namespace,
                pod_name=pod_name,
                deployment=deployment,
                container=container,
            )
        if namespace is None:
            return KubernetesEvidenceBundle(
                namespace=None,
                pod_name=pod_name,
                deployment=deployment,
                collection_errors=["namespace is required for Kubernetes evidence collection"],
            )

        pods = [
            KubernetesPodEvidence.model_validate(pod)
            for pod in await self.list_pods(namespace)
            if pod_name is None or pod.get("name") == pod_name
        ]
        log_lines = []
        if pod_name:
            log_text = await self.get_pod_logs(namespace, pod_name, container)
            log_lines = log_text.splitlines()
        events = [
            KubernetesEventEvidence.model_validate(event)
            for event in await self.list_events(namespace)
        ]
        deployment_state = None
        rollout_status = None
        replica_sets: list[KubernetesReplicaSetEvidence] = []
        if deployment:
            deployment_payload = await self.get_deployment(namespace, deployment)
            rollout_payload = await self.get_rollout_status(namespace, deployment)
            deployment_state = (
                KubernetesDeploymentEvidence.model_validate(deployment_payload)
                if deployment_payload
                else None
            )
            rollout_status = (
                KubernetesRolloutEvidence.model_validate(rollout_payload)
                if rollout_payload
                else None
            )
            replica_sets = [
                KubernetesReplicaSetEvidence.model_validate(item)
                for item in await self.list_replicasets(namespace, deployment)
            ]

        return KubernetesEvidenceBundle(
            namespace=namespace,
            pod_name=pod_name,
            deployment=deployment,
            pods=pods,
            logs=[
                KubernetesLogEvidence(
                    namespace=namespace,
                    pod_name=pod_name,
                    container=container,
                    lines=log_lines,
                )
            ]
            if pod_name and log_lines
            else [],
            events=events,
            deployment_state=deployment_state,
            rollout_status=rollout_status,
            replica_sets=replica_sets,
            source_links=_source_links(
                pods,
                events,
                deployment_state,
                rollout_status,
                replica_sets,
            ),
        )

    def _fixture_view(
        self,
        *,
        namespace: str | None,
        pod_name: str | None,
        deployment: str | None,
        container: str | None,
    ) -> KubernetesEvidenceBundle:
        assert self.fixture is not None
        namespace_filter = namespace or self.fixture.namespace
        pod_filter = pod_name or self.fixture.pod_name
        deployment_filter = deployment or self.fixture.deployment

        return KubernetesEvidenceBundle(
            namespace=namespace_filter,
            pod_name=pod_filter,
            deployment=deployment_filter,
            pods=[
                pod
                for pod in self.fixture.pods
                if (namespace_filter is None or pod.namespace == namespace_filter)
                and (pod_filter is None or pod.name == pod_filter)
            ],
            logs=[
                log
                for log in self.fixture.logs
                if (namespace_filter is None or log.namespace == namespace_filter)
                and (pod_filter is None or log.pod_name == pod_filter)
                and (container is None or log.container == container)
            ],
            events=[
                event
                for event in self.fixture.events
                if namespace_filter is None or event.namespace == namespace_filter
            ],
            deployment_state=self.fixture.deployment_state
            if self._matches_deployment(namespace_filter, deployment_filter)
            else None,
            rollout_status=self.fixture.rollout_status
            if self._matches_rollout(namespace_filter, deployment_filter)
            else None,
            replica_sets=[
                replica_set
                for replica_set in self.fixture.replica_sets
                if (namespace_filter is None or replica_set.namespace == namespace_filter)
                and (
                    deployment_filter is None
                    or replica_set.deployment == deployment_filter
                )
            ],
            collection_errors=list(self.fixture.collection_errors),
            source_links=list(self.fixture.source_links),
        )

    def _matches_deployment(
        self, namespace: str | None, deployment: str | None
    ) -> bool:
        item = self.fixture.deployment_state if self.fixture else None
        return bool(
            item
            and (namespace is None or item.namespace == namespace)
            and (deployment is None or item.name == deployment)
        )

    def _matches_rollout(self, namespace: str | None, deployment: str | None) -> bool:
        item = self.fixture.rollout_status if self.fixture else None
        return bool(
            item
            and (namespace is None or item.namespace == namespace)
            and (deployment is None or item.deployment == deployment)
        )

    def _raise_unavailable(self) -> None:
        if self.transport == "disabled":
            raise NotImplementedError("Kubernetes MCP transport is disabled")
        if not self.endpoint_url:
            raise NotImplementedError("Kubernetes MCP endpoint URL is not configured")
        raise NotImplementedError(
            "Live Kubernetes MCP read transport is configured but not implemented yet"
        )

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self.transport == "disabled":
            raise NotImplementedError("Kubernetes MCP transport is disabled")
        if not self.endpoint_url:
            raise NotImplementedError("Kubernetes MCP endpoint URL is not configured")
        return await call_mcp_tool(
            endpoint_url=self.endpoint_url,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self.timeout_seconds,
            transport=self.http_transport,
        )


def _log_text(payload: Any, limit_lines: int) -> str:
    if isinstance(payload, str):
        return "\n".join(payload.splitlines()[-limit_lines:])
    if isinstance(payload, dict):
        value = payload.get("logs") or payload.get("text")
        if isinstance(value, str):
            return "\n".join(value.splitlines()[-limit_lines:])
        lines = payload.get("lines")
        if isinstance(lines, list):
            return "\n".join(str(line) for line in lines[-limit_lines:])
    raise ValueError("Expected Kubernetes log MCP response to contain logs or lines")


def _source_links(*values: Any) -> list[str]:
    links: list[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                links.extend(_source_links(item))
            continue
        raw = getattr(value, "raw", None)
        if isinstance(raw, dict):
            link = raw.get("source_link") or raw.get("url")
            if isinstance(link, str) and link:
                links.append(link)
    return list(dict.fromkeys(links))

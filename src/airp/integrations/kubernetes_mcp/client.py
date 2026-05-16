from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class KubernetesMCPClient:
    """Thin boundary for future AKS read-only MCP transport implementation."""

    def __init__(self, fixture: KubernetesEvidenceBundle | dict[str, Any] | None = None) -> None:
        self.fixture = (
            KubernetesEvidenceBundle.model_validate(fixture) if fixture is not None else None
        )

    async def list_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return [
                pod.model_dump(mode="json")
                for pod in self.fixture.pods
                if namespace is None or pod.namespace == namespace
            ]
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_pod(self, namespace: str, pod_name: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            for pod in self.fixture.pods:
                if pod.namespace == namespace and pod.name == pod_name:
                    return pod.model_dump(mode="json")
            return None
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        container: str | None = None,
        *,
        limit_lines: int = 200,
    ) -> str:
        if self.fixture is not None:
            for log in self.fixture.logs:
                same_container = container is None or log.container == container
                if log.namespace == namespace and log.pod_name == pod_name and same_container:
                    return "\n".join(log.lines[-limit_lines:])
            return ""
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def list_events(self, namespace: str) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return [
                event.model_dump(mode="json")
                for event in self.fixture.events
                if event.namespace == namespace
            ]
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_events(self, namespace: str) -> list[dict[str, Any]]:
        return await self.list_events(namespace)

    async def get_deployment(self, namespace: str, deployment: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            item = self.fixture.deployment_state
            if item and item.namespace == namespace and item.name == deployment:
                return item.model_dump(mode="json")
            return None
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_rollout_status(
        self, namespace: str, deployment: str
    ) -> dict[str, Any] | None:
        if self.fixture is not None:
            item = self.fixture.rollout_status
            if item and item.namespace == namespace and item.deployment == deployment:
                return item.model_dump(mode="json")
            return None
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

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
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

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

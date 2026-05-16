from typing import Any


class KubernetesMCPClient:
    """Thin boundary for future AKS read-only MCP transport implementation."""

    async def list_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_pod_logs(
        self, namespace: str, pod_name: str, container: str | None = None
    ) -> str:
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

    async def get_events(self, namespace: str) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "Kubernetes MCP transport will be implemented in the workflow phase"
        )

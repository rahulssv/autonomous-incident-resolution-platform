from typing import Annotated

from fastapi import APIRouter, Depends

from airp.core.config import Settings, get_settings
from airp.schemas.common import DependencyReadiness, HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        environment=settings.environment,
        auth_enabled=settings.auth_enabled,
    )


@router.get("/readiness", response_model=ReadinessResponse)
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    dependencies = {
        "kubernetes_mcp": _mcp_dependency(
            required=settings.agent_read_only_evidence_enabled,
            transport=settings.kubernetes_mcp_transport,
            endpoint_url=str(settings.kubernetes_mcp_url)
            if settings.kubernetes_mcp_url
            else None,
            timeout_seconds=settings.kubernetes_mcp_read_timeout_seconds,
            allowlist=settings.kubernetes_mcp_namespace_allowlist,
            allowlist_name="namespace_allowlist",
        ),
        "github_mcp": _mcp_dependency(
            required=settings.agent_read_only_evidence_enabled,
            transport=settings.github_mcp_transport,
            endpoint_url=str(settings.github_mcp_url) if settings.github_mcp_url else None,
            timeout_seconds=settings.github_mcp_read_timeout_seconds,
            allowlist=settings.github_mcp_repository_allowlist,
            allowlist_name="repository_allowlist",
        ),
        "dockerhub": DependencyReadiness(
            status="ready" if settings.agent_read_only_evidence_enabled else "disabled",
            configured=True,
            required=settings.agent_read_only_evidence_enabled,
            details={
                "base_url": str(settings.dockerhub_base_url),
                "timeout_seconds": settings.dockerhub_read_timeout_seconds,
            },
        ),
    }
    status = (
        "ready"
        if all(item.status in {"ready", "disabled", "warning"} for item in dependencies.values())
        else "degraded"
    )
    return ReadinessResponse(
        status=status,
        service=settings.app_name,
        environment=settings.environment,
        dependencies=dependencies,
    )


def _mcp_dependency(
    *,
    required: bool,
    transport: str,
    endpoint_url: str | None,
    timeout_seconds: float,
    allowlist: list[str],
    allowlist_name: str,
) -> DependencyReadiness:
    if not required:
        return DependencyReadiness(
            status="disabled",
            configured=False,
            required=False,
            details={"transport": transport, allowlist_name: allowlist},
        )
    if transport != "mcp":
        return DependencyReadiness(
            status="misconfigured",
            configured=False,
            required=True,
            details={"transport": transport, "reason": "transport must be 'mcp'"},
        )
    if not endpoint_url:
        return DependencyReadiness(
            status="misconfigured",
            configured=False,
            required=True,
            details={"transport": transport, "reason": "endpoint URL is required"},
        )
    return DependencyReadiness(
        status="ready" if allowlist else "warning",
        configured=True,
        required=True,
        details={
            "transport": transport,
            "endpoint_url": endpoint_url,
            "timeout_seconds": timeout_seconds,
            allowlist_name: allowlist,
            "warning": None if allowlist else f"{allowlist_name} is empty",
        },
    )

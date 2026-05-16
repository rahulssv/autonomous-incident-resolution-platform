from typing import Annotated

from fastapi import APIRouter, Depends, Query

from airp.core.config import Settings, get_settings
from airp.core.readiness import (
    DependencyProbeRunner,
    Probe,
    apply_active_probes,
    default_probe_map,
    dependency_status,
)
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
    active: Annotated[bool | None, Query()] = None,
) -> ReadinessResponse:
    active_checks = settings.readiness_active_checks_enabled if active is None else active
    return await build_readiness_response(settings, active_checks=active_checks)


async def build_readiness_response(
    settings: Settings,
    *,
    active_checks: bool = False,
    probes: dict[str, Probe] | None = None,
) -> ReadinessResponse:
    llm_gateway = _llm_gateway_status(settings)
    dependencies = {
        "postgres": _configured_dependency(
            configured=bool(settings.database_url),
            required=True,
            details={"check_mode": "configuration_only", "reachability": "not_checked"},
        ),
        "redis": _configured_dependency(
            configured=bool(settings.redis_url),
            required=True,
            details={"check_mode": "configuration_only", "reachability": "not_checked"},
        ),
        "temporal": _configured_dependency(
            configured=bool(settings.temporal_address and settings.temporal_namespace),
            required=settings.temporal_start_workflows,
            details={
                "namespace": settings.temporal_namespace,
                "task_queue": settings.temporal_task_queue,
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        ),
        "event_hubs": _configured_dependency(
            configured=bool(settings.kafka_bootstrap_servers and settings.kafka_password),
            required=bool(settings.kafka_bootstrap_servers or settings.kafka_password),
            details={
                "alerts_raw_topic": settings.kafka_alerts_raw_topic,
                "deadletter_topic": settings.kafka_deadletter_topic,
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        ),
        "genaihub": _configured_dependency(
            configured=llm_gateway["configured"],
            required=llm_gateway["required"],
            details={
                "provider": llm_gateway["provider"],
                "base_url": llm_gateway["base_url"],
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        ),
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
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        ),
    }
    if active_checks:
        runner = DependencyProbeRunner(settings)
        dependencies = await apply_active_probes(
            dependencies,
            probes=probes or default_probe_map(runner),
            timeout_seconds=settings.readiness_probe_timeout_seconds,
        )
    return ReadinessResponse(
        status=dependency_status(dependencies),
        service=settings.app_name,
        environment=settings.environment,
        dependencies=dependencies,
    )


def _configured_dependency(
    *,
    configured: bool,
    required: bool,
    details: dict,
) -> DependencyReadiness:
    if not required and not configured:
        return DependencyReadiness(
            status="disabled",
            configured=False,
            required=False,
            details=details,
        )
    return DependencyReadiness(
        status="ready" if configured else "misconfigured",
        configured=configured,
        required=required,
        details=details,
    )


def _llm_gateway_status(settings: Settings) -> dict[str, object]:
    anthropic_configured = bool(
        settings.anthropic_base_url and settings.anthropic_auth_token
    )
    genaihub_configured = bool(settings.gateway_base_url and settings.gateway_api_key)
    if anthropic_configured:
        return {
            "provider": "anthropic",
            "base_url": str(settings.anthropic_base_url),
            "configured": True,
            "required": True,
        }
    if genaihub_configured:
        return {
            "provider": "genaihub",
            "base_url": str(settings.gateway_base_url),
            "configured": True,
            "required": True,
        }
    anthropic_present = bool(settings.anthropic_base_url or settings.anthropic_auth_token)
    genaihub_present = bool(settings.gateway_base_url or settings.gateway_api_key)
    provider = "anthropic" if anthropic_present else "genaihub"
    base_url = settings.anthropic_base_url if anthropic_present else settings.gateway_base_url
    return {
        "provider": provider,
        "base_url": str(base_url) if base_url else None,
        "configured": False,
        "required": anthropic_present or genaihub_present,
    }


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
            details={
                "transport": transport,
                allowlist_name: allowlist,
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        )
    if transport != "mcp":
        return DependencyReadiness(
            status="misconfigured",
            configured=False,
            required=True,
            details={
                "transport": transport,
                "reason": "transport must be 'mcp'",
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
        )
    if not endpoint_url:
        return DependencyReadiness(
            status="misconfigured",
            configured=False,
            required=True,
            details={
                "transport": transport,
                "reason": "endpoint URL is required",
                "check_mode": "configuration_only",
                "reachability": "not_checked",
            },
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
            "check_mode": "configuration_only",
            "reachability": "not_checked",
        },
    )

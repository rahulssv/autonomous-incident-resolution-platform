from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import redis.asyncio as redis
from confluent_kafka import Producer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from airp.core.config import Settings
from airp.messaging.eventhub_kafka import kafka_config
from airp.schemas.common import DependencyReadiness
from airp.workflows.client import get_temporal_client


@dataclass(frozen=True)
class ProbeResult:
    reachable: bool
    reason: str | None = None


Probe = Callable[[], Awaitable[ProbeResult]]


class DependencyProbeRunner:
    """Active dependency checks used by `/api/readiness` when enabled."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def postgres(self) -> ProbeResult:
        engine = create_async_engine(self.settings.database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            return ProbeResult(True)
        finally:
            await engine.dispose()

    async def redis(self) -> ProbeResult:
        client = redis.from_url(self.settings.redis_url, decode_responses=True)
        try:
            await client.ping()
            return ProbeResult(True)
        finally:
            await client.aclose()

    async def temporal(self) -> ProbeResult:
        await get_temporal_client(self.settings)
        return ProbeResult(True)

    async def event_hubs(self) -> ProbeResult:
        producer = Producer(kafka_config(self.settings))
        metadata = producer.list_topics(timeout=self.settings.readiness_probe_timeout_seconds)
        if metadata is None:
            return ProbeResult(False, "metadata unavailable")
        return ProbeResult(True)

    async def genaihub(self) -> ProbeResult:
        base_url = self._llm_gateway_base_url()
        if not base_url:
            return ProbeResult(False, "llm gateway base_url is not configured")
        return await self._http_get(str(base_url))

    async def kubernetes_mcp(self) -> ProbeResult:
        if not self.settings.kubernetes_mcp_url:
            return ProbeResult(False, "kubernetes_mcp_url is not configured")
        return await self._http_get(str(self.settings.kubernetes_mcp_url))

    async def github_mcp(self) -> ProbeResult:
        if not self.settings.github_mcp_url:
            return ProbeResult(False, "github_mcp_url is not configured")
        return await self._http_get(str(self.settings.github_mcp_url))

    async def dockerhub(self) -> ProbeResult:
        return await self._http_get(str(self.settings.dockerhub_base_url))

    async def _http_get(self, base_url: str) -> ProbeResult:
        url = f"{base_url.rstrip('/')}/"
        async with httpx.AsyncClient(
            timeout=self.settings.readiness_probe_timeout_seconds
        ) as client:
            response = await client.get(url)
            if response.status_code >= 500:
                return ProbeResult(False, f"http {response.status_code}")
            return ProbeResult(True)

    def _llm_gateway_base_url(self) -> object | None:
        if self.settings.anthropic_base_url and self.settings.anthropic_auth_token:
            return self.settings.anthropic_base_url
        if self.settings.gateway_base_url and self.settings.gateway_api_key:
            return self.settings.gateway_base_url
        return self.settings.anthropic_base_url or self.settings.gateway_base_url


async def apply_active_probes(
    dependencies: dict[str, DependencyReadiness],
    *,
    probes: dict[str, Probe],
    timeout_seconds: float,
) -> dict[str, DependencyReadiness]:
    probed = dict(dependencies)
    for name, dependency in dependencies.items():
        if dependency.status in {"disabled", "misconfigured"}:
            continue
        probe = probes.get(name)
        if probe is None:
            continue
        result = await _run_probe(probe, timeout_seconds)
        details = {
            **dependency.details,
            "check_mode": "active",
            "reachability": "reachable" if result.reachable else "unreachable",
        }
        if result.reason:
            details["reason"] = result.reason
        probed[name] = dependency.model_copy(
            update={
                "status": "ready" if result.reachable else "unavailable",
                "details": _safe_details(details),
            }
        )
    return probed


def dependency_status(dependencies: dict[str, DependencyReadiness]) -> str:
    if any(
        dependency.required and dependency.status in {"misconfigured", "unavailable"}
        for dependency in dependencies.values()
    ):
        return "degraded"
    return "ready"


def default_probe_map(runner: DependencyProbeRunner) -> dict[str, Probe]:
    return {
        "postgres": runner.postgres,
        "redis": runner.redis,
        "temporal": runner.temporal,
        "event_hubs": runner.event_hubs,
        "genaihub": runner.genaihub,
        "kubernetes_mcp": runner.kubernetes_mcp,
        "github_mcp": runner.github_mcp,
        "dockerhub": runner.dockerhub,
    }


async def _run_probe(probe: Probe, timeout_seconds: float) -> ProbeResult:
    try:
        return await asyncio.wait_for(probe(), timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - readiness must summarize failures safely
        return ProbeResult(False, _safe_reason(exc))


def _safe_reason(exc: Exception) -> str:
    return exc.__class__.__name__


def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked_keys = {"password", "token", "secret", "api_key", "connection_string"}
    return {
        key: value
        for key, value in details.items()
        if not any(blocked in key.lower() for blocked in blocked_keys)
    }

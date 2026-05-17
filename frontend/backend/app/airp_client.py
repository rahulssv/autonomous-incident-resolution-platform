from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class AirpClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        timeout: float,
    ) -> None:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

    async def list_incidents(
        self, *, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        response = await self._client.get(
            "/api/incidents", params={"limit": limit, "offset": offset}
        )
        response.raise_for_status()
        return response.json()

    async def get_incident(self, incident_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/api/incidents/{incident_id}")
        response.raise_for_status()
        return response.json()

    async def get_audit(
        self, incident_id: str, *, limit: int = 500, offset: int = 0
    ) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/incidents/{incident_id}/audit",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()

    async def get_workflow_state(self, incident_id: str) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/incidents/{incident_id}/workflow/state"
        )
        response.raise_for_status()
        return response.json()

    async def get_hypotheses(
        self, incident_id: str, *, limit: int = 50
    ) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/incidents/{incident_id}/hypotheses", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

    async def get_tool_calls(
        self, incident_id: str, *, limit: int = 200
    ) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/incidents/{incident_id}/tool-calls", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

    async def get_model_calls(
        self, incident_id: str, *, limit: int = 200
    ) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/incidents/{incident_id}/model-calls", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


_client: AirpClient | None = None


def get_airp_client() -> AirpClient:
    global _client
    if _client is None:
        _client = AirpClient(
            base_url=settings.airp_api_base_url,
            token=settings.airp_service_token,
            timeout=settings.airp_request_timeout_seconds,
        )
    return _client


async def shutdown_airp_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

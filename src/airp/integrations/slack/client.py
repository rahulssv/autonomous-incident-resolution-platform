from __future__ import annotations

from typing import Any

import httpx

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError


class SlackClient:
    """Slack transport boundary for incident notifications and approval prompts."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_transport = http_transport

    async def send_incident_notification(
        self, channel: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.settings.slack_webhook_url:
            raise AppError(
                "Slack webhook URL is not configured",
                status_code=503,
                code="slack_not_configured",
            )

        message = {"channel": channel, **payload}
        async with httpx.AsyncClient(timeout=20.0, transport=self.http_transport) as client:
            response = await client.post(str(self.settings.slack_webhook_url), json=message)

        if response.status_code >= 400:
            raise AppError(
                "Slack webhook request failed",
                status_code=502,
                code="slack_webhook_failed",
            )

        return {
            "ok": True,
            "channel": channel,
            "status_code": response.status_code,
            "response_body": response.text[:500],
        }

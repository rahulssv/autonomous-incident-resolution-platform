import json

import httpx
import pytest

from backend.src.airp.core.config import Settings
from backend.src.airp.core.errors import AppError
from backend.src.airp.integrations.slack.client import SlackClient


@pytest.mark.asyncio
async def test_slack_client_posts_incident_notification_to_webhook() -> None:
    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content.decode()))
        return httpx.Response(200, text="ok")

    client = SlackClient(
        Settings(slack_webhook_url="https://hooks.slack.com/services/T000/B000/secret"),
        http_transport=httpx.MockTransport(handler),
    )

    result = await client.send_incident_notification(
        "#airp-alerts",
        {"text": "AIRP incident ready"},
    )

    assert result["ok"] is True
    assert result["channel"] == "#airp-alerts"
    assert seen_payload == {"channel": "#airp-alerts", "text": "AIRP incident ready"}


@pytest.mark.asyncio
async def test_slack_client_requires_webhook_url() -> None:
    client = SlackClient(Settings(slack_webhook_url=None))

    with pytest.raises(AppError) as exc_info:
        await client.send_incident_notification("#airp-alerts", {"text": "hello"})

    assert exc_info.value.code == "slack_not_configured"


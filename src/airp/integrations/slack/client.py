from typing import Any


class SlackClient:
    """Slack transport boundary for incident notifications and approval prompts."""

    async def send_incident_notification(
        self, channel: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError("Slack transport will be implemented in the workflow phase")

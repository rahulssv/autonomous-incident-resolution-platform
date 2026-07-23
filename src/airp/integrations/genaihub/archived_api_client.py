"""ARCHIVED — Bob HTTP/REST gateway client.

This module is intentionally not imported by any live code.
It is retained for historical reference only.  The active implementation
has been replaced by :mod:`airp.integrations.genaihub.bob_cli_client`,
which drives the locally-installed BOB CLI instead of making direct
HTTP calls to the BOB API.

DO NOT re-enable this code without a deliberate migration review.
"""
from __future__ import annotations

# ruff: noqa
# mypy: ignore-errors

import os
import ssl

import httpx
from openai import OpenAI

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError
from airp.integrations.genaihub.client import OpenAICompatibleGatewayClient


class _ArchivedBobGatewayClient(OpenAICompatibleGatewayClient):
    """ARCHIVED — OpenAI-compatible HTTP client for the IBM Bob inference API.

    Bob used ``Authorization: Apikey <token>`` (not Bearer) and required
    ``x-instance-id`` / ``x-team-id`` headers on every request.

    This class is preserved so that the integration logic and header
    mechanics remain visible in version history. It is NOT instantiated
    anywhere in the live application. Use ``BobCLIClient`` instead.

    Original behaviour:
    * Endpoint: AIRP_BOB_BASE_URL/inference/v1
    * Auth:     Authorization: Apikey <AIRP_BOB_AUTH_TOKEN>
    * Headers:  x-instance-id / x-team-id (optional)
    * Timeout:  120s (Bob models can be slow on large prompts)
    * Retries:  AIRP_GATEWAY_MAX_RETRIES (default 0)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.bob_auth_token:
            raise AppError(
                "Bob gateway is not configured",
                status_code=503,
                code="bob_gateway_not_configured",
            )
        super().__init__(
            settings=settings,
            base_url=f"{str(settings.bob_base_url).rstrip('/')}/inference/v1",
            api_key="bob-placeholder",  # overridden below via default_headers
            max_retries=settings.gateway_max_retries,
            provider_name="Bob inference gateway",
            not_configured_code="bob_gateway_not_configured",
        )
        bob_headers: dict[str, str] = {
            "Authorization": f"Apikey {settings.bob_auth_token}",
        }
        if settings.bob_instance_id:
            bob_headers["x-instance-id"] = settings.bob_instance_id
        if settings.bob_team_id:
            bob_headers["x-team-id"] = settings.bob_team_id
        self.client = self.client.with_options(
            default_headers=bob_headers,
            http_client=self._bob_http_client(),
            timeout=120.0,
        )

    def _bob_http_client(self) -> httpx.Client:
        ca_bundle = os.getenv("SSL_CERT_FILE", os.getenv("REQUESTS_CA_BUNDLE"))
        ctx = ssl.create_default_context(cafile=ca_bundle)
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return httpx.Client(verify=ctx, timeout=120.0)

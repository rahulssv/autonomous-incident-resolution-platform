from __future__ import annotations

import json
import os
import ssl
import time
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError
from airp.integrations.genaihub.redaction import redact_payload

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OpenAICompatibleGatewayClient:
    """Production-safe client for gateways exposing OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        settings: Settings,
        base_url: object | None,
        api_key: str | None,
        max_retries: int,
        provider_name: str,
        not_configured_code: str,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider_name = provider_name
        if not base_url or not api_key:
            raise AppError(
                f"{provider_name} is not configured",
                status_code=503,
                code=not_configured_code,
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url=str(base_url).rstrip("/"),
            http_client=self._build_http_client(),
            max_retries=max_retries,
        )

    def _build_http_client(self) -> httpx.Client:
        ca_bundle = os.getenv("SSL_CERT_FILE", os.getenv("REQUESTS_CA_BUNDLE"))
        ssl_context = ssl.create_default_context(cafile=ca_bundle)
        ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return httpx.Client(verify=ssl_context, timeout=60.0)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        sanitized_messages = redact_payload(list(messages))
        started = time.monotonic()
        response = self.client.chat.completions.create(
            model=model,
            messages=sanitized_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers={"x-airp-request-id": request_id} if request_id else None,
        )
        payload = response.model_dump()
        payload["_airp_latency_ms"] = int((time.monotonic() - started) * 1000)
        return payload

    def structured_chat(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, Any]],
        response_model: type[StructuredModel],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> StructuredModel:
        response = self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            request_id=request_id,
        )
        content = response["choices"][0]["message"]["content"]
        try:
            return response_model.model_validate_json(content)
        except ValidationError:
            # Some gateway models wrap JSON in prose. Try a conservative JSON object extraction
            # before declaring the model output invalid.
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return response_model.model_validate(json.loads(content[start : end + 1]))

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def embed(self, *, input_text: str | list[str], model: str | None = None) -> list[list[float]]:
        sanitized_input = redact_payload(input_text)
        response = self.client.embeddings.create(
            model=model or self.settings.llm_embedding_model,
            input=sanitized_input,
        )
        return [item.embedding for item in response.data]


class GenAIHubClient(OpenAICompatibleGatewayClient):
    """Production-safe OpenAI-compatible client for the GenAI Hub gateway."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(
            settings=settings,
            base_url=settings.gateway_base_url,
            api_key=settings.gateway_api_key,
            max_retries=settings.gateway_max_retries,
            provider_name="GenAI Hub gateway",
            not_configured_code="genaihub_not_configured",
        )


class AnthropicGatewayClient(OpenAICompatibleGatewayClient):
    """OpenAI-compatible client for the Anthropic-named inference gateway."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        super().__init__(
            settings=settings,
            base_url=_anthropic_openai_base_url(settings.anthropic_base_url),
            api_key=settings.anthropic_auth_token,
            max_retries=settings.gateway_max_retries,
            provider_name="Anthropic inference gateway",
            not_configured_code="anthropic_gateway_not_configured",
        )


def _anthropic_openai_base_url(base_url: object | None) -> str | None:
    if not base_url:
        return None
    normalized = str(base_url).rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"

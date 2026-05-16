from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError
from airp.integrations.genaihub.redaction import redact_payload

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

# Models that drop sampling params and require adaptive thinking only.
_OPUS_4_7_PREFIX = "claude-opus-4-7"


class AnthropicClient:
    """Anthropic (Claude) client compatible with the agents' chat/structured_chat protocol.

    Reads ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN from Settings.
    Sends Authorization: Bearer <token> via the SDK's auth_token path.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.anthropic_auth_token:
            raise AppError(
                "Anthropic gateway is not configured (AIRP_ANTHROPIC_AUTH_TOKEN missing)",
                status_code=503,
                code="anthropic_not_configured",
            )
        self.client = anthropic.Anthropic(
            auth_token=self.settings.anthropic_auth_token,
            base_url=str(self.settings.anthropic_base_url).rstrip("/")
            if self.settings.anthropic_base_url
            else None,
            max_retries=self.settings.anthropic_max_retries,
            timeout=60.0,
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
        """Compatibility shim returning an OpenAI-shaped dict so existing callers don't break."""
        system_text, anthropic_messages = self._split_messages(messages)
        kwargs = self._build_kwargs(
            model=model,
            system_text=system_text,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            request_id=request_id,
        )
        started = time.monotonic()
        response = self.client.messages.create(**kwargs)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return {
            "id": response.id,
            "model": response.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": response.stop_reason,
                }
            ],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "_airp_latency_ms": int((time.monotonic() - started) * 1000),
        }

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
        system_text, anthropic_messages = self._split_messages(messages)
        schema_instruction = (
            "Respond with a single JSON object that conforms exactly to this Pydantic schema. "
            "Do not include prose, markdown fences, or commentary outside the JSON object.\n\n"
            f"Schema name: {response_model.__name__}\n"
            f"Schema: {json.dumps(response_model.model_json_schema(), separators=(',', ':'))}"
        )
        combined_system = (
            f"{system_text}\n\n{schema_instruction}" if system_text else schema_instruction
        )
        kwargs = self._build_kwargs(
            model=model,
            system_text=combined_system,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            request_id=request_id,
        )
        response = self.client.messages.create(**kwargs)
        content = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        try:
            return response_model.model_validate_json(content)
        except ValidationError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return response_model.model_validate(json.loads(content[start : end + 1]))

    def _build_kwargs(
        self,
        *,
        model: str,
        system_text: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        request_id: str | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_text:
            kwargs["system"] = system_text
        # Opus 4.7 removes temperature/top_p/top_k and budget_tokens. Adaptive thinking only.
        if model.startswith(_OPUS_4_7_PREFIX):
            kwargs["thinking"] = {"type": "adaptive"}
        else:
            kwargs["temperature"] = temperature
        if request_id:
            kwargs["extra_headers"] = {"x-airp-request-id": request_id}
        return kwargs

    @staticmethod
    def _split_messages(
        messages: Sequence[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert OpenAI-style messages to (system_text, anthropic_messages).

        Anthropic puts the system prompt in a separate top-level field. Tool/assistant turns
        from earlier conversation pass through unchanged.
        """
        sanitized = redact_payload(list(messages))
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for entry in sanitized:
            role = entry.get("role")
            content = entry.get("content", "")
            if role == "system":
                if isinstance(content, list):
                    system_parts.extend(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                else:
                    system_parts.append(str(content))
                continue
            if role not in ("user", "assistant"):
                # Unknown roles get coerced into a user turn so we don't lose context.
                role = "user"
            converted.append({"role": role, "content": content})
        if not converted:
            # Anthropic requires at least one message; surface this as an explicit error.
            raise AppError(
                "Anthropic request requires at least one user or assistant message",
                status_code=400,
                code="anthropic_empty_messages",
            )
        return "\n\n".join(part for part in system_parts if part), converted

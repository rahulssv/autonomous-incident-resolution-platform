"""Bob CLI client — drives the locally-installed ``bob`` binary.

This module replaces the archived HTTP-based
:class:`~airp.integrations.genaihub.archived_api_client._ArchivedBobGatewayClient`.
Instead of making direct REST calls to the Bob API endpoint, every request
is executed as a subprocess:

    bob --model <model> --output-format stream-json [--instance-id ...] [--team-id ...] <prompt>

The CLI writes one JSON object per line (NDJSON).  The assistant's reply is
carried in the ``tool_use`` event where ``tool_name == "attempt_completion"``
under ``parameters.result``.  The final ``result`` line contains stats.

Authentication is injected by writing ``AIRP_BOB_AUTH_TOKEN`` into the
subprocess environment before each call (the CLI picks it up automatically).

The public interface (``chat``, ``structured_chat``, ``embed``) mirrors the
``OpenAICompatibleGatewayClient`` interface so all agents work without any
changes to their own code.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError
from airp.integrations.genaihub.redaction import redact_payload, redact_text

logger = logging.getLogger(__name__)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

# Timeout (seconds) for a single CLI call.  Bob models can be slow on large prompts.
_CLI_TIMEOUT_SECONDS = 120


def _ensure_authenticated(settings: Settings) -> None:
    """Write the auth token into the process environment so the CLI picks it up.

    The BOB CLI reads its credentials from the ``BOB_API_KEY`` environment
    variable (or equivalent).  We set it from ``AIRP_BOB_AUTH_TOKEN`` so that
    no long-lived credential file is required.
    """
    if not settings.bob_auth_token:
        raise AppError(
            "Bob CLI is not configured: AIRP_BOB_AUTH_TOKEN is not set",
            status_code=503,
            code="bob_cli_not_configured",
        )
    # The CLI reads the token from the environment; we propagate it here so
    # that it is always current even if the settings object is refreshed.
    os.environ.setdefault("BOB_API_KEY", settings.bob_auth_token)
    # Overwrite unconditionally so a settings reload takes effect.
    os.environ["BOB_API_KEY"] = settings.bob_auth_token


def _build_cli_env(settings: Settings) -> dict[str, str]:
    """Return an env dict for the subprocess, with auth injected."""
    env = os.environ.copy()
    env["BOB_API_KEY"] = settings.bob_auth_token  # type: ignore[assignment]
    return env


def _build_base_cmd(settings: Settings, model: str) -> list[str]:
    """Build the base ``bob`` command list (without the prompt).

    Uses ``--output-format stream-json`` so the response is machine-parseable
    NDJSON.  The ``--model`` flag routes to the correct per-task model.
    """
    cmd: list[str] = [
        settings.bob_cli_path,
        "--model", model,
        "--output-format", "stream-json",
    ]
    if settings.bob_instance_id:
        cmd += ["--instance-id", settings.bob_instance_id]
    if settings.bob_team_id:
        cmd += ["--team-id", settings.bob_team_id]
    return cmd


def _run_cli(cmd: list[str], prompt: str, env: dict[str, str]) -> str:
    """Execute the CLI and return the assistant's response text.

    The CLI emits one JSON object per line (NDJSON).  The response is in the
    ``tool_use`` event where ``tool_name == "attempt_completion"`` under
    ``parameters.result``.  The final ``result`` line contains stats only.

    Raises ``AppError`` on non-zero exit codes, missing response, or parse
    failures.
    """
    full_cmd = cmd + [prompt]
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            f"Bob CLI timed out after {_CLI_TIMEOUT_SECONDS}s",
            status_code=504,
            code="bob_cli_timeout",
        ) from exc
    except FileNotFoundError as exc:
        raise AppError(
            "Bob CLI executable not found. "
            "Ensure 'bob' is installed and AIRP_BOB_CLI_PATH is correct.",
            status_code=503,
            code="bob_cli_not_found",
        ) from exc

    if proc.returncode != 0:
        stderr_snippet = proc.stderr[:500] if proc.stderr else "(no stderr)"
        raise AppError(
            f"Bob CLI exited with code {proc.returncode}: {stderr_snippet}",
            status_code=502,
            code="bob_cli_error",
        )

    return _parse_stream_json(proc.stdout)


def _parse_stream_json(stdout: str) -> str:
    """Extract the assistant reply from ``--output-format stream-json`` output.

    The CLI writes one JSON object per line.  The response text is stored in::

        {"type": "tool_use", "tool_name": "attempt_completion",
         "parameters": {"result": "<text>"}, ...}

    If no ``attempt_completion`` event is present the final non-empty line is
    tried as a fallback (forward-compat: future CLI versions may change names).
    """
    last_non_empty = ""
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        last_non_empty = line
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            obj.get("type") == "tool_use"
            and obj.get("tool_name") == "attempt_completion"
        ):
            result = obj.get("parameters", {}).get("result", "")
            return str(result).strip()

    if not last_non_empty:
        raise AppError(
            "Bob CLI returned empty output",
            status_code=502,
            code="bob_cli_empty_response",
        )
    raise AppError(
        "Bob CLI stream-json contained no attempt_completion event. "
        f"Last line: {last_non_empty[:200]!r}",
        status_code=502,
        code="bob_cli_no_content",
    )


class BobCLIClient:
    """LLM client that drives the locally-installed Bob CLI binary.

    Implements the same ``chat`` / ``structured_chat`` / ``embed`` interface
    as ``OpenAICompatibleGatewayClient`` so all agents work without changes.

    Authentication:
        The CLI is authenticated by injecting ``AIRP_BOB_AUTH_TOKEN`` as the
        ``BOB_API_KEY`` environment variable before every subprocess call.
        No credential files or ``bob login`` flow is required at runtime.

    Model routing:
        Each call passes ``--model <model>`` explicitly, so the per-task model
        env vars (``AIRP_LLM_RCA_MODEL``, ``AIRP_LLM_MONITORING_MODEL``, …)
        are respected through the ``settings`` object passed by the factory.

    CLI invocation::

        bob --model <model> \\
            --output-format stream-json \\
            [--instance-id <id>] \\
            [--team-id <id>] \\
            "<prompt>"

    The response is parsed from the ``attempt_completion`` tool_use NDJSON event.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Validate credentials eagerly so misconfiguration surfaces at startup.
        _ensure_authenticated(self.settings)

    # ------------------------------------------------------------------
    # Public interface (mirrors OpenAICompatibleGatewayClient)
    # ------------------------------------------------------------------

    def chat(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat-style prompt to the Bob CLI and return the raw payload.

        ``messages`` is serialised to a compact JSON string and passed as the
        positional prompt argument.  Temperature and max_tokens are advisory
        only — the CLI does not expose these flags; they are retained in the
        signature for interface compatibility.
        """
        _ = temperature, max_tokens  # ponytail: CLI does not expose these flags
        sanitized = redact_payload(list(messages))
        prompt = json.dumps(sanitized, separators=(",", ":"))

        cmd = _build_base_cmd(self.settings, model)
        env = _build_cli_env(self.settings)

        if request_id:
            logger.debug("bob_cli chat request_id=%s model=%s", request_id, model)

        started = time.monotonic()
        content = _run_cli(cmd, prompt, env)
        return {
            "content": content,
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
        """Chat and parse the result into a Pydantic model.

        The CLI is asked to respond as a plain JSON object via a system
        instruction prepended to the message list.  If the model wraps the
        JSON in prose a conservative object-extraction fallback is attempted
        (identical to the archived HTTP client's behaviour).
        """
        augmented = list(messages)
        augmented.insert(0, {
            "role": "system",
            "content": (
                "Respond with ONLY a single valid JSON object matching the "
                "required schema. Do not wrap the JSON in prose or markdown fences."
            ),
        })
        payload = self.chat(
            model=model,
            messages=augmented,
            temperature=temperature,
            max_tokens=max_tokens,
            request_id=request_id,
        )
        content = payload["content"]
        try:
            return response_model.model_validate_json(content)
        except ValidationError:
            # Conservative JSON-object extraction — some models wrap output in prose.
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return response_model.model_validate(json.loads(content[start: end + 1]))

    def embed(
        self, *, input_text: str | list[str], model: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings via the Bob CLI.

        Each text is sent as a separate CLI call because the CLI is a
        single-turn interface.  Results are returned in input order.

        Note: Bob does not expose a /v1/embeddings endpoint via the CLI
        either — if the Bob model does not support embedding generation the
        CLI will return an error and ``AppError`` will propagate.  In that
        case, configure ``AIRP_GATEWAY_BASE_URL`` / ``AIRP_GATEWAY_API_KEY``
        so the factory falls back to GenAI Hub for embeddings (same behaviour
        as the archived HTTP client).
        """
        effective_model = model or self.settings.llm_embedding_model
        if isinstance(input_text, str):
            texts = [input_text]
        else:
            texts = list(input_text)

        vectors: list[list[float]] = []
        for text in texts:
            sanitized = redact_text(text)
            prompt = json.dumps(
                {"task": "embed", "input": sanitized}, separators=(",", ":")
            )
            cmd = _build_base_cmd(self.settings, effective_model)
            env = _build_cli_env(self.settings)
            content = _run_cli(cmd, prompt, env)
            # Expect the model to return a JSON array of floats.
            try:
                vec = json.loads(content)
                if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
                    vectors.append([float(v) for v in vec])
                elif isinstance(vec, dict) and "embedding" in vec:
                    vectors.append([float(v) for v in vec["embedding"]])
                else:
                    raise ValueError(f"unexpected embedding shape: {content[:100]!r}")
            except (json.JSONDecodeError, ValueError) as exc:
                raise AppError(
                    f"Bob CLI embedding response could not be parsed: {exc}",
                    status_code=502,
                    code="bob_cli_embedding_parse_error",
                ) from exc
        return vectors

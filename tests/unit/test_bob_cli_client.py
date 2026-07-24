"""Unit tests for BobCLIClient and its stream-json output parser.

These tests are fully offline — no subprocess is spawned, no network call is
made.  Every test uses the *exact* NDJSON format produced by:

    bob --output-format stream-json "<prompt>"

Captured from a real run:

    {"type":"init","session_id":"...","model":"premium"}
    {"type":"message","role":"user","content":"..."}
    {"type":"message","role":"assistant","content":"<thinking>...","delta":true}
    ...delta lines...
    {"type":"tool_use","tool_name":"attempt_completion","tool_id":"tool-1",
     "parameters":{"result":"\\nPONG\\n"}}
    {"type":"tool_result","tool_id":"tool-1","status":"success","output":"\\nPONG\\n"}
    {"type":"result","status":"success","stats":{...}}
"""
from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from airp.core.config import Settings
from airp.core.errors import AppError
from airp.integrations.genaihub.bob_cli_client import (
    BobCLIClient,
    _build_base_cmd,
    _flatten_messages,
    _parse_stream_json,
    _run_cli,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTINGS = Settings(_env_file=None, bob_auth_token="test-tok", bob_cli_path="bob")


def _ndjson(*objects: dict) -> str:
    """Serialize a sequence of dicts as NDJSON (one JSON object per line)."""
    return "\n".join(json.dumps(obj) for obj in objects) + "\n"


def _make_stream(result_text: str) -> str:
    """Return a minimal but realistic stream-json payload with the given reply."""
    return _ndjson(
        {"type": "init", "session_id": "s1", "model": "premium"},
        {"type": "message", "role": "user", "content": "prompt"},
        # delta lines (the actual streamed tokens) — parser must skip these
        {"type": "message", "role": "assistant", "content": "chunk", "delta": True},
        {
            "type": "tool_use",
            "tool_name": "attempt_completion",
            "tool_id": "tool-1",
            "parameters": {"result": result_text},
        },
        {"type": "tool_result", "tool_id": "tool-1", "status": "success", "output": result_text},
        {
            "type": "result",
            "status": "success",
            "stats": {"total_tokens": 100, "input_tokens": 80, "output_tokens": 20},
        },
    )


def _fake_proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# _parse_stream_json — unit tests for the NDJSON parser
# ---------------------------------------------------------------------------


def test_parse_stream_json_extracts_attempt_completion_result() -> None:
    stream = _make_stream("\nPONG\n")
    assert _parse_stream_json(stream) == "PONG"


def test_parse_stream_json_strips_leading_trailing_whitespace() -> None:
    stream = _make_stream("  hello world  ")
    assert _parse_stream_json(stream) == "hello world"


def test_parse_stream_json_handles_multiline_result() -> None:
    stream = _make_stream('{"key": "value",\n"other": 1}')
    result = _parse_stream_json(stream)
    assert '"key"' in result


def test_parse_stream_json_skips_delta_lines() -> None:
    """Delta lines have role=assistant and delta=true — they must not be returned."""
    stream = _ndjson(
        {"type": "message", "role": "assistant", "content": "should-be-ignored", "delta": True},
        {
            "type": "tool_use",
            "tool_name": "attempt_completion",
            "tool_id": "t1",
            "parameters": {"result": "real-answer"},
        },
    )
    assert _parse_stream_json(stream) == "real-answer"


def test_parse_stream_json_raises_on_empty_output() -> None:
    with pytest.raises(AppError) as exc_info:
        _parse_stream_json("   \n  \n  ")
    assert exc_info.value.code == "bob_cli_empty_response"


def test_parse_stream_json_raises_when_no_attempt_completion() -> None:
    stream = _ndjson(
        {"type": "init"},
        {"type": "result", "status": "success", "stats": {}},
    )
    with pytest.raises(AppError) as exc_info:
        _parse_stream_json(stream)
    assert exc_info.value.code == "bob_cli_no_content"


def test_parse_stream_json_tolerates_non_json_lines() -> None:
    """The CLI may write [ERROR] lines to stdout — the parser must skip them."""
    stream = (
        "[ERROR] MCP server timeout\n"
        + _ndjson(
            {
                "type": "tool_use",
                "tool_name": "attempt_completion",
                "tool_id": "t1",
                "parameters": {"result": "ok"},
            }
        )
    )
    assert _parse_stream_json(stream) == "ok"


# ---------------------------------------------------------------------------
# _build_base_cmd
# ---------------------------------------------------------------------------


def test_build_base_cmd_includes_model_and_stream_json() -> None:
    cmd = _build_base_cmd(_SETTINGS, "sonnet-4.6")
    assert cmd == [
        "bob", "--model", "sonnet-4.6", "--output-format", "stream-json", "--accept-license",
    ]


def test_build_base_cmd_prefixes_node_for_js_path() -> None:
    s = Settings(_env_file=None, bob_auth_token="tok", bob_cli_path="/opt/bobshell/bundle/bob.js")
    cmd = _build_base_cmd(s, "sonnet-4.6")
    assert cmd == [
        "node", "/opt/bobshell/bundle/bob.js", "--model", "sonnet-4.6",
        "--output-format", "stream-json", "--accept-license",
    ]


def test_build_base_cmd_appends_instance_and_team_ids() -> None:
    s = Settings(
        _env_file=None,
        bob_auth_token="tok",
        bob_instance_id="inst-1",
        bob_team_id="team-1",
    )
    cmd = _build_base_cmd(s, "haiku-4.5")
    assert "--instance-id" in cmd
    assert "inst-1" in cmd
    assert "--team-id" in cmd
    assert "team-1" in cmd


def test_build_base_cmd_accepts_license_so_a_fresh_home_does_not_block() -> None:
    """Without --accept-license the CLI exits non-zero on any HOME lacking consent."""
    assert "--accept-license" in _build_base_cmd(_SETTINGS, "haiku-4.5")


def test_build_base_cmd_omits_ids_when_not_set() -> None:
    cmd = _build_base_cmd(_SETTINGS, "haiku-4.5")
    assert "--instance-id" not in cmd
    assert "--team-id" not in cmd


# ---------------------------------------------------------------------------
# _run_cli — subprocess error handling
# ---------------------------------------------------------------------------


def test_run_cli_raises_on_nonzero_exit() -> None:
    cmd = ["bob", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(returncode=1, stderr="auth failed"),
    ):
        with pytest.raises(AppError) as exc_info:
            _run_cli(cmd, "prompt", env)
    assert exc_info.value.code == "bob_cli_error"
    assert "auth failed" in str(exc_info.value)


def test_run_cli_raises_on_timeout() -> None:
    cmd = ["bob", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd, 120),
    ):
        with pytest.raises(AppError) as exc_info:
            _run_cli(cmd, "prompt", env)
    assert exc_info.value.code == "bob_cli_timeout"


def test_run_cli_raises_when_binary_not_found() -> None:
    cmd = ["bob-missing", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        with pytest.raises(AppError) as exc_info:
            _run_cli(cmd, "prompt", env)
    assert exc_info.value.code == "bob_cli_not_found"


def test_flatten_messages_emits_plain_prompt_without_role_envelope() -> None:
    """A serialised role/content array makes the CLI refuse the task as prompt injection."""
    prompt = _flatten_messages(
        [
            {"role": "system", "content": "Return ONLY JSON."},
            {"role": "user", "content": '{"incident_id":"INC-1"}'},
        ]
    )
    assert '"role"' not in prompt
    assert "Return ONLY JSON." in prompt
    assert '{"incident_id":"INC-1"}' in prompt
    # Instructions must lead; the untrusted payload follows.
    assert prompt.index("Return ONLY JSON.") < prompt.index('{"incident_id":"INC-1"}')


def test_chat_passes_flattened_prompt_to_cli() -> None:
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(stdout=_make_stream("ok")),
    ) as run_mock:
        BobCLIClient(_SETTINGS).chat(
            model="sonnet-4.6",
            messages=[
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "why did checkout-api fail"},
            ],
        )
    prompt = run_mock.call_args[0][0][-1]
    assert '"role"' not in prompt
    assert "Be terse." in prompt
    assert "why did checkout-api fail" in prompt


def test_run_cli_runs_in_a_writable_scratch_dir_not_the_app_cwd() -> None:
    """Bob writes <cwd>/.bob session state, which must not land in the source tree."""
    cmd = ["bob", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(stdout=_make_stream("ok")),
    ) as run_mock:
        _run_cli(cmd, "prompt", env)
    workdir = run_mock.call_args.kwargs["cwd"]
    assert workdir is not None
    assert workdir != os.getcwd()
    assert os.path.isdir(workdir)
    assert os.access(workdir, os.W_OK)


def test_run_cli_raises_when_binary_is_not_executable() -> None:
    """A .js bundle copied without the exec bit raises PermissionError, not FileNotFoundError."""
    cmd = ["/opt/bobshell/bundle/bob.js", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        side_effect=PermissionError(13, "Permission denied"),
    ):
        with pytest.raises(AppError) as exc_info:
            _run_cli(cmd, "prompt", env)
    assert exc_info.value.code == "bob_cli_not_executable"


def test_run_cli_returns_text_from_attempt_completion() -> None:
    cmd = ["bob", "--model", "m", "--output-format", "stream-json"]
    env = {"BOBSHELL_API_KEY": "tok"}
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(stdout=_make_stream("hello from bob")),
    ):
        text = _run_cli(cmd, "prompt", env)
    assert text == "hello from bob"


# ---------------------------------------------------------------------------
# BobCLIClient.chat
# ---------------------------------------------------------------------------


def test_bob_cli_client_chat_passes_model_flag() -> None:
    captured: list = []

    def fake_run(full_cmd, **_kw):
        captured.append(full_cmd)
        return _fake_proc(stdout=_make_stream("ok"))

    with patch("airp.integrations.genaihub.bob_cli_client.subprocess.run", fake_run):
        client = BobCLIClient(_SETTINGS)
        result = client.chat(model="sonnet-4.6", messages=[{"role": "user", "content": "hi"}])

    assert result["content"] == "ok"
    assert "--model" in captured[0]
    assert "sonnet-4.6" in captured[0]
    assert "--output-format" in captured[0]
    assert "stream-json" in captured[0]
    assert "_airp_latency_ms" in result


def test_bob_cli_client_chat_injects_bobshell_api_key_into_env() -> None:
    """BOBSHELL_API_KEY is the only name the CLI reads; any other falls back to SSO."""
    received_env: list[dict] = []

    def fake_run(_, *, env, **kw):
        received_env.append(env)
        return _fake_proc(stdout=_make_stream("ok"))

    with patch("airp.integrations.genaihub.bob_cli_client.subprocess.run", fake_run):
        client = BobCLIClient(_SETTINGS)
        client.chat(model="haiku-4.5", messages=[{"role": "user", "content": "hi"}])

    assert received_env[0]["BOBSHELL_API_KEY"] == "test-tok"


def test_bob_cli_client_chat_points_home_at_a_writable_scratch_dir() -> None:
    """The container service account has HOME=/nonexistent; the CLI writes $HOME/.bob."""
    received_env: list[dict] = []

    def fake_run(_, *, env, **kw):
        received_env.append(env)
        return _fake_proc(stdout=_make_stream("ok"))

    with patch("airp.integrations.genaihub.bob_cli_client.subprocess.run", fake_run):
        client = BobCLIClient(_SETTINGS)
        client.chat(model="haiku-4.5", messages=[{"role": "user", "content": "hi"}])

    home = received_env[0]["HOME"]
    assert os.path.isdir(home)
    assert os.access(home, os.W_OK)


def test_bob_cli_client_chat_redacts_secrets_from_prompt() -> None:
    captured_prompt: list[str] = []

    def fake_run(full_cmd, **_kw):
        captured_prompt.append(full_cmd[-1])  # prompt is the last positional arg
        return _fake_proc(stdout=_make_stream("ok"))

    with patch("airp.integrations.genaihub.bob_cli_client.subprocess.run", fake_run):
        client = BobCLIClient(_SETTINGS)
        client.chat(
            model="haiku-4.5",
            messages=[{"role": "user", "content": "api_key=super-secret-value"}],
        )

    assert "super-secret-value" not in captured_prompt[0]
    assert "[REDACTED]" in captured_prompt[0]


# ---------------------------------------------------------------------------
# BobCLIClient.structured_chat
# ---------------------------------------------------------------------------


class _Greeting(BaseModel):
    message: str
    language: str


def test_bob_cli_client_structured_chat_parses_json_response() -> None:
    reply = json.dumps({"message": "Hello", "language": "English"})
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(stdout=_make_stream(reply)),
    ):
        client = BobCLIClient(_SETTINGS)
        result = client.structured_chat(
            model="sonnet-4.5",
            messages=[{"role": "user", "content": "greet me"}],
            response_model=_Greeting,
        )

    assert result.message == "Hello"
    assert result.language == "English"


def test_bob_cli_client_structured_chat_extracts_json_from_prose() -> None:
    """The model sometimes wraps JSON in prose — the fallback extractor must handle it."""
    reply = 'Sure! Here is the result: {"message": "Hi", "language": "French"} Hope that helps!'
    with patch(
        "airp.integrations.genaihub.bob_cli_client.subprocess.run",
        return_value=_fake_proc(stdout=_make_stream(reply)),
    ):
        client = BobCLIClient(_SETTINGS)
        result = client.structured_chat(
            model="sonnet-4.5",
            messages=[{"role": "user", "content": "greet me"}],
            response_model=_Greeting,
        )

    assert result.message == "Hi"
    assert result.language == "French"


def test_bob_cli_client_structured_chat_prepends_json_system_instruction() -> None:
    captured: list[list] = []

    def fake_run(full_cmd, **_kw):
        captured.append(full_cmd)
        return _fake_proc(stdout=_make_stream('{"message":"ok","language":"en"}'))

    with patch("airp.integrations.genaihub.bob_cli_client.subprocess.run", fake_run):
        client = BobCLIClient(_SETTINGS)
        client.structured_chat(
            model="sonnet-4.5",
            messages=[{"role": "user", "content": "greet me"}],
            response_model=_Greeting,
        )

    prompt = captured[0][-1]
    assert "JSON" in prompt  # system instruction is included


# ---------------------------------------------------------------------------
# BobCLIClient init — misconfiguration
# ---------------------------------------------------------------------------


def test_bob_cli_client_raises_when_auth_token_missing() -> None:
    with pytest.raises(AppError) as exc_info:
        BobCLIClient(Settings(_env_file=None))  # no bob_auth_token
    assert exc_info.value.code == "bob_cli_not_configured"

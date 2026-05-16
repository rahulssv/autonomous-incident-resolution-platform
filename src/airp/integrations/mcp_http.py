from __future__ import annotations

from typing import Any

import httpx


class MCPToolResponseError(ValueError):
    """Raised when an MCP HTTP bridge returns an unusable tool response."""


async def call_mcp_tool(
    *,
    endpoint_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Any:
    """Call the AIRP read-only MCP HTTP bridge.

    Contract:

    - Request: `POST {endpoint}/tools/call`
    - Body: `{"tool": "<tool-name>", "arguments": {...}}`
    - Response: direct JSON, `{"result": ...}`, `{"data": ...}`, or MCP-style
      `{"content": [{"type": "json", "json": ...}]}`
    """

    url = _tool_call_url(endpoint_url)
    async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
        response = await client.post(
            url,
            json={"tool": tool_name, "arguments": arguments},
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        return normalize_mcp_response(response.json())


def normalize_mcp_response(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if "error" in payload and payload["error"]:
        raise MCPToolResponseError(f"MCP tool returned an error: {payload['error']}")
    if "result" in payload:
        return normalize_mcp_response(payload["result"])
    if "data" in payload:
        return normalize_mcp_response(payload["data"])
    if "content" in payload:
        return _content_payload(payload["content"])
    return payload


def item_list(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_dict_item(item) for item in payload]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [_dict_item(item) for item in value]
    raise MCPToolResponseError(f"Expected MCP response list under one of: {', '.join(keys)}")


def optional_dict(payload: Any, *keys: str) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value is None:
                return None
            if isinstance(value, dict):
                return value
        return payload
    raise MCPToolResponseError("Expected MCP response object")


def _tool_call_url(endpoint_url: str) -> str:
    url = endpoint_url.rstrip("/")
    if url.endswith("/tools/call"):
        return url
    return f"{url}/tools/call"


def _content_payload(content: Any) -> Any:
    if not isinstance(content, list) or not content:
        raise MCPToolResponseError("MCP content response must contain at least one item")
    first = content[0]
    if not isinstance(first, dict):
        raise MCPToolResponseError("MCP content item must be an object")
    if "json" in first:
        return first["json"]
    if first.get("type") == "text" and "text" in first:
        return first["text"]
    raise MCPToolResponseError("MCP content item must contain json or text")


def _dict_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    raise MCPToolResponseError("Expected MCP list items to be objects")

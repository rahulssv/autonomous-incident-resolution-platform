from __future__ import annotations

from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class RequestBodyTooLargeError(Exception):
    """Raised when a streaming request body exceeds the configured API limit."""


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await self._send_too_large_response(scope, receive, send)
            return

        received_body_bytes = 0

        async def receive_with_body_limit() -> Message:
            nonlocal received_body_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    received_body_bytes += len(body)
                if received_body_bytes > self.max_body_bytes:
                    raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, receive_with_body_limit, send)
        except RequestBodyTooLargeError:
            await self._send_too_large_response(scope, receive, send)

    async def _send_too_large_response(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "request_body_too_large",
                    "message": "Request body exceeds the configured API limit.",
                    "details": {"max_body_bytes": self.max_body_bytes},
                }
            },
        )
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    response_headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class RequestCorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = _safe_header_value(headers.get(REQUEST_ID_HEADER))
        correlation_id = _safe_header_value(headers.get(CORRELATION_ID_HEADER))
        if request_id is None:
            request_id = str(uuid4())
        if correlation_id is None:
            correlation_id = request_id

        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["correlation_id"] = correlation_id

        async def send_with_correlation_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
                response_headers[CORRELATION_ID_HEADER] = correlation_id
            await send(message)

        await self.app(scope, receive, send_with_correlation_headers)


def _safe_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:160]


def _content_length(scope: Scope) -> int | None:
    raw_value = Headers(scope=scope).get("content-length")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None

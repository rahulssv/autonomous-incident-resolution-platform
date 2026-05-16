from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx


async def read_with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 2,
    min_backoff_seconds: float = 0.1,
    max_backoff_seconds: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run a read-only MCP-style operation with bounded retry backoff."""

    remaining = max(1, attempts)
    delay = min_backoff_seconds
    while True:
        try:
            return await operation()
        except Exception as exc:
            remaining -= 1
            if remaining <= 0 or not is_retryable_read_error(exc):
                raise
            if delay > 0:
                await sleep(min(delay, max_backoff_seconds))
            delay = min(max(delay * 2, min_backoff_seconds), max_backoff_seconds)


def is_retryable_read_error(exc: Exception) -> bool:
    if is_timeout_error(exc):
        return True
    if isinstance(exc, (ConnectionError, OSError, httpx.ConnectError, httpx.ReadError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException))

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

import redis.asyncio as redis

from airp.core.config import Settings, get_settings


class DedupeStore(Protocol):
    async def claim(self, key: str, ttl_seconds: int) -> bool:
        """Return true only for the first claimant inside the TTL window."""


class RedisDedupeStore:
    def __init__(self, client: redis.Redis | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or redis.from_url(self.settings.redis_url, decode_responses=True)

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        claimed = await self.client.set(f"airp:dedupe:{key}", "1", ex=ttl_seconds, nx=True)
        return bool(claimed)


class InMemoryDedupeStore:
    """Small test/local fallback. It does not implement TTL expiry."""

    def __init__(self, seen: MutableMapping[str, bool] | None = None) -> None:
        self.seen = seen if seen is not None else {}

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        _ = ttl_seconds
        if key in self.seen:
            return False
        self.seen[key] = True
        return True

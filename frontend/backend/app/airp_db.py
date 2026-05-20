from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


def _dsn() -> str | None:
    raw = os.getenv("AIRP_DATABASE_URL")
    if not raw:
        return None
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


async def get_pool() -> asyncpg.Pool | None:
    global _pool
    if _pool is not None:
        return _pool
    dsn = _dsn()
    if not dsn:
        return None
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=10)
    return _pool


def _row_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


EVENT_TO_STAGE = {
    "monitoring.assessed": "monitoring",
    "correlation.completed": "correlation",
    "rca.started": "rca",
    "rca.hypotheses.generated": "rca",
    "rca.hypotheses.persisted": "rca",
    "remediation.planned": "remediation",
    "remediation.plan.persisted": "remediation",
    "documentation.drafted": "documentation",
    "documentation.report.persisted": "documentation",
    "embedding.skipped": "embedding",
    "embedding.records.persisted": "embedding",
}

STAGE_ORDER = ["monitoring", "correlation", "rca", "remediation", "documentation", "embedding"]


async def list_recent_incidents(limit: int = 25) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT i.id, i.title, i.severity, i.status, i.workflow_id,
                   i.created_at, i.updated_at,
                   COALESCE(latest.last_event, i.updated_at) AS last_activity
            FROM incidents i
            LEFT JOIN LATERAL (
                SELECT MAX(created_at) AS last_event
                FROM incident_events
                WHERE incident_id = i.id
            ) latest ON true
            ORDER BY last_activity DESC NULLS LAST, i.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def fetch_incident(incident_id: str) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, title, description, severity, status, workflow_id, created_at, updated_at "
            "FROM incidents WHERE id = $1",
            incident_id,
        )
    return dict(row) if row else None


async def fetch_events(incident_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, producer, created_at, payload "
            "FROM incident_events WHERE incident_id = $1 ORDER BY created_at",
            incident_id,
        )
    return [
        {
            "event_type": r["event_type"],
            "producer": r["producer"],
            "created_at": r["created_at"],
            "payload": _row_payload(r["payload"]),
        }
        for r in rows
    ]


def derive_stage_progress(events: list[dict[str, Any]]) -> tuple[list[str], str | None]:
    completed: list[str] = []
    for evt in events:
        stage = EVENT_TO_STAGE.get(evt["event_type"])
        if stage and stage not in completed:
            completed.append(stage)
    current = None
    for stage in STAGE_ORDER:
        if stage not in completed:
            current = stage
            break
    if current is None:
        current = STAGE_ORDER[-1]
    return completed, current


def latest_artifact(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    for evt in reversed(events):
        if evt["event_type"] == event_type:
            return evt["payload"]
    return None

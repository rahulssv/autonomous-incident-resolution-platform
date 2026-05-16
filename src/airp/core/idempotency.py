from __future__ import annotations

import hashlib
import json
from typing import Any


def build_idempotency_key(
    *,
    scope: str,
    incident_id: str,
    action: str,
    target: str | None = None,
    payload: dict[str, Any] | None = None,
    version: str = "v1",
) -> str:
    material = {
        "version": version,
        "scope": scope,
        "incident_id": incident_id,
        "action": action,
        "target": target,
        "payload": payload or {},
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    return f"airp:{version}:{scope}:{action}:{digest}"


def artifact_idempotency_marker(key: str) -> str:
    return f"<!-- airp-idempotency-key:{key} -->"

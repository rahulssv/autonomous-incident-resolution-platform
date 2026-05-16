from __future__ import annotations

import ssl
from typing import Any

from .config import settings


def httpx_verify() -> bool | ssl.SSLContext:
    if not settings.github_ssl_verify:
        return False
    if not settings.github_use_system_cert_store:
        return True

    try:
        import truststore
    except ImportError:
        return True

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def httpx_client_kwargs() -> dict[str, Any]:
    return {
        "timeout": settings.request_timeout_seconds,
        "verify": httpx_verify(),
        "trust_env": True,
    }

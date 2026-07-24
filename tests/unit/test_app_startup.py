"""Startup guardrail: the API must not boot into a permanently-401 state.

Auth cannot be disabled (core.security.get_current_principal 503s when it is),
so auth_enabled=true with no Entra credentials is unserviceable rather than
degraded — every request 401s and no token can ever be minted.
"""
from __future__ import annotations

import pytest

from airp.core.config import Settings, validate_api_startup_config


def test_rejects_auth_enabled_without_entra_credentials() -> None:
    settings = Settings(_env_file=None, auth_enabled=True)
    with pytest.raises(RuntimeError) as exc_info:
        validate_api_startup_config(settings)
    message = str(exc_info.value)
    assert "AIRP_ENTRA_TENANT_ID" in message
    assert "AIRP_ENTRA_CLIENT_ID" in message


def test_names_only_the_missing_credential() -> None:
    settings = Settings(_env_file=None, auth_enabled=True, entra_tenant_id="tenant-1")
    with pytest.raises(RuntimeError) as exc_info:
        validate_api_startup_config(settings)
    message = str(exc_info.value)
    assert "AIRP_ENTRA_CLIENT_ID" in message
    assert "AIRP_ENTRA_TENANT_ID" not in message


def test_passes_when_entra_credentials_are_present() -> None:
    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        entra_tenant_id="tenant-1",
        entra_client_id="client-1",
    )
    validate_api_startup_config(settings)


def test_skips_the_check_when_auth_is_disabled() -> None:
    """auth_enabled=false is rejected at request time, not startup — see security.py."""
    validate_api_startup_config(Settings(_env_file=None, auth_enabled=False))

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from backend.src.airp.core.config import Settings
from backend.src.airp.core.security import (
    AIRP_ADMIN_ROLE,
    AIRP_VIEWER_ROLE,
    EntraJWTValidator,
    require_roles,
)


class FakeSigningKey:
    def __init__(self, key) -> None:
        self.key = key


class FakeJwksClient:
    def __init__(self, key, *, fail_once: bool = False) -> None:
        self.signing_key = FakeSigningKey(key)
        self.fail_once = fail_once

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        if self.fail_once:
            self.fail_once = False
            raise jwt.PyJWKClientError("missing signing key")
        return self.signing_key


class FakeDiscoveryFetcher:
    def __init__(self, payload: dict | None = None, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float) -> dict:
        self.calls.append((url, timeout))
        if self.fail:
            raise OSError("discovery unavailable")
        return self.payload or {}


def test_entra_validator_accepts_valid_signed_token() -> None:
    validator, token = _validator_and_token()

    principal = validator.validate(token)

    assert principal.subject == "user-123"
    assert principal.tenant_id == "tenant-123"
    assert principal.roles == [AIRP_VIEWER_ROLE]


def test_entra_validator_discovers_openid_configuration_once_when_cache_is_fresh() -> None:
    validator, token, discovery, _ = _validator_and_token(with_discovery=True)

    validator.validate(token)
    validator.validate(token)

    assert len(discovery.calls) == 1
    assert discovery.calls[0][0].endswith("/.well-known/openid-configuration")


def test_entra_validator_discovery_failure_returns_service_unavailable() -> None:
    validator, token = _validator_and_token(discovery_failure=True)

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Microsoft Entra ID discovery failed"


def test_entra_validator_refreshes_discovery_and_jwks_after_key_lookup_failure() -> None:
    validator, token, discovery, factory_calls = _validator_and_token(
        with_discovery=True,
        fail_first_jwks_lookup=True,
    )

    principal = validator.validate(token)

    assert principal.subject == "user-123"
    assert len(discovery.calls) == 2
    assert factory_calls == [
        "https://login.microsoftonline.com/tenant-123/discovery/v2.0/keys",
        "https://login.microsoftonline.com/tenant-123/discovery/v2.0/keys",
    ]


def test_entra_validator_rejects_expired_token() -> None:
    validator, token = _validator_and_token(expired=True)

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired access token"


def test_entra_validator_rejects_wrong_audience() -> None:
    validator, token = _validator_and_token(audience="api://wrong-audience")

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired access token"


def test_entra_validator_rejects_wrong_issuer() -> None:
    validator, token = _validator_and_token(issuer="https://issuer.example.test")

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Access token issuer is not allowed"


def test_entra_validator_rejects_wrong_tenant() -> None:
    validator, token = _validator_and_token(tenant_id="tenant-other")

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Access token tenant is not allowed"


def test_entra_validator_requires_nbf_claim() -> None:
    validator, token = _validator_and_token(omit_claims={"nbf"})

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired access token"


def test_entra_validator_requires_subject_claim() -> None:
    validator, token = _validator_and_token(omit_claims={"sub", "oid"})

    with pytest.raises(HTTPException) as exc:
        validator.validate(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Access token is missing a subject claim"


@pytest.mark.asyncio
async def test_valid_viewer_token_fails_admin_role_dependency() -> None:
    validator, token = _validator_and_token()
    principal = validator.validate(token)
    dependency = require_roles(AIRP_ADMIN_ROLE)

    with pytest.raises(HTTPException) as exc:
        await dependency(principal)

    assert exc.value.status_code == 403


def _validator_and_token(
    *,
    audience: str | None = None,
    discovery_failure: bool = False,
    expired: bool = False,
    fail_first_jwks_lookup: bool = False,
    issuer: str | None = None,
    tenant_id: str = "tenant-123",
    omit_claims: set[str] | None = None,
    with_discovery: bool = False,
):
    settings = Settings(
        entra_tenant_id="tenant-123",
        entra_client_id="api://airp-test",
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    claims = {
        "iss": issuer or settings.entra_issuer,
        "aud": audience or settings.entra_client_id,
        "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=5),
        "iat": now - timedelta(minutes=2),
        "nbf": now - timedelta(minutes=2),
        "sub": "user-123",
        "tid": tenant_id,
        "roles": [AIRP_VIEWER_ROLE],
    }
    for claim in omit_claims or set():
        claims.pop(claim, None)

    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
    discovery = FakeDiscoveryFetcher(
        {
            "issuer": settings.entra_issuer,
            "jwks_uri": "https://login.microsoftonline.com/tenant-123/discovery/v2.0/keys",
        },
        fail=discovery_failure,
    )
    factory_calls = []

    def jwks_client_factory(jwks_uri: str) -> FakeJwksClient:
        factory_calls.append(jwks_uri)
        return FakeJwksClient(
            key.public_key(),
            fail_once=fail_first_jwks_lookup and len(factory_calls) == 1,
        )

    validator = EntraJWTValidator(
        settings,
        discovery_fetcher=discovery,
        jwks_client_factory=jwks_client_factory,
    )
    if with_discovery:
        return validator, token, discovery, factory_calls
    return validator, token

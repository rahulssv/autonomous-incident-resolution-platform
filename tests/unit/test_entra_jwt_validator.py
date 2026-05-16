from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from airp.core.config import Settings
from airp.core.security import (
    AIRP_ADMIN_ROLE,
    AIRP_VIEWER_ROLE,
    EntraJWTValidator,
    require_roles,
)


class FakeSigningKey:
    def __init__(self, key) -> None:
        self.key = key


class FakeJwksClient:
    def __init__(self, key) -> None:
        self.signing_key = FakeSigningKey(key)

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        return self.signing_key


def test_entra_validator_accepts_valid_signed_token() -> None:
    validator, token = _validator_and_token()

    principal = validator.validate(token)

    assert principal.subject == "user-123"
    assert principal.tenant_id == "tenant-123"
    assert principal.roles == [AIRP_VIEWER_ROLE]


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
    expired: bool = False,
    issuer: str | None = None,
    tenant_id: str = "tenant-123",
    omit_claims: set[str] | None = None,
) -> tuple[EntraJWTValidator, str]:
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
    validator = EntraJWTValidator(settings)
    validator.jwks_client = FakeJwksClient(key.public_key())
    return validator, token

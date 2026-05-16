import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any
from urllib.request import urlopen

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from airp.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)

AIRP_ADMIN_ROLE = "AIRP.Admin"
AIRP_SRE_ROLE = "AIRP.SRE"
AIRP_VIEWER_ROLE = "AIRP.Viewer"
AIRP_APPROVER_ROLE = "AIRP.Approver"
AIRP_READ_ROLES = (
    AIRP_ADMIN_ROLE,
    AIRP_SRE_ROLE,
    AIRP_VIEWER_ROLE,
    AIRP_APPROVER_ROLE,
)
AIRP_SRE_ROLES = (AIRP_ADMIN_ROLE, AIRP_SRE_ROLE)
AIRP_APPROVER_ROLES = (AIRP_ADMIN_ROLE, AIRP_APPROVER_ROLE)


@dataclass(frozen=True)
class EntraDiscoveryMetadata:
    issuer: str
    jwks_uri: str
    fetched_at: datetime


class Principal(BaseModel):
    """Authenticated Microsoft Entra ID caller."""

    subject: str
    tenant_id: str | None = None
    name: str | None = None
    username: str | None = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    claims: dict

    def has_any_role(self, allowed_roles: set[str]) -> bool:
        return bool(set(self.roles).intersection(allowed_roles))


class EntraJWTValidator:
    def __init__(
        self,
        settings: Settings,
        *,
        discovery_fetcher: Callable[[str, float], dict[str, Any]] | None = None,
        jwks_client_factory: Callable[[str], PyJWKClient] = PyJWKClient,
    ) -> None:
        self.settings = settings
        self.discovery_fetcher = discovery_fetcher or _fetch_openid_configuration
        self.jwks_client_factory = jwks_client_factory
        self.discovery_metadata: EntraDiscoveryMetadata | None = None
        self.jwks_client: PyJWKClient | None = None

    def validate(self, token: str) -> Principal:
        if not self.settings.entra_client_id or not self.settings.entra_issuer:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Microsoft Entra ID authentication is not configured",
            )

        metadata = self._get_discovery_metadata()
        jwks_client = self._get_jwks_client(metadata)
        try:
            signing_key = self._get_signing_key(token, jwks_client)
            allowed_issuers = self.settings.entra_allowed_issuers or [metadata.issuer]
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.settings.entra_client_id,
                options={"require": ["exp", "iat", "nbf"], "verify_iss": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if claims.get("iss") not in allowed_issuers:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token issuer is not allowed",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if claims.get("tid") != self.settings.entra_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token tenant is not allowed",
                headers={"WWW-Authenticate": "Bearer"},
            )

        expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
        if expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        subject = claims.get("sub") or claims.get("oid")
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token is missing a subject claim",
                headers={"WWW-Authenticate": "Bearer"},
            )

        scopes = claims.get("scp", "")
        return Principal(
            subject=subject,
            tenant_id=claims.get("tid"),
            name=claims.get("name"),
            username=claims.get("preferred_username") or claims.get("upn"),
            roles=list(claims.get("roles", [])),
            scopes=scopes.split() if isinstance(scopes, str) else list(scopes or []),
            claims=claims,
        )

    def _get_signing_key(self, token: str, jwks_client: PyJWKClient):
        try:
            return jwks_client.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError:
            metadata = self._get_discovery_metadata(force_refresh=True)
            jwks_client = self._get_jwks_client(metadata, force_refresh=True)
            return jwks_client.get_signing_key_from_jwt(token)

    def _get_discovery_metadata(self, *, force_refresh: bool = False) -> EntraDiscoveryMetadata:
        if (
            not force_refresh
            and self.discovery_metadata is not None
            and self.discovery_metadata.fetched_at
            + timedelta(seconds=self.settings.entra_discovery_cache_ttl_seconds)
            > datetime.now(UTC)
        ):
            return self.discovery_metadata

        discovery_url = f"{self.settings.entra_issuer}/.well-known/openid-configuration"
        try:
            payload = self.discovery_fetcher(
                discovery_url,
                self.settings.entra_discovery_timeout_seconds,
            )
            issuer = payload["issuer"]
            jwks_uri = payload["jwks_uri"]
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Microsoft Entra ID discovery failed",
            ) from exc

        self.discovery_metadata = EntraDiscoveryMetadata(
            issuer=str(issuer),
            jwks_uri=str(jwks_uri),
            fetched_at=datetime.now(UTC),
        )
        self.jwks_client = None
        return self.discovery_metadata

    def _get_jwks_client(
        self, metadata: EntraDiscoveryMetadata, *, force_refresh: bool = False
    ) -> PyJWKClient:
        if self.jwks_client is None or force_refresh:
            self.jwks_client = self.jwks_client_factory(metadata.jwks_uri)
        return self.jwks_client


def _fetch_openid_configuration(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@lru_cache
def get_entra_validator() -> EntraJWTValidator:
    return EntraJWTValidator(get_settings())


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    validator: Annotated[EntraJWTValidator, Depends(get_entra_validator)],
) -> Principal:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication must remain enabled for this product",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validator.validate(credentials.credentials)


def require_roles(*roles: str):
    allowed_roles = set(roles)

    async def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if allowed_roles and not principal.has_any_role(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency

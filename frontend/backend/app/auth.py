from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
import traceback
from typing import Any
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .config import settings
from .github_client import GitHubClient
from .github_service import get_viewer
from .http_client import httpx_client_kwargs


router = APIRouter()
logger = logging.getLogger(__name__)
_LOG_PATH = Path(__file__).resolve().parents[1] / "oauth-debug.log"

_STATE_COOKIE = "air_oauth_state"
_STATE_TTL_SECONDS = 600
_oauth_states: dict[str, dict[str, Any]] = {}
_sessions: dict[str, dict[str, Any]] = {}


def token_from_request(request: Request) -> str | None:
    session = current_session(request)
    if not session:
        return None
    return session.get("accessToken")


def current_session(request: Request) -> dict[str, Any] | None:
    cookie_value = request.cookies.get(settings.session_cookie_name)
    session_id = _unsign(cookie_value)
    if not session_id:
        return None

    session = _sessions.get(session_id)
    if not session:
        return None

    now = time.time()
    if now - session["createdAtEpoch"] > settings.session_ttl_seconds:
        _sessions.pop(session_id, None)
        return None
    return session


@router.get("/github/login")
async def github_login(
    return_to: str | None = Query(default=None, description="Frontend URL to return to after login.")
):
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        return JSONResponse(
            status_code=500,
            content={
                "error": "GitHub OAuth is not configured.",
                "required": [
                    "GITHUB_OAUTH_CLIENT_ID",
                    "GITHUB_OAUTH_CLIENT_SECRET",
                    "GITHUB_OAUTH_REDIRECT_URI",
                ],
            },
        )

    _cleanup_expired()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "createdAtEpoch": time.time(),
        "returnTo": _safe_return_to(return_to),
    }

    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": " ".join(settings.github_oauth_scopes),
        "state": state,
        "allow_signup": "true",
    }
    response = RedirectResponse(
        f"https://github.com/login/oauth/authorize?{urlencode(params)}",
        status_code=302,
    )
    _set_cookie(response, _STATE_COOKIE, _sign(state), max_age=_STATE_TTL_SECONDS)
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    try:
        return await _handle_github_callback(
            request=request,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
    except Exception as exc:
        _log_oauth_exception("Unhandled GitHub OAuth callback failure", exc)
        return _frontend_redirect(
            auth="error",
            message=f"GitHub sign-in failed in backend callback: {type(exc).__name__}. Check backend/oauth-debug.log.",
        )


async def _handle_github_callback(
    request: Request,
    code: str | None,
    state: str | None,
    error: str | None,
    error_description: str | None,
):
    if error:
        return _frontend_redirect(auth="error", message=error_description or error)

    cookie_state = _unsign(request.cookies.get(_STATE_COOKIE))
    state_record = _oauth_states.pop(state or "", None)
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        return _frontend_redirect(auth="error", message="Invalid OAuth state.")
    if not state_record or time.time() - state_record["createdAtEpoch"] > _STATE_TTL_SECONDS:
        return _frontend_redirect(auth="error", message="OAuth state expired.")
    if not code:
        return _frontend_redirect(auth="error", message="Missing OAuth code.")

    try:
        token_data = await _exchange_code_for_token(code)
    except RuntimeError as exc:
        _log_oauth_exception("GitHub OAuth token exchange failed", exc)
        return _frontend_redirect(auth="error", message=str(exc))

    access_token = token_data.get("access_token")
    if not access_token:
        return _frontend_redirect(auth="error", message="GitHub did not return an access token.")

    try:
        viewer = await get_viewer(GitHubClient(settings, token=access_token))
    except Exception as exc:
        _log_oauth_exception("GitHub profile read failed after OAuth token exchange", exc)
        return _frontend_redirect(
            auth="error",
            message=f"GitHub login succeeded, but reading the user profile failed: {type(exc).__name__}. Check backend/oauth-debug.log.",
        )
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        "accessToken": access_token,
        "scope": token_data.get("scope", ""),
        "tokenType": token_data.get("token_type", "bearer"),
        "createdAtEpoch": time.time(),
        "createdAt": _iso_now(),
        "user": viewer,
    }

    response = RedirectResponse(
        _append_query(state_record["returnTo"], {"auth": "success"}),
        status_code=302,
    )
    _set_cookie(
        response,
        settings.session_cookie_name,
        _sign(session_id),
        max_age=settings.session_ttl_seconds,
    )
    response.delete_cookie(_STATE_COOKIE, path="/")
    return response


@router.get("/me")
async def auth_me(request: Request) -> dict[str, Any]:
    session = current_session(request)
    if not session:
        return {
            "authenticated": False,
            "oauthConfigured": bool(
                settings.github_oauth_client_id and settings.github_oauth_client_secret
            ),
        }

    org_refresh_error = None
    try:
        session["user"] = await get_viewer(
            GitHubClient(settings, token=session["accessToken"])
        )
    except Exception as exc:
        org_refresh_error = f"{type(exc).__name__}: {exc}"
        _log_oauth_exception("Could not refresh GitHub organizations for auth session", exc)

    return {
        "authenticated": True,
        "oauthConfigured": True,
        "user": session["user"],
        "session": {
            "scope": session.get("scope", ""),
            "configuredScopes": settings.github_oauth_scopes,
            "createdAt": session["createdAt"],
            "expiresInSeconds": max(
                settings.session_ttl_seconds - int(time.time() - session["createdAtEpoch"]),
                0,
            ),
            "organizationCount": len((session.get("user") or {}).get("organizations") or []),
            "organizationRefreshError": org_refresh_error,
        },
    }


@router.get("/org-debug")
async def org_debug(request: Request) -> dict[str, Any]:
    session = current_session(request)
    if not session:
        return {
            "authenticated": False,
            "oauthConfigured": bool(
                settings.github_oauth_client_id and settings.github_oauth_client_secret
            ),
        }

    client = GitHubClient(settings, token=session["accessToken"])
    diagnostics: dict[str, Any] = {
        "authenticated": True,
        "sessionScope": session.get("scope", ""),
        "configuredScopes": settings.github_oauth_scopes,
        "storedOrganizationCount": len((session.get("user") or {}).get("organizations") or []),
        "checks": {},
    }

    diagnostics["checks"]["viewer"] = await _safe_github_check(lambda: get_viewer(client))
    diagnostics["checks"]["user_orgs"] = await _safe_github_check(
        lambda: client.rest("GET", "/user/orgs", {"per_page": 100})
    )
    diagnostics["checks"]["user_memberships"] = await _safe_github_check(
        lambda: client.rest(
            "GET", "/user/memberships/orgs", {"per_page": 100, "state": "active"}
        )
    )
    diagnostics["checks"]["user_installations"] = await _safe_github_check(
        lambda: client.rest("GET", "/user/installations", {"per_page": 100})
    )
    return diagnostics


@router.post("/logout")
async def logout(request: Request):
    session_id = _unsign(request.cookies.get(settings.session_cookie_name))
    if session_id:
        _sessions.pop(session_id, None)

    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


async def _exchange_code_for_token(code: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(**httpx_client_kwargs()) as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "air-platform-dashboard",
                },
                data={
                    "client_id": settings.github_oauth_client_id,
                    "client_secret": settings.github_oauth_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_oauth_redirect_uri,
                },
            )
    except httpx.HTTPError as exc:
        detail = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in detail:
            raise RuntimeError(
                "Python could not verify GitHub's TLS certificate. The backend is configured to use the Windows certificate store; restart the backend and retry. If this persists, check corporate proxy/root CA settings."
            ) from exc
        raise RuntimeError(f"Could not reach GitHub OAuth token endpoint: {type(exc).__name__}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("GitHub returned an invalid OAuth token response.") from exc
    if response.is_error or data.get("error"):
        message = data.get("error_description") or data.get("error") or "OAuth token exchange failed."
        raise RuntimeError(message)
    return data


async def _safe_github_check(callable_factory):
    try:
        data = await callable_factory()
    except Exception as exc:
        return {
            "ok": False,
            "errorType": type(exc).__name__,
            "message": str(exc),
        }

    if isinstance(data, list):
        return {
            "ok": True,
            "count": len(data),
            "items": [_sanitize_org_item(item) for item in data],
        }
    if isinstance(data, dict) and "organizations" in data:
        return {
            "ok": True,
            "count": len(data.get("organizations") or []),
            "items": data.get("organizations") or [],
        }
    if isinstance(data, dict) and "installations" in data:
        return {
            "ok": True,
            "count": len(data.get("installations") or []),
            "items": [_sanitize_installation_item(item) for item in data.get("installations") or []],
        }
    return {"ok": True, "data": data}


def _sanitize_org_item(item: dict[str, Any]) -> dict[str, Any]:
    organization = item.get("organization") if isinstance(item, dict) else None
    source = organization or item
    return {
        "login": source.get("login"),
        "name": source.get("name"),
        "url": source.get("html_url") or source.get("url"),
        "role": item.get("role") if isinstance(item, dict) else None,
        "state": item.get("state") if isinstance(item, dict) else None,
    }


def _sanitize_installation_item(item: dict[str, Any]) -> dict[str, Any]:
    account = item.get("account") or {}
    return {
        "id": item.get("id"),
        "accountLogin": account.get("login"),
        "accountType": account.get("type"),
        "targetType": item.get("target_type"),
        "repositorySelection": item.get("repository_selection"),
        "appSlug": item.get("app_slug"),
        "permissions": item.get("permissions"),
        "suspendedAt": item.get("suspended_at"),
    }


def _log_oauth_exception(message: str, exc: BaseException) -> None:
    logger.exception(message)
    safe_text = (
        f"\n[{_iso_now()}] {message}\n"
        f"{type(exc).__name__}: {exc}\n"
        f"{traceback.format_exc()}\n"
    )
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(safe_text)
    except OSError:
        logger.exception("Could not write OAuth debug log")


def _cleanup_expired() -> None:
    now = time.time()
    for state, record in list(_oauth_states.items()):
        if now - record["createdAtEpoch"] > _STATE_TTL_SECONDS:
            _oauth_states.pop(state, None)
    for session_id, session in list(_sessions.items()):
        if now - session["createdAtEpoch"] > settings.session_ttl_seconds:
            _sessions.pop(session_id, None)


def _safe_return_to(return_to: str | None) -> str:
    if not return_to:
        return settings.frontend_url
    parsed_return = urlparse(return_to)
    parsed_frontend = urlparse(settings.frontend_url)
    if (
        parsed_return.scheme in {"http", "https"}
        and parsed_return.scheme == parsed_frontend.scheme
        and parsed_return.netloc == parsed_frontend.netloc
    ):
        return return_to
    return settings.frontend_url


def _frontend_redirect(auth: str, message: str) -> RedirectResponse:
    return RedirectResponse(
        _append_query(settings.frontend_url, {"auth": auth, "message": message}),
        status_code=302,
    )


def _append_query(url: str, values: dict[str, str]) -> str:
    parsed = urlparse(url)
    separator = "&" if parsed.query else "?"
    return f"{url}{separator}{urlencode(values)}"


def _set_cookie(response: RedirectResponse | JSONResponse, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _sign(value: str) -> str:
    signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{value}.{encoded}"


def _unsign(value: str | None) -> str | None:
    if not value or "." not in value:
        return None
    raw, signature = value.rsplit(".", 1)
    if hmac.compare_digest(_sign(raw), value):
        return raw
    return None


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

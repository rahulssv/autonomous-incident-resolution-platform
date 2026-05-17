from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _csv_env(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _secret_env(name: str, default: str | None = None) -> str | None:
    value = (os.getenv(name) or default or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered.startswith("your_") or lowered.startswith("replace_"):
        return None
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AIR GitHub API")
    github_token: str | None = _secret_env("GITHUB_TOKEN") or _secret_env("GH_TOKEN")
    github_default_org: str | None = os.getenv("GITHUB_DEFAULT_ORG")
    github_base_url: str = os.getenv("GITHUB_BASE_URL", "https://api.github.com").rstrip("/")
    github_graphql_url: str = os.getenv(
        "GITHUB_GRAPHQL_URL", "https://api.github.com/graphql"
    )
    github_use_system_cert_store: bool = (
        os.getenv("GITHUB_USE_SYSTEM_CERT_STORE", "true").lower() == "true"
    )
    github_ssl_verify: bool = os.getenv("GITHUB_SSL_VERIFY", "true").lower() == "true"
    github_oauth_client_id: str | None = _secret_env("GITHUB_OAUTH_CLIENT_ID")
    github_oauth_client_secret: str | None = _secret_env("GITHUB_OAUTH_CLIENT_SECRET")
    github_oauth_redirect_uri: str = os.getenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "http://127.0.0.1:8000/api/auth/github/callback",
    )
    github_oauth_scopes: list[str] = field(
        default_factory=lambda: _csv_env(
            "GITHUB_OAUTH_SCOPES", "read:user,user:email,read:org,repo"
        )
    )
    github_api_version: str = os.getenv("GITHUB_API_VERSION", "2026-03-10")
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    frontend_url: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
    session_secret: str = os.getenv(
        "SESSION_SECRET", "dev-only-change-this-session-secret"
    )
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "air_session")
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    cors_origins: list[str] = field(
        default_factory=lambda: _csv_env(
            "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        )
    )
    issue_label_filter: list[str] = field(
        default_factory=lambda: _csv_env("GITHUB_ISSUE_LABEL_FILTER", "")
    )
    automation_bot_login: str = os.getenv(
        "GITHUB_AUTOMATION_BOT_LOGIN", "airp-automation-bot"
    ).strip()
    agent_pr_label_filter: list[str] = field(
        default_factory=lambda: _csv_env(
            "GITHUB_AGENT_PR_LABEL_FILTER", "agentic-remediation,ai-remediation"
        )
    )
    airp_api_base_url: str = os.getenv("AIRP_API_BASE_URL", "http://api:8080").rstrip("/")
    airp_service_token: str | None = _secret_env("AIRP_SERVICE_TOKEN")
    airp_backend_enabled: bool = os.getenv("AIRP_BACKEND_ENABLED", "false").lower() == "true"
    airp_request_timeout_seconds: float = float(
        os.getenv("AIRP_REQUEST_TIMEOUT_SECONDS", "10")
    )
    airp_stream_poll_interval_seconds: float = float(
        os.getenv("AIRP_STREAM_POLL_INTERVAL_SECONDS", "2.0")
    )
    airp_stream_poll_max_iterations: int = int(
        os.getenv("AIRP_STREAM_POLL_MAX_ITERATIONS", "150")
    )


settings = Settings()

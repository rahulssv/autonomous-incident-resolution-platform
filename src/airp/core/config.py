import json
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AIRP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AIRP Backend API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    allowed_origins: list[str] = Field(default_factory=list)
    api_max_request_body_bytes: int = Field(default=1_048_576, ge=1024)

    database_url: str = "postgresql+asyncpg://airp:airp@localhost:5432/airp"
    redis_url: str = "redis://localhost:6379/0"

    auth_enabled: bool = True
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_allowed_issuers: list[str] = Field(default_factory=list)
    entra_discovery_cache_ttl_seconds: int = Field(default=3600, ge=60)
    entra_discovery_timeout_seconds: float = Field(default=5.0, gt=0.0)

    gateway_base_url: AnyHttpUrl | None = None
    gateway_api_key: str | None = None
    gateway_max_retries: int = Field(default=0, ge=0, le=5)
    llm_monitoring_model: str = "gpt-4.1-nano"
    llm_correlation_model: str = "gpt-4.1"
    llm_rca_model: str = "gpt-5.2-CIO"
    llm_remediation_model: str = "gpt-5.2-CIO"
    llm_documentation_model: str = "gpt-4.1"
    llm_embedding_model: str = "embeddings"
    embedding_enabled: bool = True
    embedding_max_texts: int = Field(default=16, ge=1, le=50)
    embedding_text_max_chars: int = Field(default=750, ge=100, le=12_000)
    embedding_total_max_chars: int = Field(default=3_000, ge=100, le=50_000)
    embedding_rate_limit_cooldown_seconds: int = Field(default=120, ge=0, le=3_600)
    agent_read_only_evidence_enabled: bool = False
    rca_min_hypothesis_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    kubernetes_mcp_transport: Literal["disabled", "mcp"] = "disabled"
    kubernetes_mcp_url: AnyHttpUrl | None = None
    kubernetes_mcp_namespace_allowlist: list[str] = Field(default_factory=list)
    kubernetes_mcp_read_timeout_seconds: float = Field(default=20.0, gt=0.0)
    github_mcp_transport: Literal["disabled", "mcp"] = "disabled"
    github_mcp_url: AnyHttpUrl | None = None
    github_mcp_repository_allowlist: list[str] = Field(
        default_factory=lambda: ["AIRP-client/*"]
    )
    github_mcp_read_timeout_seconds: float = Field(default=20.0, gt=0.0)
    dockerhub_base_url: AnyHttpUrl = "https://hub.docker.com/v2"
    dockerhub_read_timeout_seconds: float = Field(default=20.0, gt=0.0)
    mcp_read_retry_attempts: int = Field(default=2, ge=1, le=5)
    mcp_read_retry_min_backoff_seconds: float = Field(default=0.1, ge=0.0)
    mcp_read_retry_max_backoff_seconds: float = Field(default=1.0, ge=0.0)
    readiness_active_checks_enabled: bool = False
    readiness_probe_timeout_seconds: float = Field(default=2.0, gt=0.0)
    github_issue_creation_enabled: bool = False
    slack_notifications_enabled: bool = False
    slack_webhook_url: AnyHttpUrl | None = None
    slack_default_channel: str = "#airp-alerts"
    slack_signing_secret: str | None = None
    remediation_pr_creation_enabled: bool = False
    documentation_publishing_enabled: bool = False

    client_github_org: str = "AIRP-client"
    azure_subscription_id: str = "568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa"
    azure_resource_group: str = "Semicolon-AIRP-rg"
    azure_aks_cluster_name: str = "AIRP-cluster-high-per"

    kafka_bootstrap_servers: str | None = None
    kafka_security_protocol: str = "SASL_SSL"
    kafka_sasl_mechanism: str = "PLAIN"
    kafka_username: str = "$ConnectionString"
    kafka_password: str | None = None
    kafka_alerts_raw_topic: str = "airp.alerts.raw"
    kafka_incidents_validated_topic: str = "airp.incidents.validated"
    kafka_deadletter_topic: str = "airp.deadletter"
    kafka_alert_consumer_group: str = "airp-alert-consumer"
    kafka_auto_offset_reset: Literal["earliest", "latest"] = "earliest"
    kafka_consumer_poll_timeout_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    kafka_consumer_idle_log_seconds: int = Field(default=30, ge=0, le=3600)
    kafka_consumer_session_timeout_ms: int = Field(default=30_000, ge=6_000, le=300_000)
    kafka_consumer_heartbeat_interval_ms: int = Field(default=10_000, ge=1_000, le=60_000)
    kafka_consumer_max_poll_interval_ms: int = Field(default=300_000, ge=30_000, le=3_600_000)
    alert_dedupe_ttl_seconds: int = 3600

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "airp-incident-workflows"
    temporal_tls: bool = False
    temporal_start_workflows: bool = True
    temporal_worker_max_concurrent_workflow_tasks: int = Field(default=2, ge=1, le=100)
    temporal_worker_max_concurrent_activities: int = Field(default=2, ge=1, le=100)
    temporal_worker_max_workflow_task_polls: int = Field(default=2, ge=2, le=20)
    temporal_worker_max_activity_task_polls: int = Field(default=1, ge=1, le=20)
    temporal_worker_max_activities_per_second: float = Field(default=1.0, gt=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_production_guardrails(self) -> "Settings":
        if self.environment != "production":
            return self

        errors: list[str] = []
        if not self.auth_enabled:
            errors.append("AIRP_AUTH_ENABLED must be true in production")
        if not self.entra_tenant_id:
            errors.append("AIRP_ENTRA_TENANT_ID is required in production")
        if not self.entra_client_id:
            errors.append("AIRP_ENTRA_CLIENT_ID is required in production")
        for origin in self.allowed_origins:
            if not _is_explicit_https_origin(origin):
                errors.append(
                    "AIRP_ALLOWED_ORIGINS must contain only explicit HTTPS origins "
                    f"in production: {origin!r}"
                )
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            return f"/{value}"
        return value.rstrip("/") or "/api"

    @field_validator(
        "gateway_base_url",
        "kubernetes_mcp_url",
        "github_mcp_url",
        "slack_webhook_url",
        mode="before",
    )
    @classmethod
    def empty_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator(
        "allowed_origins",
        "kubernetes_mcp_namespace_allowlist",
        "github_mcp_repository_allowlist",
        mode="before",
    )
    @classmethod
    def normalize_allowlist(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def entra_issuer(self) -> str | None:
        if not self.entra_tenant_id:
            return None
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/v2.0"

    @property
    def entra_jwks_url(self) -> str | None:
        issuer = self.entra_issuer
        if not issuer:
            return None
        return f"{issuer}/discovery/v2.0/keys"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _is_explicit_https_origin(value: str) -> bool:
    stripped = value.strip()
    if not stripped or "*" in stripped:
        return False
    parsed = urlparse(stripped)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )

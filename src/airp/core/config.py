from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
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

    database_url: str = "postgresql+asyncpg://airp:airp@localhost:5432/airp"
    redis_url: str = "redis://localhost:6379/0"

    auth_enabled: bool = True
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_allowed_issuers: list[str] = Field(default_factory=list)

    gateway_base_url: AnyHttpUrl | None = None
    gateway_api_key: str | None = None
    llm_monitoring_model: str = "gpt-4.1-nano"
    llm_correlation_model: str = "gpt-4.1"
    llm_rca_model: str = "gpt-5.2-CIO"
    llm_remediation_model: str = "gpt-5.2-CIO"
    llm_documentation_model: str = "gpt-4.1"
    llm_embedding_model: str = "embeddings"

    client_github_org: str = "AIRP-client"
    azure_subscription_id: str = "568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa"
    azure_resource_group: str = "Semicolon-AIRP-rg"
    azure_aks_cluster_name: str = "AIRP-cluster-high-per"

    kafka_bootstrap_servers: str | None = None
    kafka_security_protocol: str = "SASL_SSL"
    kafka_sasl_mechanism: str = "PLAIN"
    kafka_username: str = "$ConnectionString"
    kafka_password: str | None = None

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            return f"/{value}"
        return value.rstrip("/") or "/api"

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

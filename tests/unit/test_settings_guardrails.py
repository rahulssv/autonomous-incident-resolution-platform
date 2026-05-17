import pytest
from pydantic import ValidationError

from backend.src.airp.core.config import Settings


def test_production_settings_accept_valid_auth_and_https_cors() -> None:
    settings = Settings(
        environment="production",
        auth_enabled=True,
        entra_tenant_id="tenant-123",
        entra_client_id="api://airp",
        allowed_origins=["https://airp.example.com", "https://ops.example.com:8443"],
    )

    assert settings.environment == "production"
    assert settings.allowed_origins == [
        "https://airp.example.com",
        "https://ops.example.com:8443",
    ]


def test_production_settings_fail_when_auth_is_disabled() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            environment="production",
            auth_enabled=False,
            entra_tenant_id="tenant-123",
            entra_client_id="api://airp",
        )

    assert "AIRP_AUTH_ENABLED must be true in production" in str(exc.value)


def test_production_settings_fail_when_entra_config_is_missing() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(environment="production")

    message = str(exc.value)
    assert "AIRP_ENTRA_TENANT_ID is required in production" in message
    assert "AIRP_ENTRA_CLIENT_ID is required in production" in message


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "http://airp.example.com",
        "https://airp.example.com/path",
        "https://airp.example.com?debug=true",
        "null",
    ],
)
def test_production_settings_fail_for_unsafe_cors_origins(origin: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            environment="production",
            auth_enabled=True,
            entra_tenant_id="tenant-123",
            entra_client_id="api://airp",
            allowed_origins=[origin],
        )

    assert "AIRP_ALLOWED_ORIGINS must contain only explicit HTTPS origins" in str(
        exc.value
    )


def test_allowed_origins_accept_comma_separated_environment_style_value() -> None:
    settings = Settings(
        environment="production",
        auth_enabled=True,
        entra_tenant_id="tenant-123",
        entra_client_id="api://airp",
        allowed_origins="https://airp.example.com,https://ops.example.com",
    )

    assert settings.allowed_origins == [
        "https://airp.example.com",
        "https://ops.example.com",
    ]


def test_temporal_worker_concurrency_defaults_are_bounded() -> None:
    settings = Settings()

    assert settings.temporal_workflow_task_timeout_seconds == 60
    assert settings.temporal_worker_max_concurrent_workflow_tasks == 2
    assert settings.temporal_worker_max_concurrent_activities == 1
    assert settings.temporal_worker_max_workflow_task_polls == 2
    assert settings.temporal_worker_max_activity_task_polls == 1
    assert settings.temporal_worker_max_activities_per_second == 0.5
    assert settings.temporal_worker_activity_executor_threads == 2


def test_anthropic_airp_environment_names_are_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIRP_ANTHROPIC_BASE_URL", "https://anthropic.example.test/v1")
    monkeypatch.setenv("AIRP_ANTHROPIC_AUTH_TOKEN", "test-token")

    settings = Settings(_env_file=None)

    assert str(settings.anthropic_base_url).startswith(
        "https://anthropic.example.test/v1"
    )
    assert settings.anthropic_auth_token == "test-token"


def test_anthropic_airp_dotenv_names_are_supported(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AIRP_ANTHROPIC_BASE_URL=https://anthropic.example.test/v1",
                "AIRP_ANTHROPIC_AUTH_TOKEN=test-token",
            ]
        )
    )

    settings = Settings(_env_file=env_file)

    assert str(settings.anthropic_base_url).startswith(
        "https://anthropic.example.test/v1"
    )
    assert settings.anthropic_auth_token == "test-token"

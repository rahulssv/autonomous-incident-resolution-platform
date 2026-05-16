import pytest

from airp.core.config import Settings
from airp.core.errors import AppError
from airp.messaging.eventhub_kafka import kafka_config


def test_kafka_config_uses_event_hubs_sasl_settings() -> None:
    settings = Settings(
        kafka_bootstrap_servers="airp.servicebus.windows.net:9093",
        kafka_password="Endpoint=sb://airp.servicebus.windows.net/;SharedAccessKeyName=Root;",
    )

    config = kafka_config(settings)

    assert config["bootstrap.servers"] == "airp.servicebus.windows.net:9093"
    assert config["security.protocol"] == "SASL_SSL"
    assert config["sasl.mechanism"] == "PLAIN"
    assert config["sasl.username"] == "$ConnectionString"
    assert config["sasl.password"].startswith("Endpoint=sb://")


def test_kafka_config_requires_credentials() -> None:
    settings = Settings(kafka_bootstrap_servers=None, kafka_password=None)

    with pytest.raises(AppError):
        kafka_config(settings)

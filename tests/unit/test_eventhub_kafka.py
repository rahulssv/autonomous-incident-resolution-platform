import pytest

from backend.src.airp.core.config import Settings
from backend.src.airp.core.errors import AppError
from backend.src.airp.messaging.eventhub_kafka import build_consumer, kafka_config


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


def test_build_consumer_uses_long_running_event_hubs_settings(monkeypatch) -> None:
    class FakeConsumer:
        def __init__(self, config):
            self.config = config
            self.subscription = None

        def subscribe(self, topics, on_assign=None, on_revoke=None):
            self.subscription = {
                "topics": topics,
                "on_assign": on_assign,
                "on_revoke": on_revoke,
            }

    monkeypatch.setattr("airp.messaging.eventhub_kafka.Consumer", FakeConsumer)
    settings = Settings(
        kafka_bootstrap_servers="airp.servicebus.windows.net:9093",
        kafka_password="Endpoint=sb://airp.servicebus.windows.net/;SharedAccessKeyName=Root;",
        kafka_auto_offset_reset="latest",
        kafka_consumer_heartbeat_interval_ms=5_000,
        kafka_consumer_session_timeout_ms=20_000,
        kafka_consumer_max_poll_interval_ms=120_000,
    )
    on_assign = object()
    on_revoke = object()

    consumer = build_consumer(
        "airp-alert-consumer",
        ["aks.kubeevents.raw"],
        settings,
        on_assign=on_assign,
        on_revoke=on_revoke,
    )

    assert consumer.config["client.id"] == "airp-airp-alert-consumer"
    assert consumer.config["auto.offset.reset"] == "latest"
    assert consumer.config["enable.auto.commit"] is False
    assert consumer.config["heartbeat.interval.ms"] == 5_000
    assert consumer.config["session.timeout.ms"] == 20_000
    assert consumer.config["max.poll.interval.ms"] == 120_000
    assert consumer.config["socket.keepalive.enable"] is True
    assert consumer.subscription == {
        "topics": ["aks.kubeevents.raw"],
        "on_assign": on_assign,
        "on_revoke": on_revoke,
    }

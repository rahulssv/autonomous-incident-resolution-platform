from confluent_kafka import Consumer, Producer

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError


def kafka_config(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    if not settings.kafka_bootstrap_servers or not settings.kafka_password:
        raise AppError(
            "Kafka/Event Hubs is not configured", status_code=503, code="kafka_not_configured"
        )
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "security.protocol": settings.kafka_security_protocol,
        "sasl.mechanism": settings.kafka_sasl_mechanism,
        "sasl.username": settings.kafka_username,
        "sasl.password": settings.kafka_password,
    }


def build_producer(settings: Settings | None = None) -> Producer:
    return Producer(kafka_config(settings))


def build_consumer(group_id: str, topics: list[str], settings: Settings | None = None) -> Consumer:
    config = {
        **kafka_config(settings),
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": "false",
    }
    consumer = Consumer(config)
    consumer.subscribe(topics)
    return consumer

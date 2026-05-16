import json
from collections.abc import Callable
from typing import Any

from confluent_kafka import Consumer, Producer, TopicPartition
from pydantic import BaseModel

from airp.core.config import Settings, get_settings
from airp.core.errors import AppError

ConsumerCallback = Callable[[Consumer, list[TopicPartition]], None]


def kafka_config(settings: Settings | None = None) -> dict[str, Any]:
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


def build_consumer(
    group_id: str,
    topics: list[str],
    settings: Settings | None = None,
    *,
    on_assign: ConsumerCallback | None = None,
    on_revoke: ConsumerCallback | None = None,
) -> Consumer:
    settings = settings or get_settings()
    config = {
        **kafka_config(settings),
        "client.id": f"airp-{group_id}",
        "group.id": group_id,
        "auto.offset.reset": settings.kafka_auto_offset_reset,
        "enable.auto.commit": False,
        "heartbeat.interval.ms": settings.kafka_consumer_heartbeat_interval_ms,
        "max.poll.interval.ms": settings.kafka_consumer_max_poll_interval_ms,
        "session.timeout.ms": settings.kafka_consumer_session_timeout_ms,
        "socket.keepalive.enable": True,
    }
    consumer = Consumer(config)
    consumer.subscribe(topics, on_assign=on_assign, on_revoke=on_revoke)
    return consumer


def publish_json(
    producer: Producer,
    *,
    topic: str,
    value: BaseModel | dict[str, Any],
    key: str | None = None,
) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    producer.produce(
        topic,
        key=key,
        value=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )
    producer.poll(0)

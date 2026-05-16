from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass
from typing import Any

from confluent_kafka import KafkaError, Message
from pydantic import ValidationError

from airp.core.config import Settings, get_settings
from airp.core.logging import configure_logging, get_logger
from airp.db.session import AsyncSessionLocal
from airp.messaging.contracts import DeadLetterEvent
from airp.messaging.dedupe import RedisDedupeStore
from airp.messaging.eventhub_kafka import build_consumer, build_producer, publish_json
from airp.services.alert_ingestion_service import AlertIngestionService

logger = get_logger(__name__)


@dataclass
class ProcessedMessage:
    created_incident_ids: list[str]
    duplicate_keys: list[str]
    normalized_count: int


class AlertConsumerWorker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.consumer = build_consumer(
            self.settings.kafka_alert_consumer_group,
            [self.settings.kafka_alerts_raw_topic],
            self.settings,
        )
        self.producer = build_producer(self.settings)
        self._running = True

    async def process_message_value(self, value: bytes | str) -> ProcessedMessage:
        payload = self._decode_payload(value)
        async with AsyncSessionLocal() as session:
            service = AlertIngestionService(session, RedisDedupeStore(settings=self.settings))
            result = await service.ingest_alertmanager_payload(payload)
        return ProcessedMessage(
            created_incident_ids=result.created_incident_ids,
            duplicate_keys=result.duplicate_keys,
            normalized_count=result.normalized_count,
        )

    async def process_message(self, message: Message) -> None:
        try:
            result = await self.process_message_value(message.value())
            logger.info(
                "alert_message_processed",
                normalized_count=result.normalized_count,
                created_incident_ids=result.created_incident_ids,
                duplicate_count=len(result.duplicate_keys),
            )
            self.consumer.commit(message=message, asynchronous=False)
        except Exception as exc:
            logger.exception("alert_message_failed", error=str(exc))
            self._publish_deadletter(message, exc)
            self.consumer.commit(message=message, asynchronous=False)

    async def run_forever(self) -> None:
        logger.info(
            "alert_consumer_started",
            topic=self.settings.kafka_alerts_raw_topic,
            group_id=self.settings.kafka_alert_consumer_group,
        )
        try:
            while self._running:
                message = self.consumer.poll(1.0)
                if message is None:
                    await asyncio.sleep(0)
                    continue
                if message.error():
                    if message.error().code() != KafkaError._PARTITION_EOF:
                        logger.error("kafka_consumer_error", error=str(message.error()))
                    continue
                await self.process_message(message)
        finally:
            self.consumer.close()
            self.producer.flush(5)
            logger.info("alert_consumer_stopped")

    def stop(self) -> None:
        self._running = False

    def _publish_deadletter(self, message: Message, exc: Exception) -> None:
        failed_event = {
            "topic": message.topic(),
            "partition": message.partition(),
            "offset": message.offset(),
            "key": message.key().decode("utf-8", errors="replace") if message.key() else None,
            "value": message.value().decode("utf-8", errors="replace") if message.value() else None,
        }
        event = DeadLetterEvent(
            severity="warning",
            error=str(exc),
            failed_event=failed_event,
            payload={"source": "alert-consumer"},
        )
        publish_json(
            self.producer,
            topic=self.settings.kafka_deadletter_topic,
            value=event,
            key=failed_event["key"],
        )

    @staticmethod
    def _decode_payload(value: bytes | str) -> dict[str, Any]:
        raw = value.decode("utf-8") if isinstance(value, bytes) else value
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Kafka message value is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Kafka message value must be a JSON object")

        # Producers may either send the raw Alertmanager webhook body or wrap it in
        # AIRP's canonical event envelope. Accept both shapes.
        if "payload" in payload and "event_type" in payload:
            inner_payload = payload["payload"]
            if not isinstance(inner_payload, dict):
                raise ValueError("Event envelope payload must be an object")
            return inner_payload
        return payload


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = AlertConsumerWorker(settings)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)

    await worker.run_forever()


def main() -> None:
    try:
        asyncio.run(_run())
    except ValidationError as exc:
        logger.error("alert_consumer_configuration_error", error=str(exc))
        raise


if __name__ == "__main__":
    main()

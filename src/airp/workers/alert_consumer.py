"""
AIRP alert-consumer.

Reads alerts from the configured source and feeds them into
AlertIngestionService (the same downstream code path that manual incident
injection uses).

Two transports are supported, selected by AIRP_KAFKA_SECURITY_PROTOCOL:

  PLAINTEXT  – plain Kafka via confluent-kafka (local dev / docker-compose)
  SASL_SSL   – Azure Event Hubs SDK over AMQP-over-WebSocket on port 443
               (production; works on Basic SKU where the Kafka surface is
               unavailable). AIRP_KAFKA_PASSWORD must be the Event Hubs
               connection string in this mode.

Public surface:
    AlertConsumerWorker.run_forever()
    AlertConsumerWorker.stop()
    AlertConsumerWorker.process_message_value()
    main()
"""
from __future__ import annotations

import asyncio
import json
import signal
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from airp.core.config import Settings, get_settings
from airp.core.logging import configure_logging, get_logger
from airp.db.session import AsyncSessionLocal
from airp.messaging.dedupe import RedisDedupeStore
from airp.services.alert_ingestion_service import AlertIngestionService
from airp.workflows.client import TemporalIncidentWorkflowStarter

logger = get_logger(__name__)


@dataclass
class ProcessedMessage:
    created_incident_ids: list[str]
    duplicate_keys: list[str]
    normalized_count: int


def _starting_position_for(auto_offset_reset: str) -> str:
    """Map Kafka auto_offset_reset semantics onto Event Hubs starting_position."""
    normalized = (auto_offset_reset or "").strip().lower()
    if normalized == "earliest":
        return "-1"
    return "@latest"


def _is_plaintext(settings: Settings) -> bool:
    return (settings.kafka_security_protocol or "").upper() == "PLAINTEXT"


class AlertConsumerWorker:
    """Alert consumer supporting local Kafka (PLAINTEXT) and Azure Event Hubs (SASL_SSL).

    Transport is chosen automatically from AIRP_KAFKA_SECURITY_PROTOCOL:
      - PLAINTEXT → confluent-kafka consumer (local docker-compose Kafka)
      - SASL_SSL  → Azure Event Hubs SDK over AMQP-over-WebSocket (production)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.kafka_bootstrap_servers:
            raise ValueError("AIRP_KAFKA_BOOTSTRAP_SERVERS must be set.")

        self._hub_name = self.settings.kafka_alerts_raw_topic
        self._consumer_group = self.settings.kafka_alert_consumer_group or "$Default"

        self.workflow_starter = (
            TemporalIncidentWorkflowStarter(self.settings)
            if self.settings.temporal_start_workflows
            else None
        )
        self._running = True
        self._processed_messages = 0
        self._last_message_at = time.monotonic()
        self._stop_event: asyncio.Event | None = None
        self._idle_logger_task: asyncio.Task | None = None

        if _is_plaintext(self.settings):
            self._transport = "kafka-plaintext"
            self._kafka_consumer = self._build_kafka_consumer()
            self._eventhub_client = None
        else:
            if not self.settings.kafka_password:
                raise ValueError(
                    "AIRP_KAFKA_PASSWORD must be set to the Event Hubs connection string "
                    "when AIRP_KAFKA_SECURITY_PROTOCOL=SASL_SSL."
                )
            from azure.eventhub import TransportType  # noqa: PLC0415
            from azure.eventhub.aio import EventHubConsumerClient  # noqa: PLC0415

            self._transport = "amqp-over-websocket"
            self._kafka_consumer = None
            self._eventhub_client = EventHubConsumerClient.from_connection_string(
                self.settings.kafka_password,
                consumer_group=self._consumer_group,
                eventhub_name=self._hub_name,
                transport_type=TransportType.AmqpOverWebsocket,
            )

    def _build_kafka_consumer(self):
        from confluent_kafka import Consumer  # noqa: PLC0415

        conf = {
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "group.id": self._consumer_group,
            "auto.offset.reset": self.settings.kafka_auto_offset_reset or "latest",
            "enable.auto.commit": True,
            "session.timeout.ms": self.settings.kafka_consumer_session_timeout_ms,
            "heartbeat.interval.ms": self.settings.kafka_consumer_heartbeat_interval_ms,
            "max.poll.interval.ms": self.settings.kafka_consumer_max_poll_interval_ms,
        }
        consumer = Consumer(conf)
        consumer.subscribe([self._hub_name])
        return consumer

    async def process_message_value(self, value: bytes | str) -> ProcessedMessage:
        payload = self._decode_payload(value)
        async with AsyncSessionLocal() as session:
            service = AlertIngestionService(
                session,
                RedisDedupeStore(settings=self.settings),
                workflow_starter=self.workflow_starter,
            )
            result = await service.ingest_alertmanager_payload(payload)
        return ProcessedMessage(
            created_incident_ids=result.created_incident_ids,
            duplicate_keys=result.duplicate_keys,
            normalized_count=result.normalized_count,
        )

    # ------------------------------------------------------------------ #
    # EventHub transport                                                   #
    # ------------------------------------------------------------------ #

    async def _on_event(self, partition_context, event) -> None:
        if event is None:
            return
        try:
            value = event.body_as_str()
        except Exception as exc:  # noqa: BLE001
            logger.exception("alert_message_body_decode_failed", error=str(exc))
            await partition_context.update_checkpoint(event)
            return
        try:
            result = await self.process_message_value(value)
            logger.info(
                "alert_message_processed",
                topic=self._hub_name,
                partition=partition_context.partition_id,
                offset=event.offset,
                sequence_number=event.sequence_number,
                normalized_count=result.normalized_count,
                created_incident_ids=result.created_incident_ids,
                duplicate_count=len(result.duplicate_keys),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "alert_message_failed",
                error=str(exc),
                partition=partition_context.partition_id,
                offset=event.offset,
            )
        finally:
            self._processed_messages += 1
            self._last_message_at = time.monotonic()
            try:
                await partition_context.update_checkpoint(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning("alert_message_checkpoint_failed", error=str(exc))

    async def _run_eventhub(self) -> None:
        assert self._eventhub_client is not None
        starting_position = _starting_position_for(self.settings.kafka_auto_offset_reset)
        assert self._stop_event is not None
        async with self._eventhub_client:
            receive_task = asyncio.create_task(
                self._eventhub_client.receive(
                    on_event=self._on_event,
                    starting_position=starting_position,
                )
            )
            done, pending = await asyncio.wait(
                {receive_task, asyncio.create_task(self._stop_event.wait())},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    # ------------------------------------------------------------------ #
    # Plain Kafka transport                                                #
    # ------------------------------------------------------------------ #

    async def _run_kafka(self) -> None:
        """Poll confluent-kafka in a thread so the event loop stays free."""
        assert self._kafka_consumer is not None
        assert self._stop_event is not None
        poll_timeout = float(self.settings.kafka_consumer_poll_timeout_seconds or 1)
        loop = asyncio.get_running_loop()

        while not self._stop_event.is_set():
            msg = await loop.run_in_executor(
                None, self._kafka_consumer.poll, poll_timeout
            )
            if msg is None:
                continue
            if msg.error():
                logger.warning("kafka_consumer_error", error=str(msg.error()))
                continue
            try:
                result = await self.process_message_value(msg.value())
                logger.info(
                    "alert_message_processed",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    normalized_count=result.normalized_count,
                    created_incident_ids=result.created_incident_ids,
                    duplicate_count=len(result.duplicate_keys),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "alert_message_failed",
                    error=str(exc),
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )
            finally:
                self._processed_messages += 1
                self._last_message_at = time.monotonic()

        await loop.run_in_executor(None, self._kafka_consumer.close)

    # ------------------------------------------------------------------ #
    # Shared                                                               #
    # ------------------------------------------------------------------ #

    async def _idle_logger(self) -> None:
        interval = max(int(self.settings.kafka_consumer_idle_log_seconds or 30), 1)
        empty_polls = 0
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            if self._stop_event.is_set():
                return
            empty_polls += interval
            now = time.monotonic()
            logger.info(
                "alert_consumer_polling",
                topic=self._hub_name,
                group_id=self._consumer_group,
                idle_seconds=round(now - self._last_message_at, 3),
                empty_polls=empty_polls,
                processed_messages=self._processed_messages,
            )

    async def run_forever(self) -> None:
        self._stop_event = asyncio.Event()
        logger.info(
            "alert_consumer_started",
            transport=self._transport,
            endpoint=self.settings.kafka_bootstrap_servers,
            topic=self._hub_name,
            group_id=self._consumer_group,
            auto_offset_reset=self.settings.kafka_auto_offset_reset,
            idle_log_seconds=self.settings.kafka_consumer_idle_log_seconds,
        )
        self._idle_logger_task = asyncio.create_task(self._idle_logger())
        try:
            if _is_plaintext(self.settings):
                await self._run_kafka()
            else:
                await self._run_eventhub()
        finally:
            if self._idle_logger_task is not None:
                self._idle_logger_task.cancel()
                try:
                    await self._idle_logger_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            logger.info(
                "alert_consumer_stopped", processed_messages=self._processed_messages
            )

    def stop(self) -> None:
        self._running = False
        if self._stop_event is not None:
            self._stop_event.set()

    @staticmethod
    def _decode_payload(value: bytes | str) -> dict[str, Any]:
        raw = value.decode("utf-8") if isinstance(value, bytes) else value
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Event message value is not valid JSON") from exc
        if isinstance(payload, list):
            if not all(isinstance(item, dict) for item in payload):
                raise ValueError("Event message list values must contain only JSON objects")
            return {"records": payload}
        if not isinstance(payload, dict):
            raise ValueError("Event message value must be a JSON object")
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

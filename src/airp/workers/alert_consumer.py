"""
AIRP alert-consumer.

Reads alerts from the configured Event Hub and feeds them into
AlertIngestionService (the same downstream code path that manual incident
injection uses).

We use the official Azure Event Hubs SDK with AMQP-over-WebSocket on port
443 so this works on Event Hubs Basic SKU. The Kafka protocol surface
(port 9093) is only available on Standard SKU and above; the namespace
connection string is still the standard Event Hubs connection string,
just plumbed through the AMQP/HTTPS path rather than confluent-kafka.

Public surface preserved for backwards compatibility:
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

from azure.eventhub import TransportType
from azure.eventhub.aio import EventHubConsumerClient
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
    """Map Kafka auto_offset_reset semantics onto Event Hubs starting_position.

    - "earliest" -> "-1" (read from the beginning of the partition)
    - "latest"   -> "@latest" (only events arriving after the subscription starts)
    Anything else falls back to @latest, mirroring Kafka's permissive default.
    """
    normalized = (auto_offset_reset or "").strip().lower()
    if normalized == "earliest":
        return "-1"
    return "@latest"


class AlertConsumerWorker:
    """Event Hubs SDK based alert consumer (AMQP-over-WebSocket / port 443).

    This replaces the previous confluent-kafka implementation. Event Hubs Basic
    SKU does not expose the Kafka protocol; AMQP-over-WebSocket on port 443 is
    the only receive path that works there.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.kafka_bootstrap_servers:
            raise ValueError(
                "AIRP_KAFKA_BOOTSTRAP_SERVERS must be set even when using the Event Hubs "
                "SDK (we only use it to log the target endpoint)."
            )
        if not self.settings.kafka_password:
            raise ValueError(
                "AIRP_KAFKA_PASSWORD must be set to the Event Hubs connection string."
            )

        self._connection_string = self.settings.kafka_password
        self._hub_name = self.settings.kafka_alerts_raw_topic
        self._consumer_group = self.settings.kafka_alert_consumer_group or "$Default"
        self._starting_position = _starting_position_for(
            self.settings.kafka_auto_offset_reset
        )

        self.client = EventHubConsumerClient.from_connection_string(
            self._connection_string,
            consumer_group=self._consumer_group,
            eventhub_name=self._hub_name,
            transport_type=TransportType.AmqpOverWebsocket,
        )

        self.workflow_starter = (
            TemporalIncidentWorkflowStarter(self.settings)
            if self.settings.temporal_start_workflows
            else None
        )

        self._running = True
        self._processed_messages = 0
        self._last_message_at = time.monotonic()
        self._last_idle_log_at = time.monotonic()
        self._stop_event: asyncio.Event | None = None
        self._idle_logger_task: asyncio.Task | None = None

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

    async def _on_event(self, partition_context, event) -> None:
        if event is None:
            # Event Hubs SDK emits a None event on partition idle. Skip silently.
            return
        try:
            value = event.body_as_str()
        except Exception as exc:  # noqa: BLE001 - guard malformed payloads
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
        except Exception as exc:  # noqa: BLE001 - never crash the consumer
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
            except Exception as exc:  # noqa: BLE001 - checkpoint failures are non-fatal
                logger.warning("alert_message_checkpoint_failed", error=str(exc))

    async def _idle_logger(self) -> None:
        """Background task that emits the same `alert_consumer_polling` log
        events the old Kafka implementation produced. Preserves the observable
        contract used by monitors and dashboards."""
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
            transport="amqp-over-websocket",
            endpoint=self.settings.kafka_bootstrap_servers,
            topic=self._hub_name,
            group_id=self._consumer_group,
            auto_offset_reset=self.settings.kafka_auto_offset_reset,
            starting_position=self._starting_position,
            idle_log_seconds=self.settings.kafka_consumer_idle_log_seconds,
        )

        self._idle_logger_task = asyncio.create_task(self._idle_logger())

        try:
            async with self.client:
                receive_task = asyncio.create_task(
                    self.client.receive(
                        on_event=self._on_event,
                        starting_position=self._starting_position,
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

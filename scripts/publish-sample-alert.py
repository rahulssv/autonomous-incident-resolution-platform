#!/usr/bin/env python
from __future__ import annotations

from airp.core.config import get_settings
from airp.messaging.contracts import RawAlertEvent
from airp.messaging.eventhub_kafka import build_producer, publish_json


def sample_alertmanager_payload() -> dict:
    return {
        "receiver": "airp",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighLatency",
                    "service": "checkout-api",
                    "severity": "critical",
                    "namespace": "shopfast",
                    "environment": "prod",
                    "pod": "checkout-api-abc123",
                },
                "annotations": {
                    "summary": "Checkout latency spike",
                    "description": "p95 latency is above SLO for checkout-api.",
                },
                "startsAt": "2026-05-16T00:00:00Z",
                "fingerprint": "sample-high-latency-001",
                "generatorURL": "https://grafana.example/explore",
            }
        ],
    }


def main() -> None:
    settings = get_settings()
    producer = build_producer(settings)
    payload = sample_alertmanager_payload()
    event = RawAlertEvent(
        correlation_id="sample-high-latency-001",
        service="checkout-api",
        namespace="shopfast",
        environment="prod",
        severity="critical",
        payload=payload,
    )
    publish_json(
        producer,
        topic=settings.kafka_alerts_raw_topic,
        key="sample-high-latency-001",
        value=event,
    )
    producer.flush(10)


if __name__ == "__main__":
    main()

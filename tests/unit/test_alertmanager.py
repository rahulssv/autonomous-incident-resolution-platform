import json

import pytest

from backend.src.airp.domain.enums import IncidentSeverity
from backend.src.airp.messaging.alertmanager import normalize_alertmanager_payload
from backend.src.airp.messaging.dedupe import InMemoryDedupeStore
from backend.src.airp.workers.alert_consumer import AlertConsumerWorker


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
                    "description": "p95 latency is above SLO",
                },
                "startsAt": "2026-05-16T00:00:00Z",
                "fingerprint": "abc123",
                "generatorURL": "https://grafana.example/explore",
            }
        ],
    }


def test_normalize_alertmanager_payload_maps_incident_fields() -> None:
    alerts = normalize_alertmanager_payload(sample_alertmanager_payload())

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_name == "HighLatency"
    assert alert.service == "checkout-api"
    assert alert.severity == IncidentSeverity.CRITICAL
    assert alert.namespace == "shopfast"
    assert alert.pod_name == "checkout-api-abc123"
    assert alert.dedupe_key == "prod:shopfast:checkout-api:HighLatency:critical:abc123"

    incident = alert.to_incident_create()
    assert incident.title == "Checkout latency spike"
    assert incident.severity == IncidentSeverity.CRITICAL
    assert incident.metadata["fingerprint"] == "abc123"


def test_normalize_alertmanager_payload_requires_alerts() -> None:
    with pytest.raises(ValueError, match="non-empty alerts"):
        normalize_alertmanager_payload({"alerts": []})


@pytest.mark.asyncio
async def test_in_memory_dedupe_claims_only_once() -> None:
    store = InMemoryDedupeStore()

    assert await store.claim("key", ttl_seconds=60) is True
    assert await store.claim("key", ttl_seconds=60) is False


def test_alert_consumer_decodes_raw_or_enveloped_payload() -> None:
    raw_payload = sample_alertmanager_payload()
    raw = AlertConsumerWorker._decode_payload(
        """
        {
          "receiver": "airp",
          "alerts": [{"labels": {"alertname": "A", "service": "svc"}}]
        }
        """
    )
    enveloped = AlertConsumerWorker._decode_payload(
        json.dumps(
            {
                "event_type": "airp.alert.raw",
                "payload": raw_payload,
            }
        )
    )

    assert raw["receiver"] == "airp"
    assert enveloped["receiver"] == "airp"

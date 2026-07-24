#!/usr/bin/env python
"""Publish a raw alert to Kafka to trigger an AIRP incident workflow.

Targets the local docker-compose Kafka EXTERNAL listener by default (localhost:9093).
Produces one message to `airp.alerts.raw` (or AIRP_KAFKA_ALERTS_RAW_TOPIC).

Usage:
  # Default crashloop scenario
  python scripts/create-incident.py

  # Choose a scenario
  .venv/bin/python scripts/create-incident.py --scenario oom
  .venv/bin/python scripts/create-incident.py --scenario latency

  # Override fields
  .venv/bin/python scripts/create-incident.py --service my-svc --namespace staging --severity warning

  # Custom bootstrap server
  .venv/bin/python scripts/create-incident.py --broker localhost:9093

  # Dry-run: print the payload without publishing
  .venv/bin/python scripts/create-incident.py --dry-run

Scenarios: crashloop, oom, latency, memory-leak, high-error-rate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

# ---------------------------------------------------------------------------
# confluent-kafka is the only runtime dep; it ships with the venv/docker image.
# ---------------------------------------------------------------------------
try:
    from confluent_kafka import Producer
except ImportError:
    sys.exit(
        "confluent-kafka is not installed.\n"
        "  pip install confluent-kafka   # or activate the project venv"
    )


# ---------------------------------------------------------------------------
# Scenario presets — mirror the signals used by the AIRP agent fixtures
# ---------------------------------------------------------------------------
SCENARIOS: dict[str, dict] = {
    "crashloop": {
        "alert_name": "KubePodCrashLooping",
        "summary": "CrashLoopBackOff in payment service",
        "description": "KubeEvents reported BackOff and repeated container restarts.",
        "service": "payment-service",
        "deployment": "payment-service",
        "pod": "payment-service-6d8f9-xk2p1",
        "namespace": "payments",
        "severity": "critical",
        "signal_type": "CrashLoopBackOff",
    },
    "oom": {
        "alert_name": "KubeContainerOOMKilled",
        "summary": "OOMKilled in checkout worker",
        "description": "KubeEvents reported container termination due to memory pressure.",
        "service": "checkout-worker",
        "deployment": "checkout-worker",
        "pod": "checkout-worker-7c4b5-mn9x2",
        "namespace": "shopfast",
        "severity": "warning",
        "signal_type": "OOMKilled",
    },
    "latency": {
        "alert_name": "HighLatency",
        "summary": "Latency spike in orders API",
        "description": "Application logs reported timeout errors above the service SLO.",
        "service": "orders-api",
        "deployment": "orders-api",
        "pod": "orders-api-5f7d4-qw3r8",
        "namespace": "shopfast",
        "severity": "warning",
        "signal_type": "Latency spike",
    },
    "memory-leak": {
        "alert_name": "HighMemoryUsage",
        "summary": "Sustained memory growth in catalog service",
        "description": "Heap usage has grown monotonically for the past 30 minutes.",
        "service": "catalog-service",
        "deployment": "catalog-service",
        "pod": "catalog-service-9b2c1-rt4y5",
        "namespace": "catalog",
        "severity": "warning",
        "signal_type": "MemoryLeak",
    },
    "high-error-rate": {
        "alert_name": "HighErrorRate",
        "summary": "5xx error rate spike in checkout API",
        "description": "HTTP 5xx responses exceeded 5% of traffic for 10 minutes.",
        "service": "checkout-api",
        "deployment": "checkout-api",
        "pod": "checkout-api-3e1a7-pz6w9",
        "namespace": "shopfast",
        "severity": "critical",
        "signal_type": "HighErrorRate",
    },
}

DEFAULT_SCENARIO = "crashloop"
DEFAULT_BROKER = "localhost:9093"
DEFAULT_TOPIC = "airp.alerts.raw"
DEFAULT_ENVIRONMENT = "prod"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a raw AIRP alert to Kafka to trigger an incident workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS),
        default=os.getenv("AIRP_E2E_SCENARIO", DEFAULT_SCENARIO),
        help=f"Alert scenario preset (default: {DEFAULT_SCENARIO})",
    )
    parser.add_argument(
        "--broker",
        default=os.getenv("AIRP_KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BROKER),
        help=f"Kafka bootstrap server (default: {DEFAULT_BROKER})",
    )
    parser.add_argument(
        "--topic",
        default=os.getenv("AIRP_KAFKA_ALERTS_RAW_TOPIC", DEFAULT_TOPIC),
        help=f"Kafka topic (default: {DEFAULT_TOPIC})",
    )
    parser.add_argument(
        "--service",
        default=None,
        help="Override the service name from the scenario preset",
    )
    parser.add_argument(
        "--namespace",
        default=os.getenv("AIRP_E2E_NAMESPACE"),
        help="Override the Kubernetes namespace",
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("AIRP_E2E_ENVIRONMENT", DEFAULT_ENVIRONMENT),
        help=f"Environment label (default: {DEFAULT_ENVIRONMENT})",
    )
    parser.add_argument(
        "--severity",
        choices=["info", "warning", "critical"],
        default=None,
        help="Override severity from the scenario preset",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Override the alert summary / title",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without publishing to Kafka",
    )
    return parser.parse_args()


def _build_event(args: argparse.Namespace) -> tuple[str, dict]:
    preset = SCENARIOS[args.scenario]
    now = datetime.now(UTC)
    run_id = uuid4().hex[:12]
    fingerprint = f"{args.scenario}-{run_id}"

    service = args.service or preset["service"]
    namespace = args.namespace or preset["namespace"]
    severity = args.severity or preset["severity"]
    environment = args.environment
    alert_name = preset["alert_name"]
    summary = args.title or preset["summary"]
    description = preset["description"]
    deployment = preset["deployment"]
    pod = preset["pod"]

    # idempotency_key matches the format used by the AIRP alert consumer
    idempotency_key = f"{environment}:{namespace}:{service}:{alert_name}:{severity}:{fingerprint}"

    alertmanager_payload = {
        "receiver": "airp",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": alert_name,
                    "service": service,
                    "deployment": deployment,
                    "severity": severity,
                    "namespace": namespace,
                    "environment": environment,
                    "pod": pod,
                    "signal_type": preset["signal_type"],
                },
                "annotations": {
                    "summary": summary,
                    "description": description,
                },
                "startsAt": now.isoformat().replace("+00:00", "Z"),
                "fingerprint": fingerprint,
                "generatorURL": "https://grafana.example/airp/local",
            }
        ],
    }

    envelope = {
        "schema_version": "1.0",
        "event_id": str(uuid4()),
        "correlation_id": idempotency_key,
        "event_type": "airp.alert.raw",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "service": service,
        "namespace": namespace,
        "environment": environment,
        "severity": severity,
        "producer": "alertmanager",
        "payload": alertmanager_payload,
    }

    return fingerprint, envelope


def _publish(broker: str, topic: str, key: str, value: dict) -> None:
    producer = Producer({"bootstrap.servers": broker})

    delivered: list[bool] = []

    def _on_delivery(err, msg):
        if err:
            print(f"[create-incident] delivery error: {err}", file=sys.stderr)
            delivered.append(False)
        else:
            print(
                f"[create-incident] delivered → topic={msg.topic()} "
                f"partition={msg.partition()} offset={msg.offset()}"
            )
            delivered.append(True)

    producer.produce(
        topic,
        key=key.encode("utf-8"),
        value=json.dumps(value, separators=(",", ":")).encode("utf-8"),
        on_delivery=_on_delivery,
    )
    remaining = producer.flush(30)
    if remaining:
        sys.exit(f"[create-incident] flush timed out with {remaining} undelivered message(s)")
    if not delivered or not delivered[0]:
        sys.exit("[create-incident] message was not delivered successfully")


def main() -> None:
    args = _parse_args()
    fingerprint, envelope = _build_event(args)

    print(f"[create-incident] scenario={args.scenario}  fingerprint={fingerprint}")
    print(f"[create-incident] service={envelope['service']}  namespace={envelope['namespace']}")
    print(f"[create-incident] severity={envelope['severity']}  environment={envelope['environment']}")
    print(f"[create-incident] topic={args.topic}  broker={args.broker}")

    if args.dry_run:
        print("\n--- payload (dry-run, not published) ---")
        print(json.dumps(envelope, indent=2))
        return

    _publish(args.broker, args.topic, fingerprint, envelope)
    print(f"[create-incident] incident alert published  correlation_id={envelope['correlation_id']}")


if __name__ == "__main__":
    main()

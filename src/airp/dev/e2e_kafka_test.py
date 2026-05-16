from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4

from sqlalchemy import func, select

from airp.core.config import Settings, get_settings
from airp.db.models.incident import (
    DocumentationReport,
    EvidenceItem,
    GitHubArtifact,
    Incident,
    IncidentEmbedding,
    IncidentEvent,
    ModelCall,
    RCAHypothesis,
    RemediationPlan,
    SlackMessage,
    ToolCall,
)
from airp.db.session import AsyncSessionLocal
from airp.domain.enums import IncidentSeverity, IncidentStatus
from airp.messaging.contracts import RawAlertEvent
from airp.messaging.eventhub_kafka import build_producer, publish_json
from airp.schemas.incidents import WorkflowSignalRequest
from airp.services.incident_service import IncidentService
from airp.services.workflow_service import IncidentWorkflowSignalService

ALWAYS_LIVE_DEPENDENCIES = ("postgres", "redis", "temporal", "event_hubs", "genaihub")
EVIDENCE_LIVE_DEPENDENCIES = ("kubernetes_mcp", "github_mcp", "dockerhub")
DEFAULT_REQUIRED_EVENTS = (
    "incident.created",
    "alert.validated",
    "workflow.started",
    "monitoring.assessed",
    "correlation.completed",
    "rca.started",
    "rca.hypotheses.generated",
    "remediation.planned",
    "documentation.drafted",
    "workflow.step.completed",
    "github.issue.created",
    "slack.notification.sent",
)
EMBEDDING_STEP_EVENTS = {"embedding.generated", "embedding.skipped"}
EXTERNAL_ACTION_TERMINAL_FAILURES = {
    "github.issue.failed",
    "github.issue.skipped",
    "slack.notification.failed",
    "slack.notification.skipped",
}


@dataclass
class E2ESnapshot:
    incident_id: str | None
    incident_status: str | None
    workflow_id: str | None
    workflow_run_id: str | None
    event_types: list[str]
    counts: dict[str, int]
    latest_event: str | None
    embedding_event: dict[str, Any] | None

    @property
    def event_type_set(self) -> set[str]:
        return set(self.event_types)


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    _check_configuration(settings)
    require_evidence = _require_evidence(args, settings)
    if not args.skip_readiness:
        readiness = _wait_for_readiness(args.api_url, args.readiness_timeout_seconds)
        _assert_live_dependencies(readiness, _live_dependencies(require_evidence))

    test_case = _build_test_case(args)
    _print_step(f"Publishing Kafka alert key={test_case['fingerprint']}")
    _publish_alert(settings, test_case)

    required_events = _required_events(args)
    _print_step(f"Waiting for incident workflow evidence, timeout={args.timeout_seconds}s")
    snapshot = await _wait_for_e2e_result(
        idempotency_key=test_case["idempotency_key"],
        required_events=required_events,
        require_evidence=require_evidence,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )

    if args.close_workflow and snapshot.workflow_id:
        _print_step(f"Closing workflow {snapshot.workflow_id}")
        await _close_workflow(snapshot.incident_id)
        snapshot = await _wait_for_incident_status(
            incident_id=snapshot.incident_id,
            status=IncidentStatus.CLOSED.value,
            timeout_seconds=args.close_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

    summary = {
        "status": "passed",
        "incident_id": snapshot.incident_id,
        "incident_status": snapshot.incident_status,
        "workflow_id": snapshot.workflow_id,
        "workflow_run_id": snapshot.workflow_run_id,
        "kafka_topic": settings.kafka_alerts_raw_topic,
        "idempotency_key": test_case["idempotency_key"],
        "live_dependencies": list(_live_dependencies(require_evidence)),
        "require_evidence": require_evidence,
        "counts": snapshot.counts,
        "latest_event": snapshot.latest_event,
        "embedding_event": snapshot.embedding_event,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an AIRP E2E test through Kafka/Event Hubs, Temporal, agents, and DB.",
    )
    parser.add_argument("--api-url", default=os.getenv("AIRP_E2E_API_URL", "http://localhost:8080"))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("AIRP_E2E_TIMEOUT_SECONDS", "600")),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=float(os.getenv("AIRP_E2E_POLL_INTERVAL_SECONDS", "5")),
    )
    parser.add_argument(
        "--readiness-timeout-seconds",
        type=float,
        default=float(os.getenv("AIRP_E2E_READINESS_TIMEOUT_SECONDS", "60")),
    )
    parser.add_argument(
        "--close-timeout-seconds",
        type=float,
        default=float(os.getenv("AIRP_E2E_CLOSE_TIMEOUT_SECONDS", "60")),
    )
    parser.add_argument("--service", default=os.getenv("AIRP_E2E_SERVICE", "checkout-api"))
    parser.add_argument("--namespace", default=os.getenv("AIRP_E2E_NAMESPACE", "shopfast"))
    parser.add_argument("--environment", default=os.getenv("AIRP_E2E_ENVIRONMENT", "prod"))
    parser.add_argument("--pod", default=os.getenv("AIRP_E2E_POD", "checkout-api-e2e"))
    parser.add_argument("--deployment", default=os.getenv("AIRP_E2E_DEPLOYMENT", "checkout-api"))
    parser.add_argument(
        "--alert-name",
        default=os.getenv("AIRP_E2E_ALERT_NAME", "AIRPE2ECheckoutLatency"),
    )
    parser.add_argument(
        "--severity",
        choices=[severity.value for severity in IncidentSeverity],
        default=os.getenv("AIRP_E2E_SEVERITY", IncidentSeverity.CRITICAL.value),
    )
    parser.add_argument(
        "--required-event",
        action="append",
        default=[],
        help="Additional event type that must appear before the test passes.",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        default=_env_bool_or_none("AIRP_E2E_REQUIRE_EVIDENCE"),
        help=(
            "Require at least one persisted MCP evidence item. Defaults to true when "
            "AIRP_AGENT_READ_ONLY_EVIDENCE_ENABLED is true."
        ),
    )
    parser.add_argument(
        "--no-require-evidence",
        action="store_false",
        dest="require_evidence",
        help="Do not require a persisted MCP evidence item.",
    )
    parser.add_argument(
        "--skip-readiness",
        action="store_true",
        default=os.getenv("AIRP_E2E_SKIP_READINESS", "").lower() in {"1", "true", "yes"},
    )
    parser.add_argument(
        "--leave-workflow-open",
        action="store_false",
        dest="close_workflow",
        default=os.getenv("AIRP_E2E_CLOSE_WORKFLOW", "true").lower() not in {"0", "false", "no"},
        help="Do not close the Temporal workflow after the E2E assertion passes.",
    )
    return parser.parse_args()


def _env_bool_or_none(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value.lower() in {"1", "true", "yes"}


def _require_evidence(args: argparse.Namespace, settings: Settings) -> bool:
    if args.require_evidence is not None:
        return bool(args.require_evidence)
    return settings.agent_read_only_evidence_enabled


def _live_dependencies(require_evidence: bool) -> tuple[str, ...]:
    if require_evidence:
        return (*ALWAYS_LIVE_DEPENDENCIES, *EVIDENCE_LIVE_DEPENDENCIES)
    return ALWAYS_LIVE_DEPENDENCIES


def _check_configuration(settings: Settings) -> None:
    missing = []
    if not settings.kafka_bootstrap_servers:
        missing.append("AIRP_KAFKA_BOOTSTRAP_SERVERS")
    if not settings.kafka_password:
        missing.append("AIRP_KAFKA_PASSWORD")
    if not settings.database_url:
        missing.append("AIRP_DATABASE_URL")
    if not settings.redis_url:
        missing.append("AIRP_REDIS_URL")
    if missing:
        raise SystemExit(f"E2E configuration is incomplete: {', '.join(missing)}")


def _wait_for_readiness(api_url: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    url = f"{api_url.rstrip('/')}/api/readiness?active=true"
    last_error = "readiness has not been checked yet"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ready":
                _print_step("API active readiness is ready")
                return payload
            last_error = json.dumps(payload, sort_keys=True)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise SystemExit(f"API readiness did not become ready: {last_error}")


def _assert_live_dependencies(readiness: dict[str, Any], dependency_names: tuple[str, ...]) -> None:
    dependencies = readiness.get("dependencies")
    if not isinstance(dependencies, dict):
        raise SystemExit("API readiness response did not include dependency details")

    failures = []
    for name in dependency_names:
        dependency = dependencies.get(name)
        if not isinstance(dependency, dict):
            failures.append(f"{name}: missing")
            continue
        status = dependency.get("status")
        reachability = (dependency.get("details") or {}).get("reachability")
        if status != "ready" or reachability != "reachable":
            failures.append(f"{name}: status={status}, reachability={reachability}")

    if failures:
        raise SystemExit(
            "Live E2E dependencies are not ready/reachable: " + "; ".join(failures)
        )

    _print_step("Live dependencies reachable: " + ", ".join(dependency_names))


def _build_test_case(args: argparse.Namespace) -> dict[str, Any]:
    run_id = f"e2e-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    fingerprint = run_id
    idempotency_key = (
        f"{args.environment}:{args.namespace}:{args.service}:"
        f"{args.alert_name}:{args.severity}:{fingerprint}"
    )
    return {
        "run_id": run_id,
        "fingerprint": fingerprint,
        "idempotency_key": idempotency_key,
        "payload": {
            "receiver": "airp-e2e",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": args.alert_name,
                        "service": args.service,
                        "deployment": args.deployment,
                        "severity": args.severity,
                        "namespace": args.namespace,
                        "environment": args.environment,
                        "pod": args.pod,
                        "team": "airp-e2e",
                    },
                    "annotations": {
                        "summary": f"E2E checkout latency spike {run_id}",
                        "description": (
                            "AIRP E2E test alert. The workflow should correlate this event, "
                            "collect MCP evidence, synthesize RCA, draft remediation, and "
                            "persist documentation."
                        ),
                    },
                    "startsAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "fingerprint": fingerprint,
                    "generatorURL": "https://grafana.example/airp/e2e",
                }
            ],
        },
    }


def _publish_alert(settings: Settings, test_case: dict[str, Any]) -> None:
    event = RawAlertEvent(
        correlation_id=test_case["idempotency_key"],
        service=test_case["payload"]["alerts"][0]["labels"]["service"],
        namespace=test_case["payload"]["alerts"][0]["labels"]["namespace"],
        environment=test_case["payload"]["alerts"][0]["labels"]["environment"],
        severity=IncidentSeverity(test_case["payload"]["alerts"][0]["labels"]["severity"]),
        payload=test_case["payload"],
    )
    producer = build_producer(settings)
    publish_json(
        producer,
        topic=settings.kafka_alerts_raw_topic,
        key=test_case["fingerprint"],
        value=event,
    )
    remaining = producer.flush(30)
    if remaining:
        raise SystemExit(
            f"Kafka producer flush timed out with {remaining} queued message(s) remaining"
        )


def _required_events(args: argparse.Namespace) -> set[str]:
    required = set(DEFAULT_REQUIRED_EVENTS)
    required.update(args.required_event)
    return required


async def _wait_for_e2e_result(
    *,
    idempotency_key: str,
    required_events: set[str],
    require_evidence: bool,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> E2ESnapshot:
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: E2ESnapshot | None = None
    while time.monotonic() < deadline:
        snapshot = await _snapshot_by_idempotency_key(idempotency_key)
        if snapshot.incident_id:
            last_snapshot = snapshot
            _raise_for_failed_workflow(snapshot)
            missing_events = required_events - snapshot.event_type_set
            embedding_step_ready = bool(snapshot.event_type_set & EMBEDDING_STEP_EVENTS)
            required_artifacts_ready = (
                snapshot.counts["hypotheses"] >= 1
                and snapshot.counts["remediation_plans"] >= 1
                and snapshot.counts["documentation_reports"] >= 1
                and snapshot.counts["github_artifacts"] >= 1
                and snapshot.counts["slack_messages"] >= 1
                and (snapshot.counts["evidence"] >= 1 or not require_evidence)
            )
            if not missing_events and embedding_step_ready and required_artifacts_ready:
                return snapshot
            _print_progress(snapshot, missing_events, embedding_step_ready, require_evidence)
        else:
            _print_step("Waiting for Kafka consumer to create incident")
        await asyncio.sleep(poll_interval_seconds)

    missing = sorted(required_events - (last_snapshot.event_type_set if last_snapshot else set()))
    if last_snapshot and not last_snapshot.event_type_set & EMBEDDING_STEP_EVENTS:
        missing.append("embedding.generated|embedding.skipped")
    counts = last_snapshot.counts if last_snapshot else {}
    raise SystemExit(
        "E2E timed out before required workflow output was persisted. "
        f"missing_events={missing}, counts={counts}"
    )


async def _wait_for_incident_status(
    *,
    incident_id: str | None,
    status: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> E2ESnapshot:
    if incident_id is None:
        raise SystemExit("Cannot wait for incident status without an incident id")

    deadline = time.monotonic() + timeout_seconds
    snapshot: E2ESnapshot | None = None
    while time.monotonic() < deadline:
        snapshot = await _snapshot_by_incident_id(incident_id)
        if snapshot.incident_status == status:
            return snapshot
        await asyncio.sleep(poll_interval_seconds)
    raise SystemExit(
        f"Timed out waiting for incident {incident_id} to become {status}; "
        f"last_status={snapshot.incident_status if snapshot else None}"
    )


async def _snapshot_by_idempotency_key(idempotency_key: str) -> E2ESnapshot:
    async with AsyncSessionLocal() as session:
        incident = await session.scalar(
            select(Incident).where(Incident.idempotency_key == idempotency_key).limit(1)
        )
        return await _snapshot(session, incident)


async def _snapshot_by_incident_id(incident_id: str) -> E2ESnapshot:
    async with AsyncSessionLocal() as session:
        incident = await session.get(Incident, incident_id)
        return await _snapshot(session, incident)


async def _snapshot(session, incident: Incident | None) -> E2ESnapshot:
    if incident is None:
        return E2ESnapshot(None, None, None, None, [], _empty_counts(), None, None)

    events = list(
        (
            await session.scalars(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident.id)
                .order_by(IncidentEvent.created_at)
            )
        ).all()
    )
    event_types = [event.event_type for event in events]
    embedding_event = next(
        (
            event.payload
            for event in reversed(events)
            if event.event_type in {"embedding.generated", "embedding.skipped"}
        ),
        None,
    )
    counts = {
        "events": len(events),
        "evidence": await _count(session, EvidenceItem, incident.id),
        "tool_calls": await _count(session, ToolCall, incident.id),
        "hypotheses": await _count(session, RCAHypothesis, incident.id),
        "model_calls": await _count(session, ModelCall, incident.id),
        "remediation_plans": await _count(session, RemediationPlan, incident.id),
        "documentation_reports": await _count(session, DocumentationReport, incident.id),
        "github_artifacts": await _count(session, GitHubArtifact, incident.id),
        "slack_messages": await _count(session, SlackMessage, incident.id),
        "embeddings": await _count(session, IncidentEmbedding, incident.id),
    }
    return E2ESnapshot(
        incident_id=incident.id,
        incident_status=incident.status,
        workflow_id=incident.workflow_id,
        workflow_run_id=incident.workflow_run_id,
        event_types=event_types,
        counts=counts,
        latest_event=event_types[-1] if event_types else None,
        embedding_event=embedding_event,
    )


async def _count(session, model: type, incident_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(model.incident_id == incident_id)
        )
        or 0
    )


def _empty_counts() -> dict[str, int]:
    return {
        "events": 0,
        "evidence": 0,
        "tool_calls": 0,
        "hypotheses": 0,
        "model_calls": 0,
        "remediation_plans": 0,
        "documentation_reports": 0,
        "github_artifacts": 0,
        "slack_messages": 0,
        "embeddings": 0,
    }


def _raise_for_failed_workflow(snapshot: E2ESnapshot) -> None:
    if "workflow.start_failed" in snapshot.event_type_set:
        raise SystemExit(f"Workflow failed to start for incident {snapshot.incident_id}")
    failed_external_events = sorted(snapshot.event_type_set & EXTERNAL_ACTION_TERMINAL_FAILURES)
    if failed_external_events:
        raise SystemExit(
            f"External action did not complete for incident {snapshot.incident_id}: "
            f"{failed_external_events}"
        )


def _print_progress(
    snapshot: E2ESnapshot,
    missing_events: set[str],
    embedding_step_ready: bool,
    require_evidence: bool,
) -> None:
    artifact_gaps = []
    event_gaps = sorted(missing_events)
    if not embedding_step_ready:
        event_gaps.append("embedding.generated|embedding.skipped")
    if snapshot.counts["hypotheses"] < 1:
        artifact_gaps.append("hypotheses")
    if snapshot.counts["remediation_plans"] < 1:
        artifact_gaps.append("remediation_plans")
    if snapshot.counts["documentation_reports"] < 1:
        artifact_gaps.append("documentation_reports")
    if snapshot.counts["github_artifacts"] < 1:
        artifact_gaps.append("github_artifacts")
    if snapshot.counts["slack_messages"] < 1:
        artifact_gaps.append("slack_messages")
    if require_evidence and snapshot.counts["evidence"] < 1:
        artifact_gaps.append("evidence")
    _print_step(
        "Waiting for workflow output "
        f"incident={snapshot.incident_id} latest_event={snapshot.latest_event} "
        f"missing_events={event_gaps} artifact_gaps={artifact_gaps}"
    )


async def _close_workflow(incident_id: str | None) -> None:
    if incident_id is None:
        raise SystemExit("Cannot close workflow without an incident id")
    async with AsyncSessionLocal() as session:
        service = IncidentService(session)
        signal_service = IncidentWorkflowSignalService(service)
        await signal_service.signal_workflow(
            incident_id,
            WorkflowSignalRequest(
                signal="close",
                reason="AIRP E2E test finished.",
                payload={"source": "airp.dev.e2e_kafka_test"},
            ),
            actor="airp-e2e",
        )


def _print_step(message: str) -> None:
    print(f"[airp-e2e] {message}", flush=True)


if __name__ == "__main__":
    main()

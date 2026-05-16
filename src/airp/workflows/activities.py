from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import or_, select
from temporalio import activity

from airp.agents.factory import build_default_agent_supervisor
from airp.db.models.catalog import RuntimeWorkload, ServiceCatalog
from airp.db.session import AsyncSessionLocal
from airp.domain.enums import IncidentStatus
from airp.schemas.incidents import EvidenceItemCreate, IncidentEventCreate, IncidentSignal
from airp.services.incident_service import IncidentService


@activity.defn(name="incident_update_status")
async def incident_update_status(
    incident_id: str,
    status: str,
    reason: str | None,
    payload: dict[str, Any],
) -> None:
    async with AsyncSessionLocal() as session:
        await IncidentService(session).signal_incident(
            incident_id,
            IncidentSignal(
                status=IncidentStatus(status),
                reason=reason,
                payload=payload,
            ),
            actor="temporal-workflow",
        )


@activity.defn(name="incident_record_workflow_event")
async def incident_record_workflow_event(
    incident_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    async with AsyncSessionLocal() as session:
        await IncidentService(session).add_event(
            incident_id,
            IncidentEventCreate(
                event_type=event_type,
                producer="temporal-workflow",
                payload=payload,
            ),
        )


@activity.defn(name="agent_graph_run")
async def agent_graph_run(incident_id: str, workflow_id: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        service = IncidentService(session)
        incident = await service.get_incident(incident_id)
        service_context = await _service_context(session, incident.service_id)
        workload_context = await _workload_context(
            session,
            service_id=incident.service_id,
            namespace=incident.namespace,
            pod_name=incident.pod_name,
        )

        supervisor = build_default_agent_supervisor()
        state = await supervisor.run(
            incident_id=incident.id,
            workflow_id=workflow_id,
            title=incident.title,
            description=incident.description,
            severity=incident.severity,
            status=incident.status,
            correlation_id=incident.correlation_id,
            service_context=service_context,
            workload_context=workload_context,
        )

        for event in state.get("agent_events", []):
            await service.add_event(
                incident_id,
                IncidentEventCreate(
                    event_type=event["event_type"],
                    producer=f"langgraph.{event['agent']}",
                    payload=event["payload"],
                ),
            )
        await _persist_rca_outputs(service, incident_id, state)


async def _persist_rca_outputs(
    service: IncidentService, incident_id: str, state: dict[str, Any]
) -> None:
    evidence_ids = []
    bundle = state.get("rca_evidence_bundle") or {}

    for evidence_type in ("kubernetes", "github", "dockerhub"):
        data = bundle.get(evidence_type)
        if not _has_evidence_section(data):
            continue
        payload = dict(data)
        payload["payload_hash"] = _stable_hash(data)
        evidence = await service.add_evidence(
            incident_id,
            EvidenceItemCreate(
                evidence_type=evidence_type,
                source="langgraph.rca",
                summary=_evidence_summary(evidence_type, data),
                data=payload,
            ),
        )
        evidence_ids.append(evidence.id)

    for tool_call in _unique_tool_calls(
        [*bundle.get("tool_calls", []), *state.get("tool_calls", [])]
    ):
        await service.add_tool_call(
            incident_id,
            tool_server=tool_call.get("tool_server", "unknown"),
            tool_name=tool_call.get("tool_name", "unknown"),
            parameters=tool_call.get("parameters") or {},
            result={
                "status": tool_call.get("status"),
                "result_summary": tool_call.get("result_summary"),
            },
            latency_ms=tool_call.get("latency_ms"),
            error=tool_call.get("error"),
        )

    if evidence_ids:
        await service.add_event(
            incident_id,
            IncidentEventCreate(
                event_type="rca.evidence.persisted",
                producer="langgraph.rca",
                payload={"evidence_ids": evidence_ids},
            ),
        )


async def _service_context(session, service_id: str | None) -> dict[str, Any]:
    if not service_id:
        return {}
    service = await session.get(ServiceCatalog, service_id)
    if service is None:
        return {}
    return {
        "id": service.id,
        "name": service.name,
        "owner": service.owner,
        "environment": service.environment,
        "namespace": service.namespace,
        "deployment": service.deployment,
        "repository_url": service.repository_url,
        "docker_image": service.docker_image,
        "slack_channel": service.slack_channel,
        "dashboard_url": service.dashboard_url,
        "slo_url": service.slo_url,
        "runbook_url": service.runbook_url,
    }


async def _workload_context(
    session,
    *,
    service_id: str | None,
    namespace: str | None,
    pod_name: str | None,
) -> dict[str, Any]:
    conditions = []
    if service_id:
        conditions.append(RuntimeWorkload.service_id == service_id)
    if namespace:
        conditions.append(RuntimeWorkload.namespace == namespace)
    if pod_name:
        conditions.append(RuntimeWorkload.pod_name == pod_name)
    if not conditions:
        return {}

    stmt = select(RuntimeWorkload).where(or_(*conditions)).limit(1)
    workload = await session.scalar(stmt)
    if workload is None:
        return {}
    return {
        "id": workload.id,
        "service_id": workload.service_id,
        "namespace": workload.namespace,
        "deployment": workload.deployment,
        "replica_set": workload.replica_set,
        "pod_name": workload.pod_name,
        "container_name": workload.container_name,
        "image": workload.image,
        "image_id": workload.image_id,
        "node_name": workload.node_name,
        "ready": workload.ready,
        "restart_count": workload.restart_count,
    }


def _has_evidence_section(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return any(
        bool(value.get(key))
        for key in (
            "pods",
            "logs",
            "events",
            "deployment_state",
            "rollout_status",
            "replica_sets",
            "commits",
            "merged_prs",
            "changed_files",
            "releases",
            "prior_issues",
            "repository",
            "digest",
            "tag",
        )
    )


def _evidence_summary(evidence_type: str, data: dict[str, Any]) -> str:
    if evidence_type == "kubernetes":
        return (
            "Kubernetes evidence: "
            f"{len(data.get('pods', []))} pods, "
            f"{len(data.get('logs', []))} log windows, "
            f"{len(data.get('events', []))} events"
        )
    if evidence_type == "github":
        return (
            "GitHub evidence: "
            f"{len(data.get('commits', []))} commits, "
            f"{len(data.get('merged_prs', []))} merged PRs, "
            f"{len(data.get('prior_issues', []))} prior issues"
        )
    repository = data.get("repository", "unknown image")
    tag = data.get("tag")
    digest = data.get("digest")
    image = f"{repository}:{tag}" if tag else repository
    return f"DockerHub image evidence: {image} digest={digest or 'unknown'}"


def _unique_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        key = _stable_hash(
            {
                "tool_server": tool_call.get("tool_server"),
                "tool_name": tool_call.get("tool_name"),
                "parameters": tool_call.get("parameters"),
                "status": tool_call.get("status"),
                "error": tool_call.get("error"),
            }
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(tool_call)
    return unique


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from temporalio import activity

from airp.agents.factory import build_default_agent_supervisor
from airp.db.models.catalog import RuntimeWorkload, ServiceCatalog
from airp.db.session import AsyncSessionLocal
from airp.domain.enums import IncidentStatus, RiskLevel
from airp.schemas.incidents import (
    DocumentationReportCreate,
    EvidenceItemCreate,
    IncidentEmbeddingCreate,
    IncidentEventCreate,
    IncidentSignal,
    ModelCallCreate,
    RCAHypothesisCreate,
    RemediationPlanCreate,
)
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
    evidence_ids_by_type: dict[str, str] = {}
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
        evidence_ids_by_type[evidence_type] = evidence.id

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
        event_type = _tool_call_event_type(tool_call)
        if event_type:
            await service.add_event(
                incident_id,
                IncidentEventCreate(
                    event_type=event_type,
                    producer="langgraph.rca",
                    payload={
                        "tool_server": tool_call.get("tool_server"),
                        "tool_name": tool_call.get("tool_name"),
                        "status": tool_call.get("status"),
                        "result_summary": tool_call.get("result_summary"),
                        "error": tool_call.get("error"),
                    },
                ),
            )

    for model_call in state.get("model_calls", []):
        await service.add_model_call(
            incident_id,
            ModelCallCreate(
                model_name=model_call.get("model_name", "unknown"),
                prompt_template_version=model_call.get("prompt_template_version"),
                prompt_tokens=model_call.get("prompt_tokens"),
                completion_tokens=model_call.get("completion_tokens"),
                latency_ms=model_call.get("latency_ms"),
                response_hash=model_call.get("response_hash"),
                validation_result=model_call.get("validation_result") or {},
            ),
        )

    hypothesis_ids = []
    model_name = _rca_model_name(state)
    for hypothesis in state.get("rca_hypotheses", []):
        supporting_evidence = _supporting_evidence_payload(
            hypothesis,
            evidence_ids_by_type,
        )
        stored = await service.add_rca_hypothesis(
            incident_id,
            RCAHypothesisCreate(
                rank=hypothesis.get("rank", 1),
                hypothesis=hypothesis.get("hypothesis", "RCA hypothesis unavailable."),
                confidence=hypothesis.get("confidence", 0.0),
                supporting_evidence=supporting_evidence,
                contradicting_evidence={
                    "items": hypothesis.get("contradictions", []),
                },
                model_name=model_name,
            ),
        )
        hypothesis_ids.append(stored.id)

    if evidence_ids:
        bundle_with_ids = dict(bundle)
        bundle_with_ids["evidence_item_ids"] = evidence_ids_by_type
        await service.add_event(
            incident_id,
            IncidentEventCreate(
                event_type="rca.evidence.persisted",
                producer="langgraph.rca",
                payload={
                    "evidence_ids": evidence_ids,
                    "evidence_ids_by_type": evidence_ids_by_type,
                    "evidence_bundle": bundle_with_ids,
                },
            ),
        )
    if hypothesis_ids:
        await service.add_event(
            incident_id,
            IncidentEventCreate(
                event_type="rca.hypotheses.persisted",
                producer="langgraph.rca",
                payload={"hypothesis_ids": hypothesis_ids},
            ),
        )

    await _persist_remediation_output(service, incident_id, state)
    await _persist_documentation_output(service, incident_id, state)
    await _persist_embedding_output(service, incident_id, state)


async def _persist_remediation_output(
    service: IncidentService, incident_id: str, state: dict[str, Any]
) -> None:
    remediation = state.get("remediation_result") or {}
    if not remediation:
        return

    plan_hash = _stable_hash(remediation)
    existing_plans = await service.list_remediation_plans(incident_id, limit=100)
    for plan in existing_plans:
        metadata = plan.extra or {}
        if (
            metadata.get("source") == "langgraph.remediation"
            and metadata.get("state_hash") == plan_hash
        ):
            return

    risk_level = _risk_level(remediation.get("risk_level"))
    plan = await service.create_remediation_plan(
        incident_id,
        RemediationPlanCreate(
            plan_summary=remediation.get(
                "plan_summary",
                "Remediation plan was unavailable from agent output.",
            ),
            risk_level=risk_level,
            test_plan=remediation.get("test_plan"),
            rollback_plan=remediation.get("rollback_plan"),
            approval_required=bool(remediation.get("approval_required", True)),
            metadata={
                "source": "langgraph.remediation",
                "state_hash": plan_hash,
                "risk_score": remediation.get("risk_score"),
                "blocked_path_findings": remediation.get("blocked_path_findings", []),
                "recommended_actions": remediation.get("recommended_actions", []),
                "evidence_refs": remediation.get("evidence_refs", []),
                "external_writes_allowed": remediation.get(
                    "external_writes_allowed", False
                ),
                "pr_creation_recommended": remediation.get(
                    "pr_creation_recommended", False
                ),
                "confidence": remediation.get("confidence"),
            },
        ),
    )
    await service.add_event(
        incident_id,
        IncidentEventCreate(
            event_type="remediation.plan.persisted",
            producer="langgraph.remediation",
            payload={
                "remediation_plan_id": plan.id,
                "risk_level": plan.risk_level,
                "approval_required": plan.approval_required,
                "external_writes_allowed": remediation.get(
                    "external_writes_allowed", False
                ),
            },
        ),
    )


async def _persist_documentation_output(
    service: IncidentService, incident_id: str, state: dict[str, Any]
) -> None:
    report = state.get("documentation_report") or {}
    if not report:
        return

    report_hash = _stable_hash(report)
    existing_reports = await service.list_documentation_reports(incident_id, limit=100)
    for existing in existing_reports:
        metadata = existing.extra or {}
        if (
            metadata.get("source") == "langgraph.documentation"
            and metadata.get("state_hash") == report_hash
        ):
            return

    stored = await service.create_documentation_report(
        incident_id,
        DocumentationReportCreate(
            title=report.get("title") or f"RCA Draft: {incident_id}",
            status=report.get("status") or "draft",
            executive_summary=report.get("executive_summary")
            or "Documentation draft executive summary is unavailable.",
            root_cause_summary=report.get("root_cause_summary")
            or "Root cause summary is unavailable.",
            impact_summary=report.get("impact_summary")
            or "Impact summary is unavailable.",
            evidence_summary=report.get("evidence_summary")
            or "Evidence summary is unavailable.",
            remediation_summary=report.get("remediation_summary")
            or "Remediation summary is unavailable.",
            follow_up_tasks=list(report.get("follow_up_tasks") or []),
            source_refs=list(report.get("source_refs") or []),
            publish_recommended=bool(report.get("publish_recommended", False)),
            publishing_enabled=bool(report.get("publishing_enabled", False)),
            published_url=report.get("published_url"),
            confidence=_confidence(report.get("confidence")),
            metadata={
                "source": "langgraph.documentation",
                "state_hash": report_hash,
                "publishing_enabled": report.get("publishing_enabled", False),
                "publish_recommended": report.get("publish_recommended", False),
            },
        ),
    )
    await service.add_event(
        incident_id,
        IncidentEventCreate(
            event_type="documentation.report.persisted",
            producer="langgraph.documentation",
            payload={
                "documentation_report_id": stored.id,
                "status": stored.status,
                "publish_recommended": stored.publish_recommended,
                "publishing_enabled": stored.publishing_enabled,
            },
        ),
    )


async def _persist_embedding_output(
    service: IncidentService, incident_id: str, state: dict[str, Any]
) -> None:
    texts = state.get("embedding_texts") or []
    if not isinstance(texts, list) or not texts:
        return

    vectors = state.get("embedding_vectors") or []
    existing_embeddings = await service.list_incident_embeddings(incident_id, limit=500)
    existing_keys = {
        _embedding_key(existing.embedding_type, existing.text)
        for existing in existing_embeddings
    }
    stored_ids: list[str] = []
    skipped_duplicates = 0

    for index, text_value in enumerate(texts):
        text = str(text_value).strip()
        if not text:
            continue
        embedding_type = "langgraph.graph_text"
        key = _embedding_key(embedding_type, text)
        if key in existing_keys:
            skipped_duplicates += 1
            continue
        vector = _embedding_vector(vectors, index)
        stored = await service.create_incident_embedding(
            incident_id,
            IncidentEmbeddingCreate(
                embedding_type=embedding_type,
                text=text,
                vector=vector,
            ),
        )
        stored_ids.append(stored.id)
        existing_keys.add(key)

    if stored_ids or skipped_duplicates:
        await service.add_event(
            incident_id,
            IncidentEventCreate(
                event_type="embedding.records.persisted",
                producer="langgraph.embedding",
                payload={
                    "embedding_ids": stored_ids,
                    "stored_count": len(stored_ids),
                    "skipped_duplicate_count": skipped_duplicates,
                    "source_text_count": len(texts),
                    "source_vector_count": len(vectors) if isinstance(vectors, list) else 0,
                },
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
    candidate_conditions = []
    if namespace and pod_name:
        candidate_conditions.append(
            (
                RuntimeWorkload.namespace == namespace,
                RuntimeWorkload.pod_name == pod_name,
            )
        )
    if pod_name:
        candidate_conditions.append((RuntimeWorkload.pod_name == pod_name,))
    if service_id:
        candidate_conditions.append((RuntimeWorkload.service_id == service_id,))
    if namespace:
        candidate_conditions.append((RuntimeWorkload.namespace == namespace,))

    workload = None
    for conditions in candidate_conditions:
        stmt = select(RuntimeWorkload).where(*conditions).limit(1)
        workload = await session.scalar(stmt)
        if workload is not None:
            break

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


def _tool_call_event_type(tool_call: dict[str, Any]) -> str | None:
    status = tool_call.get("status")
    if status in {"unavailable", "forbidden", "timeout", "partial"}:
        return f"rca.evidence_collection.{status}"
    return None


def _supporting_evidence_payload(
    hypothesis: dict[str, Any], evidence_ids_by_type: dict[str, str]
) -> dict[str, Any]:
    refs = list(hypothesis.get("supporting_evidence_refs", []))
    existing_ids = list(hypothesis.get("supporting_evidence_ids", []))
    stored_ids = [
        evidence_ids_by_type[ref]
        for ref in refs
        if isinstance(ref, str) and ref in evidence_ids_by_type
    ]
    return {
        "refs": refs,
        "ids": list(dict.fromkeys([*existing_ids, *stored_ids])),
        "next_actions": hypothesis.get("next_actions", []),
    }


def _rca_model_name(state: dict[str, Any]) -> str | None:
    for model_call in state.get("model_calls", []):
        model_name = model_call.get("model_name")
        if isinstance(model_name, str) and model_name:
            return model_name
    return None


def _risk_level(value: Any) -> RiskLevel:
    try:
        return RiskLevel(str(value))
    except ValueError:
        return RiskLevel.MEDIUM


def _confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(confidence, 0.0), 1.0)


def _embedding_key(embedding_type: str, text: str) -> str:
    return _stable_hash({"embedding_type": embedding_type, "text": text})


def _embedding_vector(vectors: Any, index: int) -> list[float] | None:
    if not isinstance(vectors, list) or index >= len(vectors):
        return None
    vector = vectors[index]
    if not isinstance(vector, list):
        return None
    try:
        return [float(value) for value in vector]
    except (TypeError, ValueError):
        return None


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

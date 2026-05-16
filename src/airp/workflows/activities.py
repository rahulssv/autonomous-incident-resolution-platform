from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from temporalio import activity

from airp.agents.factory import build_default_agent_supervisor
from airp.core.allowlists import is_github_repository_allowed
from airp.core.config import Settings, get_settings
from airp.core.policy import ExternalActionPolicy
from airp.db.models.catalog import RuntimeWorkload, ServiceCatalog
from airp.db.models.incident import EvidenceItem, Incident
from airp.db.session import AsyncSessionLocal
from airp.domain.enums import IncidentStatus, RiskLevel
from airp.integrations.github_mcp.client import GitHubMCPClient
from airp.integrations.slack.client import SlackClient
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


@activity.defn(name="incident_create_github_issue")
async def incident_create_github_issue(incident_id: str) -> dict[str, Any]:
    settings = get_settings()
    policy = ExternalActionPolicy(settings).github_issue_creation()
    async with AsyncSessionLocal() as session:
        service = IncidentService(session)
        incident = await service.get_incident(incident_id)

        if not policy.allowed:
            await _record_external_action_skipped(
                service,
                incident_id,
                "github.issue.skipped",
                policy.reason,
            )
            return {"status": "skipped", "reason": policy.reason}

        repository_url = await _github_repository_for_incident(session, incident, settings)
        if not repository_url:
            reason = "No GitHub repository could be resolved for this incident"
            await _record_external_action_failed(
                service,
                incident_id,
                "github.issue.failed",
                reason,
            )
            return {"status": "failed", "reason": reason}

        if not is_github_repository_allowed(
            repository_url,
            settings.github_mcp_repository_allowlist,
        ):
            reason = "Resolved GitHub repository is outside the configured allowlist"
            await _record_external_action_failed(
                service,
                incident_id,
                "github.issue.failed",
                reason,
                {"repository_url": repository_url},
            )
            return {"status": "failed", "reason": reason, "repository_url": repository_url}

        client = GitHubMCPClient(
            transport=settings.github_mcp_transport,
            endpoint_url=str(settings.github_mcp_url) if settings.github_mcp_url else None,
            timeout_seconds=settings.github_mcp_read_timeout_seconds,
        )
        marker = f"AIRP-INCIDENT-ID-{incident_id}"
        labels = ["airp", "incident", f"severity:{incident.severity}"]
        title = _github_issue_title(incident, marker)
        body = await _github_issue_body(service, incident, marker)

        try:
            existing = await client.lookup_issue_by_idempotency_marker(repository_url, marker)
            issue = existing or await client.create_issue(
                repository_url,
                title,
                body,
                labels=labels,
            )
            issue_url = _github_issue_url(issue)
            if not issue_url:
                raise ValueError("GitHub MCP issue response did not include an issue URL")

            external_id = _github_issue_number(issue)
            await service.add_tool_call(
                incident_id,
                tool_server="github_mcp",
                tool_name="github.create_issue",
                parameters={
                    "repository_url": repository_url,
                    "title": title,
                    "labels": labels,
                    "idempotency_marker": marker,
                },
                result={
                    "status": "existing" if existing else "created",
                    "issue_url": issue_url,
                    "external_id": external_id,
                },
            )
            await service.record_github_issue(
                incident_id,
                repository_url=repository_url,
                artifact_url=issue_url,
                external_id=external_id,
                metadata={
                    "title": title,
                    "labels": labels,
                    "idempotency_marker": marker,
                    "existing": bool(existing),
                },
            )
            return {
                "status": "created",
                "repository_url": repository_url,
                "issue_url": issue_url,
                "external_id": external_id,
                "existing": bool(existing),
            }
        except Exception as exc:  # noqa: BLE001 - external action failure is recorded
            error = _safe_error(exc)
            await service.add_tool_call(
                incident_id,
                tool_server="github_mcp",
                tool_name="github.create_issue",
                parameters={
                    "repository_url": repository_url,
                    "title": title,
                    "labels": labels,
                    "idempotency_marker": marker,
                },
                result={"status": "failed"},
                error=error,
            )
            await _record_external_action_failed(
                service,
                incident_id,
                "github.issue.failed",
                error,
                {"repository_url": repository_url},
            )
            return {"status": "failed", "reason": error, "repository_url": repository_url}


@activity.defn(name="incident_send_slack_notification")
async def incident_send_slack_notification(incident_id: str) -> dict[str, Any]:
    settings = get_settings()
    policy = ExternalActionPolicy(settings).slack_notification()
    async with AsyncSessionLocal() as session:
        service = IncidentService(session)
        incident = await service.get_incident(incident_id)

        if not policy.allowed:
            await _record_external_action_skipped(
                service,
                incident_id,
                "slack.notification.skipped",
                policy.reason,
            )
            return {"status": "skipped", "reason": policy.reason}

        channel = await _slack_channel_for_incident(session, incident, settings)
        payload = await _slack_notification_payload(service, incident, channel)
        client = SlackClient(settings)

        try:
            result = await client.send_incident_notification(channel, payload)
            persisted_payload = {
                "text": payload.get("text"),
                "blocks": payload.get("blocks"),
                "github_issue_url": incident.github_issue_url,
            }
            message = await service.record_slack_message(
                incident_id,
                channel=channel,
                message_ts=_string_or_none(result.get("message_ts")),
                thread_ts=_string_or_none(result.get("thread_ts")),
                message_url=_string_or_none(result.get("message_url")),
                payload=persisted_payload,
            )
            return {
                "status": "sent",
                "channel": channel,
                "slack_message_id": message.id,
                "status_code": result.get("status_code"),
            }
        except Exception as exc:  # noqa: BLE001 - external action failure is recorded
            error = _safe_error(exc)
            await _record_external_action_failed(
                service,
                incident_id,
                "slack.notification.failed",
                error,
                {"channel": channel},
            )
            return {"status": "failed", "reason": error, "channel": channel}


async def _github_repository_for_incident(
    session,
    incident: Incident,
    settings: Settings,
) -> str | None:
    if incident.service_id:
        service = await session.get(ServiceCatalog, incident.service_id)
        if service and service.repository_url:
            return service.repository_url

    stmt = (
        select(EvidenceItem)
        .where(EvidenceItem.incident_id == incident.id, EvidenceItem.evidence_type == "github")
        .order_by(EvidenceItem.created_at.desc())
        .limit(1)
    )
    github_evidence = await session.scalar(stmt)
    evidence_data = github_evidence.data if github_evidence else {}
    repository_url = _repository_from_payload(evidence_data)
    if repository_url:
        return repository_url

    metadata = incident.extra or {}
    repository_url = _repository_from_payload(metadata)
    if repository_url:
        return repository_url

    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    service_name = _first_string(
        metadata.get("service"),
        labels.get("service"),
        labels.get("app"),
        labels.get("deployment"),
    )
    if service_name:
        return f"https://github.com/{settings.client_github_org}/{service_name}"
    return None


async def _slack_channel_for_incident(
    session,
    incident: Incident,
    settings: Settings,
) -> str:
    if incident.service_id:
        service = await session.get(ServiceCatalog, incident.service_id)
        if service and service.slack_channel:
            return service.slack_channel
    return settings.slack_default_channel


async def _github_issue_body(
    service: IncidentService,
    incident: Incident,
    marker: str,
) -> str:
    hypotheses = await service.list_rca_hypotheses(incident.id, limit=3)
    remediation_plans = await service.list_remediation_plans(incident.id, limit=2)
    reports = await service.list_documentation_reports(incident.id, limit=1)
    evidence_items = await service.list_evidence(incident.id, limit=5)
    events = await service.get_events(incident.id, limit=12)

    lines = [
        f"<!-- {marker} -->",
        "# AIRP Incident RCA",
        "",
        "## Incident",
        f"- Incident ID: `{incident.id}`",
        f"- Severity: `{incident.severity}`",
        f"- Environment: `{incident.environment}`",
        f"- Namespace: `{incident.namespace or 'unknown'}`",
        f"- Pod: `{incident.pod_name or 'unknown'}`",
        f"- Correlation ID: `{incident.correlation_id or 'unknown'}`",
        f"- Title: {_truncate(incident.title, 220)}",
    ]
    if incident.description:
        lines.extend(["", "## Description", _truncate(incident.description, 2000)])

    lines.extend(["", "## Root Cause Hypotheses"])
    if hypotheses:
        for hypothesis in hypotheses:
            lines.append(
                "- "
                f"Rank {hypothesis.rank}, confidence {hypothesis.confidence:.2f}: "
                f"{_truncate(hypothesis.hypothesis, 800)}"
            )
    else:
        lines.append("- No persisted hypothesis was available.")

    lines.extend(["", "## Evidence"])
    if evidence_items:
        for evidence in evidence_items:
            lines.append(
                "- "
                f"{evidence.evidence_type} from {evidence.source}: "
                f"{_truncate(evidence.summary, 500)}"
            )
    else:
        lines.append("- No persisted evidence was available.")

    lines.extend(["", "## Remediation"])
    if remediation_plans:
        for plan in remediation_plans:
            lines.append(
                "- "
                f"Risk {plan.risk_level}, approval_required={plan.approval_required}: "
                f"{_truncate(plan.plan_summary, 800)}"
            )
            if plan.test_plan:
                lines.append(f"  - Test plan: {_truncate(plan.test_plan, 500)}")
            if plan.rollback_plan:
                lines.append(f"  - Rollback plan: {_truncate(plan.rollback_plan, 500)}")
    else:
        lines.append("- No remediation plan was available.")

    if reports:
        report = reports[0]
        lines.extend(
            [
                "",
                "## Post-Mortem Draft",
                f"- Title: {_truncate(report.title, 220)}",
                f"- Summary: {_truncate(report.executive_summary, 800)}",
                f"- Root cause: {_truncate(report.root_cause_summary, 800)}",
            ]
        )

    lines.extend(["", "## Timeline"])
    for event in events:
        lines.append(f"- `{event.created_at.isoformat()}` `{event.event_type}`")

    lines.extend(
        [
            "",
            "## Automation",
            (
                "Created automatically by AIRP after Kafka ingestion, MCP evidence "
                "collection, RCA synthesis, remediation planning, and documentation draft."
            ),
        ]
    )
    return "\n".join(lines)


async def _slack_notification_payload(
    service: IncidentService,
    incident: Incident,
    channel: str,
) -> dict[str, Any]:
    hypotheses = await service.list_rca_hypotheses(incident.id, limit=1)
    remediation_plans = await service.list_remediation_plans(incident.id, limit=1)
    evidence_items = await service.list_evidence(incident.id, limit=3)

    hypothesis = hypotheses[0].hypothesis if hypotheses else "No RCA hypothesis persisted."
    remediation = (
        remediation_plans[0].plan_summary
        if remediation_plans
        else "No remediation plan persisted."
    )
    issue_link = (
        f"<{incident.github_issue_url}|GitHub issue>"
        if incident.github_issue_url
        else "GitHub issue unavailable"
    )
    evidence_summary = "; ".join(
        f"{item.evidence_type}: {_truncate(item.summary, 160)}" for item in evidence_items
    )
    if not evidence_summary:
        evidence_summary = "No evidence summary available."

    text = (
        f"AIRP incident {incident.id} RCA ready: {incident.title}. "
        f"Issue: {incident.github_issue_url or 'unavailable'}"
    )
    return {
        "text": _truncate(text, 2000),
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": _truncate(f"AIRP {incident.severity.upper()} incident", 140),
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident*\n`{incident.id}`"},
                    {"type": "mrkdwn", "text": f"*Channel*\n`{channel}`"},
                    {"type": "mrkdwn", "text": f"*Service*\n`{_incident_service_name(incident)}`"},
                    {"type": "mrkdwn", "text": f"*Issue*\n{issue_link}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*RCA*\n{_truncate(hypothesis, 2800)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Remediation*\n{_truncate(remediation, 1800)}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Evidence:* {_truncate(evidence_summary, 1800)}",
                    }
                ],
            },
        ],
    }


async def _record_external_action_skipped(
    service: IncidentService,
    incident_id: str,
    event_type: str,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await service.add_event(
        incident_id,
        IncidentEventCreate(
            event_type=event_type,
            producer="temporal-workflow",
            payload={"reason": reason, **(payload or {})},
        ),
    )


async def _record_external_action_failed(
    service: IncidentService,
    incident_id: str,
    event_type: str,
    error: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await service.add_event(
        incident_id,
        IncidentEventCreate(
            event_type=event_type,
            producer="temporal-workflow",
            payload={"error": _redact_secret_urls(error), **(payload or {})},
        ),
    )


def _github_issue_title(incident: Incident, marker: str) -> str:
    service_name = _incident_service_name(incident)
    suffix = f" [{marker}]"
    base = f"[AIRP][{incident.severity}] {service_name}: {incident.title}"
    return f"{_truncate(base, 240 - len(suffix))}{suffix}"


def _repository_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    return _first_string(
        payload.get("repository_url"),
        payload.get("repo_url"),
        payload.get("repository"),
        payload.get("repo"),
    )


def _incident_service_name(incident: Incident) -> str:
    metadata = incident.extra or {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    return (
        _first_string(
            metadata.get("service"),
            labels.get("service"),
            labels.get("app"),
            labels.get("deployment"),
        )
        or "unknown-service"
    )


def _github_issue_url(issue: dict[str, Any]) -> str | None:
    raw = issue.get("raw") if isinstance(issue.get("raw"), dict) else {}
    return _first_string(issue.get("url"), issue.get("html_url"), raw.get("html_url"))


def _github_issue_number(issue: dict[str, Any]) -> str | None:
    value = issue.get("number")
    return str(value) if value is not None else None


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_error(exc: Exception) -> str:
    message = _redact_secret_urls(str(exc))
    return _truncate(f"{exc.__class__.__name__}: {message}", 500)


def _redact_secret_urls(value: str) -> str:
    return re.sub(
        r"https://hooks\.slack\.com/services/[^\s)]+",
        "https://hooks.slack.com/services/[redacted]",
        value,
    )


def _truncate(value: Any, max_length: int) -> str:
    text = str(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


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

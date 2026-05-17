from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from .airp_client import get_airp_client
from .config import settings
from .graph_service import GRAPH_STAGES, sse_event

logger = logging.getLogger(__name__)

PRODUCER_TO_STAGE = {
    "langgraph.monitoring": "monitoring",
    "langgraph.correlation": "correlation",
    "langgraph.rca": "rca",
    "langgraph.remediation": "remediation",
    "langgraph.documentation": "documentation",
    "langgraph.embedding": "embedding",
}

STAGE_LABEL = {stage["id"]: stage["label"] for stage in GRAPH_STAGES}

STATUS_TO_CURRENT_STAGE = {
    "received": "monitoring",
    "validated": "monitoring",
    "correlated": "correlation",
    "image_correlated": "correlation",
    "rca_collecting_k8s_evidence": "rca",
    "rca_collecting_github_evidence": "rca",
    "rca_in_progress": "rca",
    "rca_issue_created": "rca",
    "slack_notified": "rca",
    "remediation_planned": "remediation",
    "waiting_for_approval": "remediation",
    "approved": "remediation",
    "pr_created": "remediation",
    "ci_validating": "remediation",
    "documenting": "documentation",
    "closed": "embedding",
    "escalated": "embedding",
}

TERMINAL_STATUSES = {"closed", "escalated"}

STAGE_ORDER = [stage["id"] for stage in GRAPH_STAGES]


def _derive_scenario(incident: dict[str, Any]) -> str:
    title = (incident.get("title") or "").lower()
    if "crashloop" in title or "backoff" in title:
        return "crashloop"
    if "oom" in title or "outofmemory" in title or "out of memory" in title:
        return "oom"
    if "latency" in title or "timeout" in title or "slow" in title:
        return "latency"
    return "crashloop"


def _humanize_status(status: str) -> str:
    return status.replace("_", " ").title() if status else "Unknown"


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "Unknown confidence"
    if value >= 0.75:
        return "High confidence"
    if value >= 0.4:
        return "Medium confidence"
    return "Low confidence"


def _find_event(
    events: list[dict[str, Any]],
    producer: str,
    event_type: str | None = None,
) -> dict[str, Any] | None:
    for event in events:
        if event.get("producer") != producer:
            continue
        if event_type and event.get("event_type") != event_type:
            continue
        return event
    return None


def _agent_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if (e.get("producer") or "").startswith("langgraph.")]


def _completed_stages_from_audit(events: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for event in _agent_events(events):
        stage = PRODUCER_TO_STAGE.get(event.get("producer", ""))
        if stage and stage not in seen:
            seen.append(stage)
    return seen


def _current_stage(status: str, completed: list[str]) -> str:
    if len(completed) >= len(STAGE_ORDER):
        return STAGE_ORDER[-1]
    if completed:
        last_idx = STAGE_ORDER.index(completed[-1]) if completed[-1] in STAGE_ORDER else -1
        if last_idx + 1 < len(STAGE_ORDER):
            return STAGE_ORDER[last_idx + 1]
        return completed[-1]
    return STATUS_TO_CURRENT_STAGE.get(status, STAGE_ORDER[0])


def _derive_signal(incident: dict[str, Any], events: list[dict[str, Any]]) -> str:
    monitoring = _find_event(events, "langgraph.monitoring")
    if monitoring:
        payload = monitoring.get("payload") or {}
        summary = payload.get("summary")
        if summary:
            return summary
    return incident.get("title") or "Incident detected"


def _derive_route(incident: dict[str, Any]) -> str:
    meta = incident.get("metadata") or {}
    return meta.get("source_topic") or "aks.kubeevents.raw"


def _derive_service(incident: dict[str, Any]) -> str:
    return (
        incident.get("service_id")
        or incident.get("namespace")
        or incident.get("pod_name")
        or "unknown"
    )


def _stage_summary(stage_id: str, events: list[dict[str, Any]]) -> str:
    if stage_id == "monitoring":
        event = _find_event(events, "langgraph.monitoring")
        if event:
            return (event.get("payload") or {}).get("summary") or "Monitoring agent assessed the signal."
        return "Monitoring agent assessed the signal."
    if stage_id == "correlation":
        event = _find_event(events, "langgraph.correlation")
        if event:
            return (event.get("payload") or {}).get("context_summary") or "Correlation agent gathered context."
        return "Correlation agent gathered context."
    if stage_id == "rca":
        rca_event = _find_event(events, "langgraph.rca", "rca.started")
        if rca_event:
            return (rca_event.get("payload") or {}).get("summary") or "RCA agent investigating."
        return "RCA agent investigating."
    if stage_id == "remediation":
        event = _find_event(events, "langgraph.remediation")
        if event:
            return (event.get("payload") or {}).get("plan_summary") or "Remediation plan drafted."
        return "Remediation plan drafted."
    if stage_id == "documentation":
        event = _find_event(events, "langgraph.documentation")
        if event:
            return (event.get("payload") or {}).get("executive_summary") or "Incident documentation drafted."
        return "Incident documentation drafted."
    if stage_id == "embedding":
        return "Knowledge captured for future retrieval."
    return "Stage in progress."


def _evidence_from_hypotheses(hypotheses: list[dict[str, Any]]) -> list[str]:
    if not hypotheses:
        return []
    top = hypotheses[0]
    supporting = top.get("supporting_evidence") or {}
    items = supporting.get("items") if isinstance(supporting, dict) else None
    if isinstance(items, list):
        descriptions: list[str] = []
        for item in items:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("source") or item.get("id")
                if desc:
                    descriptions.append(str(desc))
            elif item:
                descriptions.append(str(item))
        if descriptions:
            return descriptions
    return ["KubeEvents", "Container logs", "Recent deployment"]


def _documentation_payload(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    doc_event = _find_event(events, "langgraph.documentation")
    if not doc_event:
        return None
    payload = doc_event.get("payload") or {}
    return {
        "executive_summary": payload.get("executive_summary"),
        "root_cause_summary": payload.get("root_cause_summary"),
        "remediation_summary": payload.get("remediation_summary"),
    }


def _github_issue(incident: dict[str, Any]) -> dict[str, Any] | None:
    url = incident.get("github_issue_url")
    if not url:
        return None
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    repo = None
    number: int | None = None
    if len(parts) >= 4 and parts[2] == "issues":
        repo = f"{parts[0]}/{parts[1]}"
        try:
            number = int(parts[3])
        except ValueError:
            number = None
    return {"repo": repo, "number": number, "url": url}


def _snapshot(
    audit_events: list[dict[str, Any]],
    tool_calls_total: int,
    model_calls_total: int,
) -> dict[str, int]:
    return {
        "agent_event_count": len(_agent_events(audit_events)),
        "tool_call_count": tool_calls_total,
        "model_call_count": model_calls_total,
    }


def _incident_summary(
    incident: dict[str, Any],
    audit_events: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = _completed_stages_from_audit(audit_events)
    current = _current_stage(incident.get("status", ""), completed)
    return {
        "id": incident["id"],
        "title": incident.get("title") or incident["id"],
        "severity": incident.get("severity") or "info",
        "status": _humanize_status(incident.get("status", "")),
        "scenario": _derive_scenario(incident),
        "signal": _derive_signal(incident, audit_events),
        "service": _derive_service(incident),
        "currentStage": current,
        "currentStageLabel": STAGE_LABEL.get(current, current.title()),
        "completedCount": len(completed),
        "totalStages": len(GRAPH_STAGES),
        "updatedAt": incident.get("updated_at") or incident.get("created_at"),
    }


def _incident_detail(
    incident: dict[str, Any],
    audit_events: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    tool_calls_total: int,
    model_calls_total: int,
) -> dict[str, Any]:
    completed = _completed_stages_from_audit(audit_events)
    current = _current_stage(incident.get("status", ""), completed)
    monitoring_event = _find_event(audit_events, "langgraph.monitoring")
    monitoring_payload = (monitoring_event or {}).get("payload") or {}

    return {
        "source": "airp",
        "stages": GRAPH_STAGES,
        "incident": {
            "id": incident["id"],
            "incident_id": incident["id"],
            "title": incident.get("title") or incident["id"],
            "severity": incident.get("severity") or "info",
            "status": _humanize_status(incident.get("status", "")),
            "description": incident.get("description") or "",
            "scenario": _derive_scenario(incident),
            "signal": _derive_signal(incident, audit_events),
            "route": _derive_route(incident),
            "confidence": _confidence_label(monitoring_payload.get("confidence")),
            "service": _derive_service(incident),
            "updatedAt": incident.get("updated_at") or incident.get("created_at"),
            "issueCreated": _github_issue(incident),
        },
        "currentStage": current,
        "currentStageLabel": STAGE_LABEL.get(current, current.title()),
        "completedStages": completed,
        "summary": _stage_summary(current, audit_events),
        "snapshot": _snapshot(audit_events, tool_calls_total, model_calls_total),
        "rca": {
            "hypothesis": hypotheses[0]["hypothesis"] if hypotheses else None,
            "evidence": _evidence_from_hypotheses(hypotheses),
        },
        "documentation": _documentation_payload(audit_events),
    }


def _stage_update_for_event(event: dict[str, Any]) -> dict[str, Any]:
    producer = event.get("producer") or ""
    payload = event.get("payload") or {}
    if producer == "langgraph.rca":
        if event.get("event_type") == "rca.hypotheses.generated":
            return {}
        return {
            "rca_hypotheses": [{"hypothesis": payload.get("summary")}]
            if payload.get("summary")
            else [],
            "rca_evidence_bundle": {
                "evidence_sources": payload.get("evidence_sources") or [],
            },
        }
    if producer == "langgraph.documentation":
        return {
            "documentation_report": {
                "executive_summary": payload.get("executive_summary"),
                "root_cause_summary": payload.get("root_cause_summary"),
                "remediation_summary": payload.get("remediation_summary"),
            }
        }
    return {}


async def list_resolution_incidents(
    limit: int = 30, pool_size: int = 100
) -> dict[str, Any]:
    client = get_airp_client()
    listing = await client.list_incidents(limit=pool_size)
    incidents = listing.get("items", [])

    semaphore = asyncio.Semaphore(20)

    async def _audit_for(incident_id: str) -> list[dict[str, Any]]:
        async with semaphore:
            try:
                response = await client.get_audit(incident_id, limit=200)
                return response.get("items", [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("airp: audit fetch failed for %s: %s", incident_id, exc)
                return []

    audits = await asyncio.gather(
        *(_audit_for(incident["id"]) for incident in incidents),
        return_exceptions=False,
    )
    summaries = [
        _incident_summary(incident, audit) for incident, audit in zip(incidents, audits)
    ]

    # Sort to surface the best demo material first:
    # 1. Fully-resolved runs (completedCount == 6) — rich audit, real LLM output
    # 2. In-flight runs (1..5 stages completed)
    # 3. Queued runs (0 stages) — newest first so users still see fresh ones
    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        completed = item["completedCount"]
        if completed >= len(GRAPH_STAGES):
            tier = 0
        elif completed > 0:
            tier = 1
        else:
            tier = 2
        # Within each tier: more progress first, then newest first.
        return (tier, -completed, "" if item.get("updatedAt") is None else item["updatedAt"])

    summaries.sort(
        key=lambda i: (_sort_key(i)[0], _sort_key(i)[1], -_iso_to_epoch(i.get("updatedAt")))
    )
    return {
        "source": "airp",
        "polling": True,
        "items": summaries[:limit],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _iso_to_epoch(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


async def get_resolution_incident(incident_id: str) -> dict[str, Any] | None:
    client = get_airp_client()
    incident = await client.get_incident(incident_id)
    audit_task = client.get_audit(incident_id, limit=500)
    hypotheses_task = client.get_hypotheses(incident_id)
    tool_calls_task = client.get_tool_calls(incident_id, limit=1)
    model_calls_task = client.get_model_calls(incident_id, limit=1)
    audit_resp, hypotheses_resp, tool_resp, model_resp = await asyncio.gather(
        audit_task, hypotheses_task, tool_calls_task, model_calls_task,
        return_exceptions=True,
    )

    def _items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, Exception):
            return []
        return (value or {}).get("items", [])

    def _total(value: Any) -> int:
        if isinstance(value, Exception):
            return 0
        return (value or {}).get("total", 0)

    audit_events = _items(audit_resp)
    hypotheses = _items(hypotheses_resp)
    tool_calls_total = _total(tool_resp)
    model_calls_total = _total(model_resp)

    return _incident_detail(
        incident, audit_events, hypotheses, tool_calls_total, model_calls_total
    )


def _first_event_per_stage(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return the earliest langgraph event per stage_id."""
    by_stage: dict[str, dict[str, Any]] = {}
    for event in _agent_events(events):
        stage = PRODUCER_TO_STAGE.get(event.get("producer") or "")
        if not stage or stage in by_stage:
            continue
        by_stage[stage] = event
    return by_stage


async def _fetch_artifacts(
    client: Any, incident_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    audit_resp, hypotheses_resp, tool_resp, model_resp = await asyncio.gather(
        client.get_audit(incident_id, limit=500),
        client.get_hypotheses(incident_id),
        client.get_tool_calls(incident_id, limit=1),
        client.get_model_calls(incident_id, limit=1),
        return_exceptions=True,
    )
    audit = audit_resp.get("items", []) if not isinstance(audit_resp, Exception) else []
    hypotheses = (
        hypotheses_resp.get("items", [])
        if not isinstance(hypotheses_resp, Exception)
        else []
    )
    tool_total = tool_resp.get("total", 0) if not isinstance(tool_resp, Exception) else 0
    model_total = (
        model_resp.get("total", 0) if not isinstance(model_resp, Exception) else 0
    )
    return audit, hypotheses, tool_total, model_total


async def stream_incident_resolution(incident_id: str) -> AsyncIterator[str]:
    client = get_airp_client()
    # Let exceptions propagate — the main.py wrapper falls back to demo data when
    # airp is unreachable or doesn't recognize the incident.
    incident = await client.get_incident(incident_id)
    audit_events, hypotheses, tool_calls_total, model_calls_total = await _fetch_artifacts(
        client, incident_id
    )

    def build_detail() -> dict[str, Any]:
        return _incident_detail(
            incident, audit_events, hypotheses, tool_calls_total, model_calls_total
        )

    detail = build_detail()
    yield sse_event(
        "metadata",
        {
            "source": "airp",
            "incident": detail["incident"],
            "scenario": detail["incident"]["scenario"],
            "stages": GRAPH_STAGES,
            "detail": detail,
        },
    )
    await asyncio.sleep(0.2)
    yield sse_event(
        "run_started",
        {
            "summary": "Replaying agent events from airp.",
            "currentStage": detail["currentStage"],
            "snapshot": detail["snapshot"],
        },
    )

    emitted_stages: set[str] = set()

    async def emit_stage(stage_id: str, event: dict[str, Any]) -> AsyncIterator[str]:
        if stage_id in emitted_stages or stage_id not in STAGE_ORDER:
            return
        emitted_stages.add(stage_id)
        idx = STAGE_ORDER.index(stage_id)
        next_stage = STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None
        await asyncio.sleep(0.45)
        yield sse_event(
            "stage_completed",
            {
                "source": "airp",
                "incidentId": incident_id,
                "stage": stage_id,
                "nextStage": next_stage,
                "summary": _stage_summary(stage_id, audit_events),
                "snapshot": _snapshot(audit_events, tool_calls_total, model_calls_total),
                "update": _stage_update_for_event(event),
                "detail": build_detail(),
            },
        )

    # Replay in canonical stage order using the earliest event for each stage.
    stage_to_event = _first_event_per_stage(audit_events)
    for stage_id in STAGE_ORDER:
        event = stage_to_event.get(stage_id)
        if event is None:
            continue
        async for chunk in emit_stage(stage_id, event):
            yield chunk

    incident_status = incident.get("status", "")
    all_stages_done = len(emitted_stages) == len(STAGE_ORDER)

    if incident_status in TERMINAL_STATUSES or all_stages_done:
        yield sse_event(
            "run_completed",
            {
                "summary": "Resolution completed.",
                "incidentId": incident_id,
                "issueCreated": _github_issue(incident),
                "snapshot": _snapshot(audit_events, tool_calls_total, model_calls_total),
                "detail": build_detail(),
            },
        )
        return

    poll_interval = settings.airp_stream_poll_interval_seconds
    max_iters = settings.airp_stream_poll_max_iterations

    for _ in range(max_iters):
        await asyncio.sleep(poll_interval)
        try:
            latest_audit, latest_state, latest_hypos = await asyncio.gather(
                client.get_audit(incident_id, limit=500),
                client.get_workflow_state(incident_id),
                client.get_hypotheses(incident_id),
                return_exceptions=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("airp: poll error for %s: %s", incident_id, exc)
            continue

        if not isinstance(latest_audit, Exception):
            audit_events = latest_audit.get("items", audit_events)
        if not isinstance(latest_hypos, Exception):
            hypotheses = latest_hypos.get("items", hypotheses)

        stage_to_event = _first_event_per_stage(audit_events)
        for stage_id in STAGE_ORDER:
            event = stage_to_event.get(stage_id)
            if event is None or stage_id in emitted_stages:
                continue
            async for chunk in emit_stage(stage_id, event):
                yield chunk

        status_now = (
            latest_state.get("incident_status")
            if not isinstance(latest_state, Exception) and latest_state
            else incident_status
        )
        all_stages_done = len(emitted_stages) == len(STAGE_ORDER)
        if status_now in TERMINAL_STATUSES or all_stages_done:
            try:
                incident = await client.get_incident(incident_id)
            except Exception:  # noqa: BLE001
                pass
            yield sse_event(
                "run_completed",
                {
                    "summary": "Resolution completed.",
                    "incidentId": incident_id,
                    "issueCreated": _github_issue(incident),
                    "snapshot": _snapshot(
                        audit_events, tool_calls_total, model_calls_total
                    ),
                    "detail": build_detail(),
                },
            )
            return

    yield sse_event(
        "run_completed",
        {
            "summary": "Incident is still in progress; reconnect to continue.",
            "incidentId": incident_id,
            "snapshot": _snapshot(audit_events, tool_calls_total, model_calls_total),
            "detail": build_detail(),
        },
    )

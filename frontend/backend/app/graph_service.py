from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from . import airp_db


GRAPH_STAGES = [
    {"id": "monitoring", "label": "Monitoring", "agent": "Monitoring Agent"},
    {"id": "correlation", "label": "Correlation", "agent": "Correlation Agent"},
    {"id": "rca", "label": "RCA", "agent": "RCA Agent"},
    {"id": "remediation", "label": "Remediation", "agent": "Remediation Agent"},
    {"id": "documentation", "label": "Documentation", "agent": "Documentation Agent"},
    {"id": "embedding", "label": "Knowledge Capture", "agent": "Documentation Memory"},
]

SCENARIO_DETAILS = {
    "crashloop": {
        "signal": "CrashLoopBackOff",
        "route": "aks.kubeevents.raw",
        "confidence": "High confidence",
        "source": "KubeEvents reported BackOff and repeated container restarts.",
        "service": "payment service",
        "hypothesis": "A deployment change introduced an invalid startup configuration, causing repeated container restarts.",
    },
    "oom": {
        "signal": "OOMKilled",
        "route": "aks.kubeevents.raw",
        "confidence": "High confidence",
        "source": "KubeEvents reported container termination due to memory pressure.",
        "service": "checkout worker",
        "hypothesis": "The workload memory limit is below the current runtime demand after recent traffic growth.",
    },
    "latency": {
        "signal": "Latency spike",
        "route": "aks.containerlogs.raw",
        "confidence": "Medium confidence",
        "source": "Application logs reported timeout errors above the service SLO.",
        "service": "orders API",
        "hypothesis": "Downstream dependency saturation is causing request queues and elevated response time.",
    },
}

DUMMY_GRAPH_INCIDENTS = [
    {
        "id": "LG-1001",
        "scenario": "crashloop",
        "title": "CrashLoopBackOff in payment service",
        "severity": "critical",
        "status": "RCA running",
        "currentStage": "rca",
        "completedStages": ["monitoring", "correlation"],
        "metrics": {"agent_event_count": 4, "tool_call_count": 3, "model_call_count": 2},
        "updatedAt": "2026-05-17T09:42:00Z",
        "state": "unresolved",
        "issueCreated": None,
    },
    {
        "id": "LG-1002",
        "scenario": "oom",
        "title": "OOMKilled in checkout worker",
        "severity": "warning",
        "status": "Correlating signals",
        "currentStage": "correlation",
        "completedStages": ["monitoring"],
        "metrics": {"agent_event_count": 2, "tool_call_count": 1, "model_call_count": 1},
        "updatedAt": "2026-05-17T09:39:00Z",
        "state": "unresolved",
        "issueCreated": None,
    },
    {
        "id": "LG-1003",
        "scenario": "latency",
        "title": "Latency spike in orders API",
        "severity": "info",
        "status": "Monitoring",
        "currentStage": "monitoring",
        "completedStages": [],
        "metrics": {"agent_event_count": 1, "tool_call_count": 0, "model_call_count": 0},
        "updatedAt": "2026-05-17T09:35:00Z",
        "state": "unresolved",
        "issueCreated": None,
    },
]


def stage_summary(stage_id: str, details: dict[str, str]) -> str:
    summaries = {
        "monitoring": f"{details['signal']} matched incident detection policy from {details['route']}.",
        "correlation": "Related logs, deployment changes, and service metadata were grouped into one incident context.",
        "rca": details["hypothesis"],
        "remediation": "A remediation path was selected and prepared for review.",
        "documentation": "The incident record was drafted with root cause, impact, and remediation summary.",
        "embedding": "Resolution knowledge was prepared for future retrieval.",
    }
    return summaries.get(stage_id, "Stage completed.")


def sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def list_resolution_incidents() -> dict[str, Any]:
    real_rows = await airp_db.list_recent_incidents(limit=25)
    real_items: list[dict[str, Any]] = []
    for row in real_rows:
        events = await airp_db.fetch_events(str(row["id"]))
        real_items.append(_real_incident_summary(row, events))

    dummy_items = [
        _incident_summary(record)
        for record in DUMMY_GRAPH_INCIDENTS
        if record.get("state") == "unresolved"
    ]

    items = real_items + dummy_items
    if real_items and dummy_items:
        source = "mixed"
    elif real_items:
        source = "airp-backend"
    else:
        source = "langgraph-demo"

    return {
        "source": source,
        "polling": True,
        "items": items,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


async def get_resolution_incident(incident_id: str) -> dict[str, Any] | None:
    real = await airp_db.fetch_incident(incident_id)
    if real:
        events = await airp_db.fetch_events(incident_id)
        return _real_incident_detail(real, events)

    record = _find_record(incident_id)
    if not record:
        return None
    return _incident_detail(record)


async def stream_incident_resolution(incident_id: str) -> AsyncIterator[str]:
    real = await airp_db.fetch_incident(incident_id)
    if real:
        events = await airp_db.fetch_events(incident_id)
        async for chunk in _stream_real_incident(real, events):
            yield chunk
        return

    record = _find_record(incident_id)
    if not record:
        yield sse_event("resolution_error", {"error": "Incident not found."})
        return

    detail = _incident_detail(record)
    yield sse_event(
        "metadata",
        {
            "source": "langgraph-demo",
            "incident": detail["incident"],
            "scenario": record["scenario"],
            "stages": GRAPH_STAGES,
            "detail": detail,
        },
    )
    await asyncio.sleep(0.2)

    yield sse_event(
        "run_started",
        {
            "summary": "LangGraph node execution resumed for selected incident.",
            "currentStage": record["currentStage"],
            "snapshot": record["metrics"],
        },
    )

    start_index = _stage_index(record["currentStage"])
    for index in range(start_index, len(GRAPH_STAGES)):
        stage = GRAPH_STAGES[index]
        next_stage = GRAPH_STAGES[index + 1]["id"] if index + 1 < len(GRAPH_STAGES) else None
        await asyncio.sleep(0.65)
        _complete_stage(record, stage["id"], next_stage)
        details = SCENARIO_DETAILS.get(record["scenario"], SCENARIO_DETAILS["crashloop"])

        yield sse_event(
            "stage_completed",
            {
                "source": "langgraph-demo",
                "incidentId": record["id"],
                "stage": stage["id"],
                "nextStage": next_stage,
                "summary": stage_summary(stage["id"], details),
                "snapshot": record["metrics"],
                "update": _stage_update(stage["id"], details),
                "detail": _incident_detail(record),
            },
        )

    issue = {
        "repo": "air-platform/demo-service",
        "number": int(record["id"].split("-")[-1]),
        "url": f"https://github.com/air-platform/demo-service/issues/{int(record['id'].split('-')[-1])}",
    }
    record["state"] = "resolved"
    record["status"] = "Issue created"
    record["issueCreated"] = issue
    record["updatedAt"] = _now()
    await asyncio.sleep(0.2)
    yield sse_event(
        "run_completed",
        {
            "summary": "Resolution completed and GitHub issue was created.",
            "incidentId": record["id"],
            "issueCreated": issue,
            "snapshot": record["metrics"],
            "detail": _incident_detail(record),
        },
    )


async def stream_demo_resolution(
    scenario: str,
    severity: str,
    title: str | None = None,
) -> AsyncIterator[str]:
    details = SCENARIO_DETAILS.get(scenario, SCENARIO_DETAILS["crashloop"])
    incident = {
        "incident_id": f"INC-{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "title": title or f"{details['signal']} in {details['service']}",
        "severity": severity,
        "status": "Investigating",
        "description": details["source"],
    }

    yield sse_event(
        "metadata",
        {
            "source": "langgraph-demo",
            "incident": incident,
            "scenario": scenario,
            "stages": GRAPH_STAGES,
        },
    )
    await asyncio.sleep(0.2)

    yield sse_event(
        "run_started",
        {
            "summary": "Incident resolution started.",
            "currentStage": GRAPH_STAGES[0]["id"],
            "snapshot": {
                "agent_event_count": 1,
                "tool_call_count": 0,
                "model_call_count": 0,
            },
        },
    )

    for index, stage in enumerate(GRAPH_STAGES):
        next_stage = GRAPH_STAGES[index + 1]["id"] if index + 1 < len(GRAPH_STAGES) else None
        await asyncio.sleep(0.65)
        update: dict[str, Any] = {}
        if stage["id"] == "rca":
            update = {
                "rca_hypotheses": [{"hypothesis": details["hypothesis"]}],
                "rca_evidence_bundle": {
                    "evidence_sources": ["KubeEvents", "Container logs", "Recent deployment"]
                },
            }
        elif stage["id"] == "documentation":
            update = {
                "documentation_report": {
                    "executive_summary": f"{details['signal']} was detected and routed into the incident process.",
                    "root_cause_summary": details["hypothesis"],
                    "remediation_summary": "Agent prepared remediation context and updated the incident record.",
                }
            }

        yield sse_event(
            "stage_completed",
            {
                "source": "langgraph-demo",
                "stage": stage["id"],
                "nextStage": next_stage,
                "summary": stage_summary(stage["id"], details),
                "snapshot": {
                    "agent_event_count": index + 2,
                    "tool_call_count": min(index + 1, 5),
                    "model_call_count": min(index + 1, 4),
                },
                "update": update,
            },
        )

    await asyncio.sleep(0.2)
    yield sse_event(
        "run_completed",
        {
            "summary": "Incident resolution completed.",
            "snapshot": {
                "agent_event_count": len(GRAPH_STAGES) + 2,
                "tool_call_count": 5,
                "model_call_count": 4,
            },
        },
    )


def _find_record(incident_id: str) -> dict[str, Any] | None:
    return next(
        (record for record in DUMMY_GRAPH_INCIDENTS if record["id"].lower() == incident_id.lower()),
        None,
    )


def _stage_index(stage_id: str) -> int:
    return next(
        (index for index, stage in enumerate(GRAPH_STAGES) if stage["id"] == stage_id),
        0,
    )


def _stage_label(stage_id: str) -> str:
    return next(
        (stage["label"] for stage in GRAPH_STAGES if stage["id"] == stage_id),
        stage_id,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _incident_summary(record: dict[str, Any]) -> dict[str, Any]:
    details = SCENARIO_DETAILS.get(record["scenario"], SCENARIO_DETAILS["crashloop"])
    return {
        "id": record["id"],
        "title": record["title"],
        "severity": record["severity"],
        "status": record["status"],
        "scenario": record["scenario"],
        "signal": details["signal"],
        "service": details["service"],
        "currentStage": record["currentStage"],
        "currentStageLabel": _stage_label(record["currentStage"]),
        "completedCount": len(record["completedStages"]),
        "totalStages": len(GRAPH_STAGES),
        "updatedAt": record["updatedAt"],
    }


def _incident_detail(record: dict[str, Any]) -> dict[str, Any]:
    details = SCENARIO_DETAILS.get(record["scenario"], SCENARIO_DETAILS["crashloop"])
    completed = record["completedStages"]
    current_stage = record["currentStage"]
    return {
        "source": "langgraph-demo",
        "stages": GRAPH_STAGES,
        "incident": {
            "id": record["id"],
            "incident_id": record["id"],
            "title": record["title"],
            "severity": record["severity"],
            "status": record["status"],
            "description": details["source"],
            "scenario": record["scenario"],
            "signal": details["signal"],
            "route": details["route"],
            "confidence": details["confidence"],
            "service": details["service"],
            "updatedAt": record["updatedAt"],
            "issueCreated": record.get("issueCreated"),
        },
        "currentStage": current_stage,
        "currentStageLabel": _stage_label(current_stage),
        "completedStages": completed,
        "summary": stage_summary(current_stage, details),
        "snapshot": record["metrics"],
        "rca": {
            "hypothesis": details["hypothesis"] if "rca" in completed or current_stage == "rca" else None,
            "evidence": ["KubeEvents", "Container logs", "Recent deployment"]
            if "rca" in completed or current_stage == "rca"
            else [],
        },
        "documentation": _documentation(details) if "documentation" in completed else None,
    }


def _complete_stage(record: dict[str, Any], stage_id: str, next_stage: str | None) -> None:
    if stage_id not in record["completedStages"]:
        record["completedStages"].append(stage_id)
    record["currentStage"] = next_stage or stage_id
    record["status"] = "Resolving" if next_stage else "Creating GitHub issue"
    record["metrics"] = {
        "agent_event_count": len(record["completedStages"]) + 1,
        "tool_call_count": min(len(record["completedStages"]), 5),
        "model_call_count": min(len(record["completedStages"]), 4),
    }
    record["updatedAt"] = _now()


def _stage_update(stage_id: str, details: dict[str, str]) -> dict[str, Any]:
    if stage_id == "rca":
        return {
            "rca_hypotheses": [{"hypothesis": details["hypothesis"]}],
            "rca_evidence_bundle": {
                "evidence_sources": ["KubeEvents", "Container logs", "Recent deployment"]
            },
        }
    if stage_id == "documentation":
        return {"documentation_report": _documentation(details)}
    return {}


def _documentation(details: dict[str, str]) -> dict[str, str]:
    return {
        "executive_summary": f"{details['signal']} was detected and routed into the incident process.",
        "root_cause_summary": details["hypothesis"],
        "remediation_summary": "Agent prepared remediation context and updated the incident record.",
    }


# --- Real AIRP backend data adapters --------------------------------------

_TERMINAL_INCIDENT_STATUSES = {
    "pr_created",
    "issue_created",
    "resolved",
    "closed",
    "merged",
    "completed",
}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value) if value is not None else _now()


def _status_label(status: str | None, current_stage: str) -> str:
    if not status:
        return _stage_label(current_stage)
    nice = status.replace("_", " ").title()
    return nice


def _real_incident_summary(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    completed, current = airp_db.derive_stage_progress(events)
    status_raw = row.get("status") or ""
    state = "resolved" if status_raw in _TERMINAL_INCIDENT_STATUSES else "unresolved"
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "severity": row["severity"],
        "status": _status_label(status_raw, current),
        "scenario": "real",
        "signal": "AIRP backend incident",
        "service": _service_from_events(events) or "unknown",
        "currentStage": current,
        "currentStageLabel": _stage_label(current),
        "completedCount": len(completed),
        "totalStages": len(GRAPH_STAGES),
        "updatedAt": _iso(row.get("last_activity") or row.get("updated_at") or row.get("created_at")),
        "state": state,
    }


def _service_from_events(events: list[dict[str, Any]]) -> str | None:
    for evt in events:
        if evt["event_type"] == "alert.validated":
            svc = (evt.get("payload") or {}).get("service")
            if svc:
                return svc
        if evt["event_type"] == "correlation.completed":
            svc = (evt.get("payload") or {}).get("service_name")
            if svc:
                return svc
    return None


def _real_incident_detail(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    completed, current = airp_db.derive_stage_progress(events)
    status_raw = row.get("status") or ""

    issue = airp_db.latest_artifact(events, "github.issue.created") or {}
    pr = airp_db.latest_artifact(events, "github.pull_request.created") or {}
    slack = airp_db.latest_artifact(events, "slack.notification.sent") or {}
    rca = airp_db.latest_artifact(events, "rca.hypotheses.generated") or {}
    rca_started = airp_db.latest_artifact(events, "rca.started") or {}
    doc = airp_db.latest_artifact(events, "documentation.drafted") or {}
    remediation = airp_db.latest_artifact(events, "remediation.planned") or {}

    issue_created = (
        {
            "repo": (issue.get("repository_url") or "").rsplit("/", 2)[-2:],
            "number": issue.get("external_id"),
            "url": issue.get("artifact_url"),
        }
        if issue
        else None
    )
    pull_request = (
        {
            "repo": (pr.get("repository_url") or "").rsplit("/", 2)[-2:],
            "number": pr.get("external_id"),
            "url": pr.get("artifact_url"),
            "branch": pr.get("branch"),
            "assignees": pr.get("assignees") or [],
        }
        if pr
        else None
    )

    return {
        "source": "airp-backend",
        "stages": GRAPH_STAGES,
        "incident": {
            "id": str(row["id"]),
            "incident_id": str(row["id"]),
            "title": row["title"],
            "severity": row["severity"],
            "status": _status_label(status_raw, current),
            "description": row.get("description") or "",
            "scenario": "real",
            "signal": "AIRP backend incident",
            "service": _service_from_events(events) or "unknown",
            "updatedAt": _iso(row.get("updated_at") or row.get("created_at")),
            "issueCreated": issue_created,
            "pullRequest": pull_request,
            "slack": slack or None,
        },
        "currentStage": current,
        "currentStageLabel": _stage_label(current),
        "completedStages": completed,
        "summary": _real_summary(current, rca_started, doc, remediation),
        "snapshot": {
            "agent_event_count": len(events),
            "tool_call_count": rca_started.get("tool_call_count") or 0,
            "model_call_count": 0,
        },
        "rca": {
            "hypothesis": (rca_started.get("summary") if rca_started else None),
            "evidence": rca_started.get("evidence_sources") or [],
            "hypothesis_count": rca.get("hypothesis_count"),
            "escalation_required": rca.get("escalation_required"),
        },
        "documentation": doc or None,
        "remediation": remediation or None,
        "timings": _stage_timings_payload(events),
        "workflowDurationMs": _workflow_duration_ms(events),
    }


def _stage_timings_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    raw = _compute_stage_timings(events)
    return {
        stage_id: {
            "started_at": _iso(v["started_at"]),
            "completed_at": _iso(v["completed_at"]),
            "duration_ms": v["duration_ms"],
            "event_count": v["event_count"],
        }
        for stage_id, v in raw.items()
    }


def _workflow_duration_ms(events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    delta = events[-1]["created_at"] - events[0]["created_at"]
    return max(int(delta.total_seconds() * 1000), 0)


def _real_summary(current: str, rca_started: dict, doc: dict, remediation: dict) -> str:
    if current == "monitoring":
        return "Monitoring agent assessing the alert."
    if current == "correlation":
        return "Correlating the alert against service catalog and recent deployments."
    if current == "rca":
        return rca_started.get("summary") or "RCA agent investigating root cause."
    if current == "remediation":
        return remediation.get("plan_summary") or "Remediation agent preparing a fix plan."
    if current == "documentation":
        return doc.get("executive_summary") or "Documentation agent drafting the incident report."
    return "Resolution flow complete."


def _compute_stage_timings(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group events by stage and compute first/last/duration per stage."""
    by_stage: dict[str, dict[str, Any]] = {}
    workflow_start = events[0]["created_at"] if events else None
    for evt in events:
        stage = airp_db.EVENT_TO_STAGE.get(evt["event_type"])
        if not stage:
            continue
        ts = evt["created_at"]
        entry = by_stage.setdefault(stage, {"started_at": ts, "completed_at": ts, "event_count": 0})
        if ts < entry["started_at"]:
            entry["started_at"] = ts
        if ts > entry["completed_at"]:
            entry["completed_at"] = ts
        entry["event_count"] += 1

    # Stage "started" is more accurately the previous stage's completion.
    prev_end = workflow_start
    for stage_id in STAGE_ORDER_FROM_PIPELINE:
        if stage_id in by_stage:
            if prev_end is not None and prev_end < by_stage[stage_id]["completed_at"]:
                by_stage[stage_id]["started_at"] = prev_end
            prev_end = by_stage[stage_id]["completed_at"]

    for stage_id, entry in by_stage.items():
        delta_ms = int((entry["completed_at"] - entry["started_at"]).total_seconds() * 1000)
        entry["duration_ms"] = max(delta_ms, 0)
    return by_stage


STAGE_ORDER_FROM_PIPELINE = [s["id"] for s in GRAPH_STAGES]


_TERMINAL_INCIDENT_STATUSES_LIVE = {"pr_created", "issue_created", "resolved", "closed", "merged", "completed"}

_LIVE_MAX_SECONDS = 360
_LIVE_POLL_INTERVAL = 1.0


def _is_terminal_workflow(row: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    if (row.get("status") or "") in _TERMINAL_INCIDENT_STATUSES_LIVE:
        return True
    emitted = {airp_db.EVENT_TO_STAGE.get(e["event_type"]) for e in events}
    return all(stage in emitted for stage in STAGE_ORDER_FROM_PIPELINE)


async def _stream_real_incident(row: dict[str, Any], events: list[dict[str, Any]]) -> AsyncIterator[str]:
    detail = _real_incident_detail(row, events)
    timings = _compute_stage_timings(events)
    workflow_start = events[0]["created_at"] if events else None
    workflow_end = events[-1]["created_at"] if events else None
    workflow_duration_ms = (
        int((workflow_end - workflow_start).total_seconds() * 1000)
        if workflow_start and workflow_end
        else 0
    )

    incident_id = str(row["id"])
    is_live = not _is_terminal_workflow(row, events)

    yield sse_event(
        "metadata",
        {
            "source": "airp-backend",
            "mode": "live" if is_live else "replay",
            "incident": detail["incident"],
            "scenario": "real",
            "stages": GRAPH_STAGES,
            "detail": detail,
            "timings": {
                k: {
                    "started_at": _iso(v["started_at"]),
                    "completed_at": _iso(v["completed_at"]),
                    "duration_ms": v["duration_ms"],
                    "event_count": v["event_count"],
                }
                for k, v in timings.items()
            },
            "workflow_started_at": _iso(workflow_start) if workflow_start else None,
            "workflow_completed_at": _iso(workflow_end) if workflow_end else None,
            "workflow_duration_ms": workflow_duration_ms,
        },
    )
    await asyncio.sleep(0.1)
    yield sse_event(
        "run_started",
        {
            "summary": (
                "Watching live agent events from AIRP backend."
                if is_live
                else "Replaying agent events from AIRP backend."
            ),
            "mode": "live" if is_live else "replay",
            "currentStage": detail["currentStage"],
            "snapshot": detail["snapshot"],
            "workflow_started_at": _iso(workflow_start) if workflow_start else None,
        },
    )

    emitted_stages: set[str] = set()
    deadline = asyncio.get_event_loop().time() + _LIVE_MAX_SECONDS

    async def _emit_stage_events(current_events: list[dict[str, Any]]) -> None:
        nonlocal emitted_stages
        t_map = _compute_stage_timings(current_events)
        for stage_id in STAGE_ORDER_FROM_PIPELINE:
            if stage_id in emitted_stages or stage_id not in t_map:
                continue
            t = t_map[stage_id]
            idx = _stage_index(stage_id)
            next_stage = GRAPH_STAGES[idx + 1]["id"] if idx + 1 < len(GRAPH_STAGES) else None
            emitted_stages.add(stage_id)
            detail_now = _real_incident_detail(row, current_events)
            await asyncio.sleep(0.15)
            payload = {
                "source": "airp-backend",
                "incidentId": incident_id,
                "stage": stage_id,
                "nextStage": next_stage,
                "summary": _stage_label(stage_id),
                "snapshot": {"agent_event_count": len(current_events)},
                "started_at": _iso(t["started_at"]),
                "completed_at": _iso(t["completed_at"]),
                "duration_ms": t["duration_ms"],
                "event_count": t["event_count"],
                "detail": detail_now,
            }
            # Capture event in outer scope via the sentinel queue below
            _stage_event_queue.append(payload)

    _stage_event_queue: list[dict[str, Any]] = []

    if is_live:
        # Live mode: emit already-completed stages, then poll for new events.
        await _emit_stage_events(events)
        for p in _stage_event_queue:
            yield sse_event("stage_completed", p)
        _stage_event_queue.clear()

        while True:
            if asyncio.get_event_loop().time() > deadline:
                yield sse_event(
                    "resolution_error",
                    {"error": "Live stream exceeded max wait; reload to replay.", "incidentId": incident_id},
                )
                return
            await asyncio.sleep(_LIVE_POLL_INTERVAL)
            current_row = await airp_db.fetch_incident(incident_id) or row
            current_events = await airp_db.fetch_events(incident_id)
            await _emit_stage_events(current_events)
            for p in _stage_event_queue:
                yield sse_event("stage_completed", p)
            _stage_event_queue.clear()
            if _is_terminal_workflow(current_row, current_events):
                events = current_events
                row = current_row  # noqa: F841 - used in closure & final detail below
                break
    else:
        await _emit_stage_events(events)
        for p in _stage_event_queue:
            yield sse_event("stage_completed", p)
        _stage_event_queue.clear()

    final_events = await airp_db.fetch_events(incident_id)
    final_row = await airp_db.fetch_incident(incident_id) or row
    final_detail = _real_incident_detail(final_row, final_events)
    final_start = final_events[0]["created_at"] if final_events else workflow_start
    final_end = final_events[-1]["created_at"] if final_events else workflow_end
    final_duration_ms = (
        int((final_end - final_start).total_seconds() * 1000)
        if final_start and final_end
        else workflow_duration_ms
    )
    await asyncio.sleep(0.1)
    yield sse_event(
        "run_completed",
        {
            "summary": "Workflow complete." if is_live else "Replay complete.",
            "mode": "live" if is_live else "replay",
            "incidentId": incident_id,
            "issueCreated": final_detail["incident"].get("issueCreated"),
            "pullRequest": final_detail["incident"].get("pullRequest"),
            "snapshot": final_detail["snapshot"],
            "workflow_duration_ms": final_duration_ms,
            "workflow_started_at": _iso(final_start) if final_start else None,
            "workflow_completed_at": _iso(final_end) if final_end else None,
            "detail": final_detail,
        },
    )

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator


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


def list_resolution_incidents() -> dict[str, Any]:
    items = [
        _incident_summary(record)
        for record in DUMMY_GRAPH_INCIDENTS
        if record.get("state") == "unresolved"
    ]
    return {
        "source": "langgraph-demo",
        "polling": True,
        "items": items,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def get_resolution_incident(incident_id: str) -> dict[str, Any] | None:
    record = _find_record(incident_id)
    if not record:
        return None
    return _incident_detail(record)


async def stream_incident_resolution(incident_id: str) -> AsyncIterator[str]:
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

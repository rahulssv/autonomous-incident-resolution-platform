from __future__ import annotations

from types import SimpleNamespace

import pytest

from airp.workflows.activities import _persist_documentation_output

pytestmark = pytest.mark.asyncio


class FakeIncidentService:
    def __init__(self) -> None:
        self.reports = []
        self.events = []
        self.created_payloads = []

    async def list_documentation_reports(self, incident_id: str, *, limit: int, offset: int = 0):
        _ = incident_id, limit, offset
        return self.reports

    async def create_documentation_report(self, incident_id: str, payload):
        self.created_payloads.append(payload)
        report = SimpleNamespace(
            id=f"doc-{len(self.reports) + 1}",
            incident_id=incident_id,
            title=payload.title,
            status=payload.status,
            publish_recommended=payload.publish_recommended,
            publishing_enabled=payload.publishing_enabled,
            extra=payload.metadata,
        )
        self.reports.append(report)
        return report

    async def add_event(self, incident_id: str, payload):
        self.events.append((incident_id, payload))
        return SimpleNamespace(id=f"evt-{len(self.events)}")


async def test_documentation_output_persistence_is_idempotent() -> None:
    service = FakeIncidentService()
    state = {
        "documentation_report": {
            "title": "RCA Draft: Checkout latency spike",
            "executive_summary": "Checkout latency increased after a timeout change.",
            "root_cause_summary": "Timeout configuration likely caused the incident.",
            "impact_summary": "Critical checkout latency degraded.",
            "evidence_summary": "GitHub and Kubernetes evidence were reviewed.",
            "remediation_summary": "Use an approval-gated timeout fix.",
            "follow_up_tasks": ["add_latency_regression_test"],
            "source_refs": ["github", "kubernetes"],
            "publish_recommended": True,
            "publishing_enabled": False,
            "confidence": 0.82,
        }
    }

    await _persist_documentation_output(service, "inc-1", state)
    await _persist_documentation_output(service, "inc-1", state)

    assert len(service.reports) == 1
    assert len(service.events) == 1
    assert service.created_payloads[0].metadata["source"] == "langgraph.documentation"
    assert service.events[0][1].event_type == "documentation.report.persisted"

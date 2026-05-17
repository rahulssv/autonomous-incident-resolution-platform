from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from airp.agents.prompts import (
    DOCUMENTATION_REPORT_PROMPT_VERSION,
    documentation_report_messages,
)
from airp.agents.state import AgentEvent, AgentGraphState, DocumentationReportDraft
from airp.core.config import Settings, get_settings
from airp.core.policy import ExternalActionPolicy


class DocumentationStructuredChatClient(Protocol):
    def structured_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[DocumentationReportDraft],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> DocumentationReportDraft:
        """Return a validated structured documentation draft response."""


class DocumentationAgent:
    name = "documentation"

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: DocumentationStructuredChatClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.policy = ExternalActionPolicy(self.settings)

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        report, model_call = self.generate_report(state)
        event = AgentEvent(
            event_type="documentation.drafted",
            agent=self.name,
            payload=report.model_dump(mode="json"),
        )
        model_calls = [model_call] if model_call else []

        return {
            "documentation_report": report.model_dump(mode="json"),
            "model_calls": model_calls,
            "next_action": "embedding",
            "agent_events": [event.model_dump(mode="json")],
        }

    def generate_report(
        self, state: AgentGraphState
    ) -> tuple[DocumentationReportDraft, dict[str, Any] | None]:
        if self.llm_client is None:
            return self._deterministic_report(state), None

        started = time.monotonic()
        validation_result: dict[str, Any]
        try:
            report = self.llm_client.structured_chat(
                model=self.settings.llm_documentation_model,
                messages=documentation_report_messages(
                    incident=self._incident_payload(state),
                    timeline=state.get("agent_events", []),
                    evidence_bundle=state.get("rca_evidence_bundle", {}),
                    rca_hypotheses=state.get("rca_hypotheses", []),
                    remediation_result=state.get("remediation_result", {}),
                    policy=self._policy_payload(),
                ),
                response_model=DocumentationReportDraft,
                temperature=0.0,
                request_id=state.get("correlation_id") or state.get("incident_id"),
            )
            report, validation_result = self._ground_output(report)
        except Exception as exc:  # noqa: BLE001 - documentation should degrade gracefully
            report = self._deterministic_report(state)
            report.follow_up_tasks.append(
                f"Review documentation draft; structured generation failed: {exc}"
            )
            validation_result = {
                "valid": False,
                "schema": "DocumentationReportDraft",
                "error": str(exc),
                "fallback": "deterministic",
            }

        payload = report.model_dump(mode="json")
        model_call = {
            "model_name": self.settings.llm_documentation_model,
            "prompt_template_version": DOCUMENTATION_REPORT_PROMPT_VERSION,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "response_hash": _stable_hash(payload),
            "validation_result": validation_result,
        }
        return report, model_call

    def _deterministic_report(self, state: AgentGraphState) -> DocumentationReportDraft:
        publishing_policy = self.policy.documentation_publishing()
        hypotheses = state.get("rca_hypotheses", [])
        top_hypothesis = hypotheses[0] if hypotheses else {}
        remediation = state.get("remediation_result") or {}
        evidence_refs = self._evidence_refs(state)
        title = state.get("title") or f"Incident {state.get('incident_id')}"
        root_cause = top_hypothesis.get(
            "hypothesis",
            "RCA did not produce a sufficiently supported root-cause hypothesis.",
        )
        remediation_summary = remediation.get(
            "plan_summary",
            "No remediation plan has been generated yet.",
        )

        follow_up_tasks = list(remediation.get("recommended_actions") or [])
        if not publishing_policy.allowed:
            follow_up_tasks.append(publishing_policy.reason)

        return DocumentationReportDraft(
            title=f"RCA Draft: {title}",
            executive_summary=(
                f"AIRP processed {title} through monitoring, correlation, RCA, "
                "remediation planning, and documentation drafting."
            ),
            root_cause_summary=str(root_cause),
            impact_summary=(
                f"Severity was classified as {state.get('severity') or 'unknown'}; "
                "operator review is required before closing the incident."
            ),
            evidence_summary=(
                "Evidence refs considered: "
                f"{', '.join(evidence_refs) if evidence_refs else 'incident'}."
            ),
            remediation_summary=str(remediation_summary),
            follow_up_tasks=list(dict.fromkeys(follow_up_tasks)),
            source_refs=evidence_refs,
            publish_recommended=True,
            publishing_enabled=publishing_policy.allowed,
            confidence=float(top_hypothesis.get("confidence", 0.4) or 0.4),
        )

    def _ground_output(
        self, report: DocumentationReportDraft
    ) -> tuple[DocumentationReportDraft, dict[str, Any]]:
        publishing_policy = self.policy.documentation_publishing()
        follow_up_tasks = list(report.follow_up_tasks)
        if not publishing_policy.allowed and publishing_policy.reason not in follow_up_tasks:
            follow_up_tasks.append(publishing_policy.reason)
        grounded = bool(report.root_cause_summary and report.evidence_summary)
        return (
            report.model_copy(
                update={
                    "follow_up_tasks": follow_up_tasks,
                    "publishing_enabled": publishing_policy.allowed,
                    "confidence": min(max(report.confidence, 0.0), 1.0),
                }
            ),
            {
                "valid": True,
                "schema": "DocumentationReportDraft",
                "grounded": grounded,
                "publishing_enabled": publishing_policy.allowed,
            },
        )

    def _incident_payload(self, state: AgentGraphState) -> dict[str, Any]:
        return {
            "incident_id": state.get("incident_id"),
            "title": state.get("title"),
            "description": state.get("description"),
            "severity": state.get("severity"),
            "status": state.get("status"),
        }

    def _policy_payload(self) -> dict[str, Any]:
        publishing_policy = self.policy.documentation_publishing()
        return {
            "documentation_publishing_allowed": publishing_policy.allowed,
            "documentation_publishing_reason": publishing_policy.reason,
        }

    def _evidence_refs(self, state: AgentGraphState) -> list[str]:
        refs: list[str] = []
        bundle = state.get("rca_evidence_bundle") or {}
        refs.extend(
            ref for ref in bundle.get("evidence_sources", []) if isinstance(ref, str)
        )
        for hypothesis in state.get("rca_hypotheses", []):
            refs.extend(
                ref
                for ref in hypothesis.get("supporting_evidence_refs", [])
                if isinstance(ref, str)
            )
        remediation = state.get("remediation_result") or {}
        refs.extend(ref for ref in remediation.get("evidence_refs", []) if isinstance(ref, str))
        return list(dict.fromkeys(refs))


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()

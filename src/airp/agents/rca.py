from __future__ import annotations

from airp.agents.evidence import RCAEvidenceCollector
from airp.agents.state import AgentEvent, AgentGraphState, RCAEvidenceBundle, RCAPlan


class RCAAgent:
    name = "rca"

    def __init__(self, evidence_collector: RCAEvidenceCollector | None = None) -> None:
        self.evidence_collector = evidence_collector

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        plan = self.plan_evidence_collection(state)
        if self.evidence_collector is not None:
            collected = await self.evidence_collector.collect(state)
            self._attach_collected_evidence(plan, collected.model_dump(mode="json"))

        event = AgentEvent(
            event_type="rca.started",
            agent=self.name,
            payload={
                "status": plan.status,
                "summary": plan.summary,
                "next_steps": plan.next_steps,
                "confidence": plan.confidence,
                "evidence_sources": plan.evidence_bundle.evidence_sources,
                "tool_call_count": len(plan.evidence_bundle.tool_calls),
            },
        )
        return {
            "rca_plan": plan.model_dump(mode="json"),
            "rca_evidence_bundle": plan.evidence_bundle.model_dump(mode="json"),
            "tool_calls": [
                *state.get("tool_calls", []),
                *plan.evidence_bundle.tool_calls,
            ],
            "next_action": "embedding",
            "agent_events": [*state.get("agent_events", []), event.model_dump(mode="json")],
        }

    def plan_evidence_collection(self, state: AgentGraphState) -> RCAPlan:
        monitoring = state.get("monitoring_assessment") or {}
        correlation = state.get("correlation_result") or {}
        service_context = state.get("service_context") or {}
        workload_context = state.get("workload_context") or {}

        evidence_sources = ["incident"]
        if monitoring:
            evidence_sources.append("monitoring")
        if correlation:
            evidence_sources.append("correlation")
        if service_context:
            evidence_sources.append("service_catalog")
        if workload_context:
            evidence_sources.append("runtime_workload")

        bundle = RCAEvidenceBundle(
            incident_id=state["incident_id"],
            evidence_sources=evidence_sources,
            monitoring_summary=monitoring.get("summary"),
            correlation_summary=correlation.get("context_summary"),
            service_context=service_context,
            workload_context=workload_context,
        )
        next_steps = [
            "collect_kubernetes_logs_events_and_rollout_state",
            "collect_github_commits_prs_and_changed_files",
            "correlate_running_image_to_repository_commit",
        ]

        ready = bool(service_context or workload_context or correlation)
        return RCAPlan(
            status="ready_for_evidence_collection" if ready else "needs_manual_triage",
            summary=self._summary(state, correlation),
            evidence_bundle=bundle,
            next_steps=next_steps,
            confidence=0.6 if ready else 0.35,
        )

    def _attach_collected_evidence(
        self, plan: RCAPlan, collected: dict[str, object]
    ) -> None:
        bundle = plan.evidence_bundle
        for source in ("kubernetes", "github", "dockerhub"):
            value = collected.get(source)
            if isinstance(value, dict) and value:
                setattr(bundle, source, value)
                bundle.evidence_sources.append(source)
        tool_calls = collected.get("tool_calls")
        if isinstance(tool_calls, list):
            bundle.tool_calls.extend(
                item for item in tool_calls if isinstance(item, dict)
            )
        bundle.evidence_sources = list(dict.fromkeys(bundle.evidence_sources))

    def _summary(self, state: AgentGraphState, correlation: dict) -> str:
        title = state.get("title") or f"incident {state['incident_id']}"
        context = correlation.get("context_summary")
        if context:
            return f"RCA evidence planning started for {title}. {context}"
        return f"RCA evidence planning started for {title}; catalog context is incomplete."

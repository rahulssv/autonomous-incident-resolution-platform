from __future__ import annotations

from airp.agents.state import AgentEvent, AgentGraphState, RCAEvidenceBundle, RCAPlan


class RCAAgent:
    name = "rca"

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        plan = self.plan_evidence_collection(state)
        event = AgentEvent(
            event_type="rca.started",
            agent=self.name,
            payload=plan.model_dump(mode="json"),
        )
        return {
            "rca_plan": plan.model_dump(mode="json"),
            "rca_evidence_bundle": plan.evidence_bundle.model_dump(mode="json"),
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

    def _summary(self, state: AgentGraphState, correlation: dict) -> str:
        title = state.get("title") or f"incident {state['incident_id']}"
        context = correlation.get("context_summary")
        if context:
            return f"RCA evidence planning started for {title}. {context}"
        return f"RCA evidence planning started for {title}; catalog context is incomplete."

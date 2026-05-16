from __future__ import annotations

from airp.agents.state import AgentEvent, AgentGraphState, CorrelationResult


class CorrelationAgent:
    name = "correlation"

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        result = self.correlate(state)
        event = AgentEvent(
            event_type="correlation.completed",
            agent=self.name,
            payload=result.model_dump(mode="json"),
        )
        return {
            "correlation_result": result.model_dump(mode="json"),
            "next_action": result.recommended_next_agent,
            "agent_events": [*state.get("agent_events", []), event.model_dump(mode="json")],
        }

    def correlate(self, state: AgentGraphState) -> CorrelationResult:
        service_context = state.get("service_context") or {}
        workload_context = state.get("workload_context") or {}
        monitoring = state.get("monitoring_assessment") or {}

        service_name = service_context.get("name") or monitoring.get("affected_service")
        repository_url = service_context.get("repository_url")
        docker_image = service_context.get("docker_image") or workload_context.get("image")
        namespace = service_context.get("namespace") or workload_context.get("namespace")
        pod_name = workload_context.get("pod_name")
        workload_match = bool(workload_context)

        context_bits = []
        if service_name:
            context_bits.append(f"service={service_name}")
        if namespace:
            context_bits.append(f"namespace={namespace}")
        if pod_name:
            context_bits.append(f"pod={pod_name}")
        if repository_url:
            context_bits.append(f"repository={repository_url}")
        if docker_image:
            context_bits.append(f"image={docker_image}")

        if not context_bits:
            context_summary = "No catalog or runtime workload context is available yet."
            confidence = 0.25
        else:
            context_summary = "Correlated incident context: " + ", ".join(context_bits)
            confidence = 0.75 if workload_match else 0.55

        return CorrelationResult(
            service_name=service_name,
            repository_url=repository_url,
            docker_image=docker_image,
            namespace=namespace,
            pod_name=pod_name,
            workload_match=workload_match,
            context_summary=context_summary,
            recommended_next_agent="rca",
            confidence=confidence,
        )

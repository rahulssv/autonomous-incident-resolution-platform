from __future__ import annotations

import re

from airp.agents.state import AgentEvent, AgentGraphState, CorrelationResult
from airp.core.config import Settings, get_settings


class CorrelationAgent:
    name = "correlation"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

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
            "agent_events": [event.model_dump(mode="json")],
        }

    def correlate(self, state: AgentGraphState) -> CorrelationResult:
        service_context = state.get("service_context") or {}
        workload_context = state.get("workload_context") or {}
        monitoring = state.get("monitoring_assessment") or {}

        # The alert's own labels beat the monitoring model's prose: it only sees
        # the incident title, so "OOMKilled in checkout worker" yields the
        # service name "checkout worker" — a space that makes every derived
        # repository URL 404.
        service_name = (
            service_context.get("name")
            or workload_context.get("service_name")
            or workload_context.get("deployment")
            or monitoring.get("affected_service")
        )
        repository_url = service_context.get("repository_url")
        if not repository_url and service_name:
            repository_url = self._infer_repository_url(service_name)
        docker_image = service_context.get("docker_image") or workload_context.get("image")
        namespace = service_context.get("namespace") or workload_context.get("namespace")
        pod_name = workload_context.get("pod_name")
        # Alert-derived context is not a catalog match and must not claim one.
        workload_match = bool(workload_context) and workload_context.get("source") != "alert_labels"

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

    def _infer_repository_url(self, service_name: str) -> str | None:
        org = (getattr(self.settings, "client_github_org", "") or "").strip()
        slug = _repository_slug(service_name)
        if not org or not slug:
            return None
        return f"https://github.com/{org}/{slug}"


def _repository_slug(service_name: str) -> str:
    """Coerce a service name into something that can be a GitHub repository name.

    A guessed URL is only useful if it is well-formed. Whitespace and other
    characters GitHub does not allow are folded to hyphens rather than
    interpolated raw, which previously produced unfetchable URLs like
    ``https://github.com/AIRP-client/checkout worker``.
    """
    slug = re.sub(r"[^a-z0-9._-]+", "-", service_name.strip().lower())
    return slug.strip("-")

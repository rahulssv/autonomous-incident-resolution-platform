from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from airp.agents.evidence import RCAEvidenceCollector
from airp.agents.prompts import RCA_HYPOTHESIS_PROMPT_VERSION, rca_hypothesis_messages
from airp.agents.state import (
    AgentEvent,
    AgentGraphState,
    RCAEvidenceBundle,
    RCAHypothesisOutput,
    RCAHypothesisSet,
    RCAPlan,
)
from airp.core.config import Settings, get_settings


class RCAStructuredChatClient(Protocol):
    def structured_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[RCAHypothesisSet],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> RCAHypothesisSet:
        """Return a validated structured RCA hypothesis response."""


class RCAAgent:
    name = "rca"

    def __init__(
        self,
        settings: Settings | None = None,
        evidence_collector: RCAEvidenceCollector | None = None,
        llm_client: RCAStructuredChatClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.evidence_collector = evidence_collector
        self.llm_client = llm_client

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        plan = self.plan_evidence_collection(state)
        if self.evidence_collector is not None:
            collected = await self.evidence_collector.collect(state)
            self._attach_collected_evidence(plan, collected.model_dump(mode="json"))

        hypothesis_result, model_call = self.generate_hypotheses(state, plan)
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
        hypothesis_event = AgentEvent(
            event_type="rca.hypotheses.generated",
            agent=self.name,
            payload={
                "hypothesis_count": len(hypothesis_result.hypotheses),
                "escalation_required": hypothesis_result.escalation_required,
                "escalation_reason": hypothesis_result.escalation_reason,
            },
        )
        agent_events = [
            *state.get("agent_events", []),
            event.model_dump(mode="json"),
            hypothesis_event.model_dump(mode="json"),
        ]
        model_calls = list(state.get("model_calls", []))
        if model_call:
            model_calls.append(model_call)
        return {
            "rca_plan": plan.model_dump(mode="json"),
            "rca_evidence_bundle": plan.evidence_bundle.model_dump(mode="json"),
            "rca_hypothesis_result": hypothesis_result.model_dump(mode="json"),
            "rca_hypotheses": [
                hypothesis.model_dump(mode="json")
                for hypothesis in hypothesis_result.hypotheses
            ],
            "tool_calls": [
                *state.get("tool_calls", []),
                *plan.evidence_bundle.tool_calls,
            ],
            "model_calls": model_calls,
            "next_action": "embedding",
            "agent_events": agent_events,
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

    def generate_hypotheses(
        self, state: AgentGraphState, plan: RCAPlan
    ) -> tuple[RCAHypothesisSet, dict[str, Any] | None]:
        if self.llm_client is None:
            return self._deterministic_hypotheses(plan), None

        messages = rca_hypothesis_messages(
            incident={
                "incident_id": state.get("incident_id"),
                "title": state.get("title"),
                "description": state.get("description"),
                "severity": state.get("severity"),
                "status": state.get("status"),
            },
            evidence_bundle=plan.evidence_bundle.model_dump(mode="json"),
        )
        started = time.monotonic()
        try:
            result = self.llm_client.structured_chat(
                model=self.settings.llm_rca_model,
                messages=messages,
                response_model=RCAHypothesisSet,
                temperature=0.0,
                request_id=state.get("correlation_id") or state.get("incident_id"),
            )
            validation_result = {
                "valid": True,
                "schema": "RCAHypothesisSet",
                "hypothesis_count": len(result.hypotheses),
            }
        except Exception as exc:  # noqa: BLE001 - RCA should escalate, not crash the graph
            result = RCAHypothesisSet(
                summary="RCA hypothesis generation failed; manual triage is required.",
                hypotheses=[
                    RCAHypothesisOutput(
                        rank=1,
                        hypothesis="Unable to generate a validated RCA hypothesis.",
                        confidence=0.1,
                        supporting_evidence_refs=plan.evidence_bundle.evidence_sources,
                        contradictions=[str(exc)],
                        next_actions=["manual_sre_triage"],
                    )
                ],
                escalation_required=True,
                escalation_reason=str(exc),
            )
            validation_result = {
                "valid": False,
                "schema": "RCAHypothesisSet",
                "error": str(exc),
            }

        payload = result.model_dump(mode="json")
        model_call = {
            "model_name": self.settings.llm_rca_model,
            "prompt_template_version": RCA_HYPOTHESIS_PROMPT_VERSION,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "response_hash": _stable_hash(payload),
            "validation_result": validation_result,
        }
        return result, model_call

    def _deterministic_hypotheses(self, plan: RCAPlan) -> RCAHypothesisSet:
        bundle = plan.evidence_bundle
        refs = bundle.evidence_sources
        if not any(source in refs for source in ("kubernetes", "github", "dockerhub")):
            return RCAHypothesisSet(
                summary="RCA evidence is incomplete; manual triage is recommended.",
                hypotheses=[
                    RCAHypothesisOutput(
                        rank=1,
                        hypothesis=(
                            "Insufficient runtime or repository evidence to identify a "
                            "root cause."
                        ),
                        confidence=0.25,
                        supporting_evidence_refs=refs,
                        contradictions=[
                            "No Kubernetes, GitHub, or DockerHub evidence was collected."
                        ],
                        next_actions=[
                            "collect_kubernetes_logs_events_and_rollout_state",
                            "collect_github_commits_prs_and_changed_files",
                        ],
                    )
                ],
                escalation_required=True,
                escalation_reason="Evidence collection has not produced enough grounded context.",
            )

        signals: list[str] = []
        next_actions = ["review_ranked_evidence_with_service_owner"]
        if bundle.kubernetes:
            restarts = [
                pod.get("restart_count")
                for pod in bundle.kubernetes.get("pods", [])
                if pod.get("restart_count") is not None
            ]
            if restarts and max(restarts) > 0:
                signals.append("Kubernetes evidence shows container restarts.")
                next_actions.append("inspect_recent_pod_logs_and_events")
        if bundle.github.get("commits") or bundle.github.get("merged_prs"):
            signals.append("GitHub evidence shows recent repository change activity.")
            next_actions.append("compare_recent_changes_to_error_window")
        if bundle.dockerhub.get("source_commit_sha"):
            signals.append("DockerHub metadata links the running image to a source commit.")
            next_actions.append("correlate_image_source_commit_with_recent_prs")

        hypothesis = "Runtime symptoms may be related to recent deployment or code changes."
        if signals:
            hypothesis = " ".join([hypothesis, *signals])

        return RCAHypothesisSet(
            summary="Generated deterministic RCA hypothesis from collected evidence.",
            hypotheses=[
                RCAHypothesisOutput(
                    rank=1,
                    hypothesis=hypothesis,
                    confidence=0.55,
                    supporting_evidence_refs=[
                        source
                        for source in ("kubernetes", "github", "dockerhub")
                        if source in refs
                    ],
                    contradictions=[],
                    next_actions=next_actions,
                )
            ],
            escalation_required=False,
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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()

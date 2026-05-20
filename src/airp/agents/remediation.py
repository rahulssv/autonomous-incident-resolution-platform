from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Protocol

from pydantic import BaseModel, Field

from airp.agents.prompts import (
    REMEDIATION_PLAN_PROMPT_VERSION,
    code_change_messages,
    remediation_plan_messages,
)
from airp.agents.state import (
    AgentEvent,
    AgentGraphState,
    CodeChange,
    RemediationAgentOutput,
)
from airp.core.config import Settings, get_settings
from airp.core.policy import ExternalActionPolicy

logger = logging.getLogger(__name__)


class CodeChangeProposalSet(BaseModel):
    """Structured LLM output for code-fix proposals."""

    code_changes: list[CodeChange] = Field(default_factory=list)
    rationale: str = ""


class RemediationStructuredChatClient(Protocol):
    def structured_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_model: type[RemediationAgentOutput],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        request_id: str | None = None,
    ) -> RemediationAgentOutput:
        """Return a validated structured remediation plan response."""


class RemediationAgent:
    name = "remediation"

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: RemediationStructuredChatClient | None = None,
        github_client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        # Optional GitHub MCP client — when present the agent will fetch the suspect
        # source file and propose a patched version that ends up as a real code-fix PR.
        self.github_client = github_client
        self.policy = ExternalActionPolicy(self.settings)

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        result, model_call = self.generate_plan(state)
        model_calls = [model_call] if model_call else []

        # After the textual plan is generated, attempt to produce a real code change
        # (a patched suspect file) when the conditions are right. This is what
        # turns "documentation-only PR" runs into proper code-fix PRs.
        try:
            code_changes, code_model_call = await self._maybe_generate_code_changes(state, result)
        except Exception as exc:  # noqa: BLE001 - never crash the graph on code-fix failure
            logger.warning("code change generation failed: %s", exc)
            code_changes, code_model_call = [], None
        if code_changes:
            result = result.model_copy(update={"code_changes": code_changes})
        if code_model_call:
            model_calls.append(code_model_call)

        event = AgentEvent(
            event_type="remediation.planned",
            agent=self.name,
            payload=result.model_dump(mode="json"),
        )
        return {
            "remediation_result": result.model_dump(mode="json"),
            "model_calls": model_calls,
            "next_action": "embedding",
            "agent_events": [event.model_dump(mode="json")],
        }

    async def _maybe_generate_code_changes(
        self,
        state: AgentGraphState,
        plan: RemediationAgentOutput,
    ) -> tuple[list[CodeChange], dict[str, Any] | None]:
        """Best-effort code-fix proposal. Returns ([], None) when not applicable.

        We deliberately do NOT gate on plan.pr_creation_recommended — even when
        the RCA hypothesis validation failed (a common transient), if we have a
        repo + a recently-changed suspect file + LLM + GitHub MCP, it is worth
        asking the LLM whether a small fix to that file would help. The LLM is
        free to return empty code_changes when it isn't confident.
        """
        if self.llm_client is None or self.github_client is None:
            return [], None

        repo_url = self._repository_context(state).get("repository_url")
        if not repo_url:
            return [], None

        # Identify the suspect file: the path most recently changed in the github
        # evidence bundle. This is the strongest signal that a recent commit broke
        # something.
        suspect = self._pick_suspect_file(state)
        if not suspect:
            return [], None

        ref = suspect.get("ref") or "main"
        path = suspect["path"]

        # Pull the current contents of that file from GitHub.
        try:
            file_payload = await self.github_client.read_file(
                repo_url, path=path, ref=ref
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("read_file failed for %s:%s: %s", repo_url, path, exc)
            return [], None
        if not file_payload or not file_payload.get("content"):
            return [], None

        started = time.monotonic()
        try:
            proposal: CodeChangeProposalSet = self.llm_client.structured_chat(
                model=self.settings.llm_remediation_model,
                messages=code_change_messages(
                    incident=self._incident_payload(state),
                    rca_hypotheses=state.get("rca_hypotheses", []),
                    remediation_plan=plan.model_dump(mode="json"),
                    suspect_file={
                        "path": path,
                        "ref": ref,
                        "content": file_payload["content"],
                        "html_url": file_payload.get("html_url"),
                    },
                ),
                response_model=CodeChangeProposalSet,
                temperature=0.0,
                request_id=state.get("correlation_id") or state.get("incident_id"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("code change LLM call failed: %s", exc)
            return [], None

        # Reject changes that touch unrelated paths.
        sanitized: list[CodeChange] = []
        for change in proposal.code_changes:
            if not change.content or not change.path:
                continue
            if change.path != path:
                # Constrain the agent: it may only modify the suspect file for now.
                continue
            if change.content.strip() == file_payload["content"].strip():
                # No-op: skip changes identical to the current file content.
                continue
            sanitized.append(
                change.model_copy(
                    update={
                        "message": change.message
                        or f"AIRP automated fix for {path}",
                    }
                )
            )

        payload = proposal.model_dump(mode="json")
        model_call = {
            "model_name": self.settings.llm_remediation_model,
            "prompt_template_version": REMEDIATION_PLAN_PROMPT_VERSION + ".code-change-v1",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "response_hash": _stable_hash(payload),
            "validation_result": {
                "valid": True,
                "schema": "CodeChangeProposalSet",
                "accepted_changes": len(sanitized),
                "rejected_changes": len(proposal.code_changes) - len(sanitized),
            },
        }
        return sanitized, model_call

    def _pick_suspect_file(self, state: AgentGraphState) -> dict[str, Any] | None:
        """Pick the most recently changed file in the github evidence bundle."""
        bundle = state.get("rca_evidence_bundle") or {}
        github = bundle.get("github") or {}
        # Prefer files mentioned in the most recent commit (commits[0] is newest
        # from GitHub's /commits ordering).
        for commit in github.get("commits") or []:
            for changed in commit.get("changed_files") or []:
                if changed.get("path"):
                    return {"path": changed["path"], "ref": commit.get("sha") or "main"}
        # Fallback: top-level changed_files
        for changed in github.get("changed_files") or []:
            if changed.get("path"):
                return {"path": changed["path"], "ref": "main"}
        return None

    def generate_plan(
        self, state: AgentGraphState
    ) -> tuple[RemediationAgentOutput, dict[str, Any] | None]:
        if self.llm_client is None:
            return self._deterministic_plan(state), None

        started = time.monotonic()
        validation_result: dict[str, Any]
        try:
            result = self.llm_client.structured_chat(
                model=self.settings.llm_remediation_model,
                messages=remediation_plan_messages(
                    incident=self._incident_payload(state),
                    rca_hypotheses=state.get("rca_hypotheses", []),
                    evidence_bundle=state.get("rca_evidence_bundle", {}),
                    repository_context=self._repository_context(state),
                    policy=self._policy_payload(),
                ),
                response_model=RemediationAgentOutput,
                temperature=0.0,
                request_id=state.get("correlation_id") or state.get("incident_id"),
            )
            result, validation_result = self._ground_output(state, result)
        except Exception as exc:  # noqa: BLE001 - remediation should fall back, not crash
            result = self._deterministic_plan(state)
            result.blocked_path_findings.append(
                f"Structured remediation generation failed: {exc}"
            )
            validation_result = {
                "valid": False,
                "schema": "RemediationAgentOutput",
                "error": str(exc),
                "fallback": "deterministic",
            }

        payload = result.model_dump(mode="json")
        model_call = {
            "model_name": self.settings.llm_remediation_model,
            "prompt_template_version": REMEDIATION_PLAN_PROMPT_VERSION,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "response_hash": _stable_hash(payload),
            "validation_result": validation_result,
        }
        return result, model_call

    def _deterministic_plan(self, state: AgentGraphState) -> RemediationAgentOutput:
        hypotheses = state.get("rca_hypotheses", [])
        hypothesis = hypotheses[0] if hypotheses else {}
        rca_result = state.get("rca_hypothesis_result") or {}
        service_context = state.get("service_context") or {}
        correlation = state.get("correlation_result") or {}
        repository_url = (
            service_context.get("repository_url") or correlation.get("repository_url")
        )
        pr_policy = self.policy.remediation_pr_creation()
        evidence_refs = self._default_evidence_refs(state)
        confidence = float(hypothesis.get("confidence", 0.2) or 0.2)
        escalation_required = bool(rca_result.get("escalation_required"))
        severity = str(state.get("severity") or "warning")
        risk_score = self._risk_score(confidence, severity, escalation_required)
        risk_level = self._risk_level(risk_score)

        blocked_findings = []
        if not repository_url:
            blocked_findings.append(
                "Repository context is missing; no branch or PR can be prepared."
            )
        if not pr_policy.allowed:
            blocked_findings.append(pr_policy.reason)
        if escalation_required:
            blocked_findings.append(
                rca_result.get("escalation_reason")
                or "RCA requires manual triage before remediation execution."
            )

        probable_root_cause = hypothesis.get(
            "hypothesis",
            "The root cause is not sufficiently established for automated remediation.",
        )
        recommended_actions = list(hypothesis.get("next_actions") or [])
        if not recommended_actions:
            recommended_actions = ["review_rca_with_service_owner"]
        if repository_url:
            recommended_actions.append("prepare_minimal_repo_change_after_approval")

        return RemediationAgentOutput(
            plan_summary=(
                "Propose a minimal, approval-gated remediation for "
                f"{state.get('title') or state.get('incident_id')}. "
                f"RCA signal: {probable_root_cause}"
            ),
            risk_level=risk_level,
            risk_score=risk_score,
            test_plan=(
                "Run targeted unit tests around the suspected change, service integration "
                "tests for the affected path, container build validation, and a canary or "
                "staged rollout check before production promotion."
            ),
            rollback_plan=(
                "If validation fails or error rates rise, revert the proposed change or "
                "roll back the AKS deployment to the last known healthy Docker image, then "
                "re-run the incident evidence collection."
            ),
            approval_required=True,
            blocked_path_findings=blocked_findings,
            recommended_actions=list(dict.fromkeys(recommended_actions)),
            evidence_refs=evidence_refs,
            external_writes_allowed=pr_policy.allowed,
            pr_creation_recommended=bool(repository_url and not escalation_required),
            confidence=min(max(confidence, 0.0), 1.0),
        )

    def _ground_output(
        self, state: AgentGraphState, result: RemediationAgentOutput
    ) -> tuple[RemediationAgentOutput, dict[str, Any]]:
        pr_policy = self.policy.remediation_pr_creation()
        allowed_refs = set(self._default_evidence_refs(state))
        unsupported_refs = sorted(
            ref for ref in result.evidence_refs if ref not in allowed_refs
        )
        evidence_refs = [
            ref for ref in result.evidence_refs if ref in allowed_refs
        ] or sorted(allowed_refs)
        blocked_findings = list(result.blocked_path_findings)
        if unsupported_refs:
            blocked_findings.append(
                "Unsupported remediation evidence refs were removed: "
                f"{', '.join(unsupported_refs)}"
            )
        if not pr_policy.allowed and pr_policy.reason not in blocked_findings:
            blocked_findings.append(pr_policy.reason)

        risk_score = min(max(result.risk_score, 0.0), 1.0)
        grounded = not unsupported_refs and bool(evidence_refs)
        normalized = result.model_copy(
            update={
                "risk_score": risk_score,
                "risk_level": self._risk_level(risk_score),
                "approval_required": True,
                "blocked_path_findings": blocked_findings,
                "evidence_refs": evidence_refs,
                "external_writes_allowed": pr_policy.allowed,
                "confidence": min(max(result.confidence, 0.0), 1.0),
            }
        )
        return (
            normalized,
            {
                "valid": True,
                "schema": "RemediationAgentOutput",
                "grounded": grounded,
                "unsupported_refs": unsupported_refs,
                "external_writes_allowed": pr_policy.allowed,
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

    def _repository_context(self, state: AgentGraphState) -> dict[str, Any]:
        service_context = state.get("service_context") or {}
        correlation = state.get("correlation_result") or {}
        return {
            "repository_url": service_context.get("repository_url")
            or correlation.get("repository_url"),
            "docker_image": service_context.get("docker_image")
            or correlation.get("docker_image"),
            "service_name": service_context.get("name") or correlation.get("service_name"),
            "namespace": service_context.get("namespace") or correlation.get("namespace"),
        }

    def _policy_payload(self) -> dict[str, Any]:
        pr_policy = self.policy.remediation_pr_creation()
        return {
            "remediation_pr_creation_allowed": pr_policy.allowed,
            "remediation_pr_creation_reason": pr_policy.reason,
            "external_writes_enabled": pr_policy.allowed,
            "approval_required": True,
        }

    def _default_evidence_refs(self, state: AgentGraphState) -> list[str]:
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
        return list(dict.fromkeys(refs or ["incident"]))

    def _risk_score(
        self, confidence: float, severity: str, escalation_required: bool
    ) -> float:
        if escalation_required:
            return 0.9
        if severity == "critical":
            return 0.75 if confidence < 0.7 else 0.65
        if confidence < 0.4:
            return 0.8
        return 0.45

    def _risk_level(self, risk_score: float) -> str:
        if risk_score >= 0.75:
            return "high"
        if risk_score >= 0.45:
            return "medium"
        return "low"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()

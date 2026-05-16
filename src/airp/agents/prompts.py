from __future__ import annotations

import json
from typing import Any

from airp.agents.safety import sanitize_untrusted_payload

RCA_HYPOTHESIS_PROMPT_VERSION = "rca-hypothesis-v1"
REMEDIATION_PLAN_PROMPT_VERSION = "remediation-plan-v1"
DOCUMENTATION_REPORT_PROMPT_VERSION = "documentation-report-v1"


def rca_hypothesis_messages(
    *,
    incident: dict[str, Any],
    evidence_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the versioned RCA hypothesis prompt for structured GenAI output."""

    return [
        {
            "role": "system",
            "content": (
                "You are the AIRP RCA Agent. Produce only JSON matching the requested "
                "schema. Ground every hypothesis in the supplied evidence refs. Use "
                "supporting_evidence_refs values from: kubernetes, github, dockerhub, "
                "monitoring, correlation, service_catalog, runtime_workload. Do not "
                "claim a root cause when evidence is missing; escalate instead."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "prompt_version": RCA_HYPOTHESIS_PROMPT_VERSION,
                    "incident": sanitize_untrusted_payload(incident),
                    "evidence_bundle": sanitize_untrusted_payload(evidence_bundle),
                },
                separators=(",", ":"),
                default=str,
            ),
        },
    ]


def remediation_plan_messages(
    *,
    incident: dict[str, Any],
    rca_hypotheses: list[dict[str, Any]],
    evidence_bundle: dict[str, Any],
    repository_context: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the versioned Remediation Agent prompt for structured GenAI output."""

    return [
        {
            "role": "system",
            "content": (
                "You are the AIRP Remediation Agent. Produce only JSON matching the "
                "requested schema. Propose a safe plan, test plan, rollback plan, risk "
                "score, approval requirement, blocked-path findings, and evidence refs. "
                "Do not claim that a branch, PR, Slack message, or external write was "
                "created. External writes require explicit policy and approval."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "prompt_version": REMEDIATION_PLAN_PROMPT_VERSION,
                    "incident": sanitize_untrusted_payload(incident),
                    "rca_hypotheses": sanitize_untrusted_payload(rca_hypotheses),
                    "evidence_bundle": sanitize_untrusted_payload(evidence_bundle),
                    "repository_context": sanitize_untrusted_payload(repository_context),
                    "policy": policy,
                },
                separators=(",", ":"),
                default=str,
            ),
        },
    ]


def documentation_report_messages(
    *,
    incident: dict[str, Any],
    timeline: list[dict[str, Any]],
    evidence_bundle: dict[str, Any],
    rca_hypotheses: list[dict[str, Any]],
    remediation_result: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the versioned Documentation Agent prompt for structured GenAI output."""

    return [
        {
            "role": "system",
            "content": (
                "You are the AIRP Documentation Agent. Produce only JSON matching the "
                "requested schema. Draft a concise final RCA report from supplied "
                "timeline, evidence, hypotheses, and remediation plan. Do not claim the "
                "report was published unless publishing_enabled is true."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "prompt_version": DOCUMENTATION_REPORT_PROMPT_VERSION,
                    "incident": sanitize_untrusted_payload(incident),
                    "timeline": sanitize_untrusted_payload(timeline),
                    "evidence_bundle": sanitize_untrusted_payload(evidence_bundle),
                    "rca_hypotheses": sanitize_untrusted_payload(rca_hypotheses),
                    "remediation_result": sanitize_untrusted_payload(remediation_result),
                    "policy": policy,
                },
                separators=(",", ":"),
                default=str,
            ),
        },
    ]

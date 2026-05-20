from __future__ import annotations

import json
from typing import Any

from airp.agents.safety import sanitize_untrusted_payload

RCA_HYPOTHESIS_PROMPT_VERSION = "rca-hypothesis-v2"
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
                "You are the AIRP RCA Agent. Return ONLY a single JSON object that "
                "strictly matches the schema below. No prose, no markdown fences, no "
                "extra fields, no comments.\n\n"
                "REQUIRED SCHEMA (RCAHypothesisSet):\n"
                "{\n"
                '  "summary": "<one-paragraph string overview of the RCA conclusions>",\n'
                '  "hypotheses": [\n'
                "    {\n"
                '      "rank": 1,                          // INTEGER >= 1, NOT a string id like "H1"\n'
                '      "hypothesis": "<string explaining the suspected root cause>",\n'
                '      "confidence": 0.85,                  // FLOAT 0.0-1.0, NOT "high"/"low"\n'
                '      "supporting_evidence_refs": ["github", "kubernetes"],\n'
                '      "supporting_evidence_ids": [],\n'
                '      "contradictions": [],\n'
                '      "next_actions": ["roll_back_deployment"]\n'
                "    }\n"
                "  ],\n"
                '  "escalation_required": false,           // BOOLEAN\n'
                '  "escalation_reason": null                // STRING or null\n'
                "}\n\n"
                "Field rules:\n"
                "- rank is an INTEGER starting at 1; do not use string identifiers like H1/H2.\n"
                "- confidence is a FLOAT between 0.0 and 1.0 (e.g. 0.9 for high, 0.3 for low).\n"
                "- supporting_evidence_refs values must come from: kubernetes, github, "
                "dockerhub, monitoring, correlation, service_catalog, runtime_workload.\n"
                "- Every hypothesis MUST include supporting_evidence_refs grounded in the "
                "supplied evidence; otherwise set escalation_required=true.\n"
                "- Do not claim a root cause when evidence is missing; escalate instead."
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

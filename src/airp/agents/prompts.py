from __future__ import annotations

import json
from typing import Any

RCA_HYPOTHESIS_PROMPT_VERSION = "rca-hypothesis-v1"


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
                    "incident": incident,
                    "evidence_bundle": evidence_bundle,
                },
                separators=(",", ":"),
                default=str,
            ),
        },
    ]

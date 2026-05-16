from __future__ import annotations

import re
from typing import Any

from airp.integrations.genaihub.redaction import redact_text

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(all\s+)?(previous|prior)\s+instructions\b"),
    re.compile(r"(?i)\bdisregard\s+(all\s+)?(previous|prior)\s+instructions\b"),
    re.compile(r"(?i)\breveal\s+(the\s+)?(system|developer)\s+(prompt|message)\b"),
    re.compile(r"(?i)\bexfiltrate\b"),
    re.compile(r"(?i)\bact\s+as\s+(system|developer|admin)\b"),
    re.compile(r"(?i)\btool\s+output\s+override\b"),
]

INJECTION_REPLACEMENT = "[UNTRUSTED_INSTRUCTION_REDACTED]"


def sanitize_untrusted_text(value: str) -> str:
    sanitized = redact_text(value)
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub(INJECTION_REPLACEMENT, sanitized)
    return sanitized


def sanitize_untrusted_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_untrusted_text(value)
    if isinstance(value, list):
        return [sanitize_untrusted_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_untrusted_payload(item) for key, item in value.items()}
    return value

from backend.src.airp.integrations.genaihub.redaction import redact_payload, redact_text


def test_redact_text_masks_common_secret_patterns() -> None:
    value = "token=super-secret Authorization: Bearer abc.def.ghi sk-abc1234567890"

    redacted = redact_text(value)

    assert "super-secret" not in redacted
    assert "abc.def.ghi" not in redacted
    assert "sk-abc1234567890" not in redacted
    assert redacted.count("[REDACTED]") >= 3


def test_redact_payload_recurses() -> None:
    payload = {"messages": [{"content": "api_key=secret-value"}]}

    redacted = redact_payload(payload)

    assert redacted == {"messages": [{"content": "[REDACTED]"}]}

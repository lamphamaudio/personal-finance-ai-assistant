import pytest

from spectra.chat.memory import extract_memory_candidates, has_sensitive_memory_payload, upsert_user_memory
from spectra.chat.redaction import redact_text


def test_memory_service_rejects_sensitive_payload_before_db():
    with pytest.raises(ValueError):
        upsert_user_memory(
            "user-1",
            "preference",
            "account_number",
            {"account_number": "1234567890123456"},
        )


def test_sensitive_memory_detector_rejects_tokens_and_long_identifiers():
    assert has_sensitive_memory_payload({"token": "secret"})
    assert has_sensitive_memory_payload({"value": "account 123456789012"})


def test_extract_memory_candidates_requires_confirmation_for_preference():
    candidates = extract_memory_candidates("Lan sau tra loi ngan gon hon nhe", "", [])

    assert candidates
    assert candidates[0]["memory_type"] == "preference"
    assert candidates[0]["requires_confirmation"] is True


def test_redact_text_masks_account_numbers_and_tokens():
    redacted = redact_text("Bearer abcdefghijklmnop account 1234567890123456 sk-abcdef1234567890")

    assert "abcdefghijklmnop" not in redacted
    assert "1234567890123456" not in redacted
    assert "sk-abcdef" not in redacted

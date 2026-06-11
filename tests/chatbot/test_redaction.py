from spectra.chat.redaction import mask_account_number, redact_payload


def test_redaction_masks_account_numbers():
    assert mask_account_number("1234567890") == "******7890"


def test_redact_payload_does_not_mutate_original():
    payload = {"account_number": "1234567890", "nested": {"reference_number": "987654321"}}

    redacted = redact_payload(payload)

    assert redacted["account_number"] == "******7890"
    assert redacted["nested"]["reference_number"] == "*****4321"
    assert payload["account_number"] == "1234567890"


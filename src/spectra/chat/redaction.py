"""Small redaction helpers for chatbot tool payloads."""

from __future__ import annotations

import copy
import re
from typing import Any


_LONG_NUMERIC_RE = re.compile(r"^\d{6,}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{12,}")
_BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
_ACCOUNT_NUMBER_RE = re.compile(r"\b\d{10,19}\b")
_LONG_IDENTIFIER_RE = re.compile(r"\b\d{8,}\b")
_STACK_TRACE_RE = re.compile(r"(?is)traceback \(most recent call last\):.*")


def mask_account_number(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) <= 4:
        return "*" * len(digits) if digits else ""
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_reference(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= 4:
        return "*" * len(raw) if raw else ""
    return "*" * (len(raw) - 4) + raw[-4:]


def redact_text(value: str) -> str:
    """Redact secrets and raw identifiers before chat persistence."""
    text = str(value or "")
    text = _STACK_TRACE_RE.sub("[redacted stack trace]", text)
    text = _OPENAI_KEY_RE.sub("[redacted api key]", text)
    text = _BEARER_TOKEN_RE.sub("Bearer [redacted token]", text)
    text = _ACCOUNT_NUMBER_RE.sub(lambda match: mask_reference(match.group(0)), text)
    text = _LONG_IDENTIFIER_RE.sub(lambda match: mask_reference(match.group(0)), text)
    return text


def redact_payload(payload: Any) -> Any:
    cloned = copy.deepcopy(payload)
    return _redact_value(cloned)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if "account_number" in normalized_key:
                redacted[key] = mask_account_number(str(item))
            elif "reference" in normalized_key:
                redacted[key] = mask_reference(str(item))
            elif normalized_key in {"user_id", "token", "access_token", "session_token"} or "token" in normalized_key:
                redacted[key] = mask_reference(str(item))
            elif normalized_key in {"password", "api_key", "openai_api_key", "cookie", "session_cookie"}:
                redacted[key] = "[redacted]"
            elif isinstance(item, str) and _LONG_NUMERIC_RE.fullmatch(item):
                redacted[key] = mask_reference(item)
            elif isinstance(item, str) and _UUID_RE.fullmatch(item) and normalized_key != "id":
                redacted[key] = mask_reference(item)
            else:
                redacted[key] = _redact_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        if _LONG_NUMERIC_RE.fullmatch(value):
            return mask_reference(value)
        return redact_text(value)
    return value

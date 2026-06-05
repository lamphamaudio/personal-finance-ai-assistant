"""Input guardrails for checking user query safety and scope."""

from __future__ import annotations

import unicodedata
from spectra.chat.guardrails.rules import (
    INVESTMENT_KEYWORDS,
    OUT_OF_SCOPE_KEYWORDS,
    PROMPT_INJECTION_KEYWORDS,
    OPENAI_KEY_RE,
    BEARER_TOKEN_RE,
    ACCOUNT_NUMBER_RE,
)


def fold_text(value: str) -> str:
    """Normalize Vietnamese accents and convert to lowercase ascii."""
    value = str(value or "").replace("đ", "d").replace("Đ", "D").replace("Ä‘", "d").replace("Ä ", "D")
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().split())


class InputGuardResult:
    def __init__(self, passed: bool, reason: str | None = None, refusal_key: str | None = None):
        self.passed = passed
        self.reason = reason
        self.refusal_key = refusal_key


class PromptInjectionGuard:
    def check(self, message: str) -> InputGuardResult:
        normalized = fold_text(message)
        # Check direct keyword matches
        for keyword in PROMPT_INJECTION_KEYWORDS:
            if keyword in normalized or keyword in message.lower():
                return InputGuardResult(
                    passed=False,
                    reason=f"Detected prompt injection pattern: {keyword}",
                    refusal_key="prompt_injection",
                )
        return InputGuardResult(passed=True)


class OutOfScopeGuard:
    def check(self, message: str) -> InputGuardResult:
        normalized = fold_text(message)
        for keyword in OUT_OF_SCOPE_KEYWORDS:
            if keyword in normalized or keyword in message.lower():
                return InputGuardResult(
                    passed=False,
                    reason=f"Detected out-of-scope topic: {keyword}",
                    refusal_key="out_of_scope",
                )
        return InputGuardResult(passed=True)


class InvestmentAdviceGuard:
    def check(self, message: str) -> InputGuardResult:
        normalized = fold_text(message)
        for keyword in INVESTMENT_KEYWORDS:
            if keyword in normalized or keyword in message.lower():
                return InputGuardResult(
                    passed=False,
                    reason=f"Detected investment advice request: {keyword}",
                    refusal_key="investment_advice",
                )
        return InputGuardResult(passed=True)


class SensitiveDataGuard:
    def check(self, message: str) -> InputGuardResult:
        # Check for OpenAI key
        if OPENAI_KEY_RE.search(message):
            return InputGuardResult(
                passed=False,
                reason="Detected raw OpenAI API key in query",
                refusal_key="sensitive_data",
            )
        # Check for Bearer token
        if BEARER_TOKEN_RE.search(message):
            return InputGuardResult(
                passed=False,
                reason="Detected Bearer token in query",
                refusal_key="sensitive_data",
            )
        # Check for unmasked long account numbers
        if ACCOUNT_NUMBER_RE.search(message):
            return InputGuardResult(
                passed=False,
                reason="Detected raw account number in query",
                refusal_key="sensitive_data",
            )
        return InputGuardResult(passed=True)

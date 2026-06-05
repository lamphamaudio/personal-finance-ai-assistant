"""Output guardrails for scanning chatbot responses for leaks and ensuring disclaimers."""

from __future__ import annotations

import re
from spectra.chat.guardrails.rules import (
    OPENAI_KEY_RE,
    BEARER_TOKEN_RE,
    API_KEY_OR_SECRET_RE,
    UUID_RE,
    ACCOUNT_NUMBER_RE,
    FINANCIAL_DISCLAIMER,
)

# Additional output constraints
MAX_RESPONSE_LENGTH = 1500
TOOL_NAME_RE = re.compile(
    r"\b(?:get|update|create|archive|remember|forget|simulate|recommend|compare|plan)_[a-z0-9_]+\b",
    re.IGNORECASE,
)


class OutputGuardResult:
    def __init__(self, passed: bool, reason: str | None = None, redacted_answer: str | None = None):
        self.passed = passed
        self.reason = reason
        self.redacted_answer = redacted_answer


class CredentialLeakGuard:
    def check(self, answer: str) -> OutputGuardResult:
        if OPENAI_KEY_RE.search(answer):
            return OutputGuardResult(False, "Detected OpenAI key in output")
        if BEARER_TOKEN_RE.search(answer):
            return OutputGuardResult(False, "Detected Bearer token in output")
        if API_KEY_OR_SECRET_RE.search(answer):
            return OutputGuardResult(False, "Detected API key/secret keyword in output")
        return OutputGuardResult(True)


class PIILeakGuard:
    def check(self, answer: str) -> OutputGuardResult:
        if UUID_RE.search(answer):
            return OutputGuardResult(False, "Detected UUID in output")
        if ACCOUNT_NUMBER_RE.search(answer):
            return OutputGuardResult(False, "Detected unmasked bank account number in output")
        return OutputGuardResult(True)


class SystemPromptLeakGuard:
    def check(self, answer: str) -> OutputGuardResult:
        # Prevent output of tool names
        if TOOL_NAME_RE.search(answer):
            return OutputGuardResult(False, "Detected internal tool name in output")
        # Ensure it doesn't contain prompt-injection reference tokens
        if "system prompt" in answer.lower() or "llm supervisor" in answer.lower():
            return OutputGuardResult(False, "Detected supervisor prompt metadata in output")
        if len(answer) > MAX_RESPONSE_LENGTH:
            return OutputGuardResult(False, f"Response exceeds max safe length: {len(answer)}")
        return OutputGuardResult(True)


class DisclaimerEnforcerGuard:
    def check(self, answer: str, intent_name: str) -> OutputGuardResult:
        # Intents related to financial health, budget recommendations, or saving suggestion advice
        sensitive_intents = {
            "FINANCIAL_HEALTH_SCORE",
            "SAVING_SUGGESTION",
            "OUT_OF_SCOPE_INVESTMENT_ADVICE",
        }
        if intent_name in sensitive_intents:
            # Check if disclaimer is already mentioned (case insensitive check on keywords like 'tham khao', 'chuyen nghiep')
            from spectra.chat.guardrails.input_guards import fold_text
            normalized = fold_text(answer)
            has_disclaimer = "tham khao" in normalized and ("chuyen nghiep" in normalized or "tu van" in normalized)
            if not has_disclaimer:
                # Proactively append the disclaimer at the end
                delim = "\n\n" if not answer.endswith("\n") else "\n"
                appended_answer = f"{answer}{delim}{FINANCIAL_DISCLAIMER}"
                return OutputGuardResult(
                    passed=True,
                    reason="Appended mandatory financial advice disclaimer",
                    redacted_answer=appended_answer,
                )
        return OutputGuardResult(True)

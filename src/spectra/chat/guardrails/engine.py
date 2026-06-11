"""Core Guardrails engine to run pipeline checks on input, tool call, and output."""

from __future__ import annotations

import logging
from typing import Any

from spectra.chat.models import ChatIntent, ChatResponse, ToolExecutionResult
from spectra.chat.guardrails.rules import REFUSAL_ANSWERS
from spectra.chat.guardrails.input_guards import (
    PromptInjectionGuard,
    OutOfScopeGuard,
    InvestmentAdviceGuard,
    SensitiveDataGuard,
)
from spectra.chat.guardrails.tool_guards import (
    UnregisteredToolGuard,
    ToolParameterGuard,
    WriteConfirmationGuard,
)
from spectra.chat.guardrails.output_guards import (
    CredentialLeakGuard,
    PIILeakGuard,
    SystemPromptLeakGuard,
    DisclaimerEnforcerGuard,
)

logger = logging.getLogger("spectra.chat.guardrails")


class GuardrailEngine:
    def __init__(self):
        # Input guards
        self.input_guards = [
            PromptInjectionGuard(),
            OutOfScopeGuard(),
            InvestmentAdviceGuard(),
            SensitiveDataGuard(),
        ]
        # Tool guards
        self.unregistered_tool_guard = UnregisteredToolGuard()
        self.tool_parameter_guard = ToolParameterGuard()
        self.write_confirmation_guard = WriteConfirmationGuard()
        # Output guards
        self.output_guards = [
            CredentialLeakGuard(),
            PIILeakGuard(),
            SystemPromptLeakGuard(),
        ]
        self.disclaimer_enforcer = DisclaimerEnforcerGuard()

    def check_input(self, message: str) -> ChatResponse | None:
        """Run all input guards. Returns ChatResponse if violated, else None."""
        for guard in self.input_guards:
            result = guard.check(message)
            if not result.passed:
                refusal_key = result.refusal_key or "prompt_injection"
                answer = REFUSAL_ANSWERS.get(refusal_key, REFUSAL_ANSWERS["prompt_injection"])
                
                # Map refusal keys to correct ChatIntent
                intent = ChatIntent.UNKNOWN
                if refusal_key == "investment_advice":
                    intent = ChatIntent.OUT_OF_SCOPE_INVESTMENT_ADVICE
                elif refusal_key == "sensitive_data":
                    intent = ChatIntent.PRIVACY_OR_PERMISSION
                
                logger.warning(
                    "Input Guardrail triggered: %s (Reason: %s)",
                    guard.__class__.__name__,
                    result.reason,
                )
                return ChatResponse(answer=answer, intent=intent)
        return None

    def check_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        confirmation_id: str | None,
        user_id: str | None,
    ) -> ToolExecutionResult | None:
        """Run all tool guards. Returns ToolExecutionResult with rejected status if violated, else None."""
        # Unregistered / dangerous check
        res = self.unregistered_tool_guard.check(tool_name, arguments, user_id)
        if not res.passed:
            logger.warning("Tool Guardrail triggered (Unregistered/Dangerous): %s", res.reason)
            return ToolExecutionResult(tool_name=tool_name, status=res.status, error=res.reason)

        # Parameter checks
        res = self.tool_parameter_guard.check(tool_name, arguments, user_id)
        if not res.passed:
            logger.warning("Tool Guardrail triggered (Parameter check): %s", res.reason)
            return ToolExecutionResult(tool_name=tool_name, status=res.status, error=res.reason)

        # Write confirmation checks
        res = self.write_confirmation_guard.check(tool_name, arguments, confirmation_id, user_id)
        if not res.passed:
            logger.warning("Tool Guardrail triggered (Write confirmation check): %s", res.reason)
            return ToolExecutionResult(tool_name=tool_name, status=res.status, error=res.reason)

        return None

    def check_output(self, answer: str, intent_name: str) -> str:
        """Run all output guards. Returns sanitized or modified answer, or refusal message if violated."""
        # Check leak guards
        for guard in self.output_guards:
            result = guard.check(answer)
            if not result.passed:
                logger.error(
                    "Output Guardrail triggered: %s (Reason: %s)",
                    guard.__class__.__name__,
                    result.reason,
                )
                return REFUSAL_ANSWERS["output_violation"]

        # Check disclaimer enforcer
        res = self.disclaimer_enforcer.check(answer, intent_name)
        if res.redacted_answer:
            return res.redacted_answer

        return answer


# Singleton engine instance
guardrail_engine = GuardrailEngine()
